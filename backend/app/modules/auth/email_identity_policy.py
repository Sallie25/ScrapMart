"""Pure, versioned registration collision policy; never login authorization.

Legacy source values are not rewritten. ``owned`` means an OWNED CANDIDATE:
future backfill must still aggregate contributions from distinct Users and block
conflicts. ``blocked`` candidates must never become owned, even for one User.
Invalid/unclassifiable results block readiness; they must never be skipped.

V1 uses NFC, not general local-part NFKC/transliteration. Unicode case-fold and
explicit dotted-I projections are conservative compatibility candidates. Domain
identity uses nontransitional UTS #46/IDNA2008; compatibility domains are derived
from decoded U-labels so Unicode and A-label input have identical results.

No settings, database/HTTP imports, DNS, logging, or persistent state. Existing
signup code deliberately does not call this module yet.
"""
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import unicodedata

import email_validator
import idna
from idna import idnadata, uts46data


POLICY_VERSION = 1
ASCII_BOUNDARY_WHITESPACE = " \t\n\r\v\f"
ASCII_CASE_MAP = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
MAX_KEY_LENGTH = 255
MAX_ALIASES = 9  # At most three local forms crossed with three domain forms.


@dataclass(frozen=True)
class NormalizationVersions:
    unicode_data: str
    email_validator: str
    idna: str
    idna_data: str
    uts46_data: str


EXPECTED_VERSIONS = NormalizationVersions("15.1.0", "2.3.0", "3.20", "18.0.0", "18.0.0")


class PolicyVersionMismatch(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Unsupported email identity normalization versions")


class InvalidRegistrationEmail(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid registration email")


class AliasDisposition(str, Enum):
    OWNED = "owned"
    BLOCKED = "blocked"


class LegacyClassification(str, Enum):
    ALIASES = "aliases"
    ZERO_ASCII_ALIASES = "zero_ascii_aliases"
    INVALID = "invalid"
    UNCLASSIFIABLE = "unclassifiable"


@dataclass(frozen=True)
class ReservationAlias:
    key: str = field(repr=False)
    disposition: AliasDisposition


@dataclass(frozen=True)
class LegacyIdentity:
    classification: LegacyClassification
    aliases: tuple[ReservationAlias, ...] = field(repr=False)
    fingerprint: str
    reason: str | None = None
    policy_version: int = POLICY_VERSION

    @property
    def blocks_readiness(self) -> bool:
        return self.classification not in {
            LegacyClassification.ALIASES, LegacyClassification.ZERO_ASCII_ALIASES,
        }


def normalization_versions() -> NormalizationVersions:
    """Inspect only in-memory library constants, not settings or package files."""
    return NormalizationVersions(
        getattr(unicodedata, "unidata_version", "unknown"),
        getattr(email_validator, "__version__", "unknown"),
        getattr(idna, "__version__", "unknown"),
        getattr(idnadata, "__version__", "unknown"),
        getattr(uts46data, "__version__", "unknown"),
    )


def policy_fingerprint() -> str:
    """Fail closed on unapproved tables/libraries, without pinning Python patch."""
    if normalization_versions() != EXPECTED_VERSIONS:
        raise PolicyVersionMismatch()
    descriptor = {
        "version": POLICY_VERSION,
        "versions": asdict(EXPECTED_VERSIONS),
        "boundary_whitespace": ASCII_BOUNDARY_WHITESPACE,
        "case_map": "ASCII A-Z to a-z",
        "local_canonical": "NFC then ASCII-only case map",
        "local_compatibility": "NFC(casefold(NFC(local))); dotted-i projection",
        "dotted_i": "NFC(NFC(casefold(text)).replace(U+0069 U+0307,U+0069))",
        "domain": "IDNA2008; UTS46; nontransitional; STD3; strict separators; roundtrip",
        "domain_compatibility": "decoded U-label NFC casefold and dotted-i projection",
        "compatibility": "different from canonical means blocked; blocking dominates",
        "syntax": "SMTPUTF8 only for legacy; no quotes/display/literals/empty local; strict=False",
        "deliverability": "globally_deliverable=True; test_environment=True; no DNS",
        "max_key_length": MAX_KEY_LENGTH,
        "max_aliases": MAX_ALIASES,
        "invalid_transform": "unclassifiable; no partial alias result",
    }
    encoded = json.dumps(descriptor, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _validate_syntax(value: str, *, unicode_local: bool) -> None:
    # Set every policy-affecting option: library global defaults are mutable.
    # The returned normalized email is intentionally not used for local parts.
    email_validator.validate_email(
        value, allow_smtputf8=unicode_local, allow_empty_local=False,
        allow_quoted_local=False, allow_domain_literal=False,
        allow_display_name=False, strict=False, check_deliverability=False,
        test_environment=True, globally_deliverable=True,
    )


def _trim_and_check(value: str, *, new_registration: bool) -> str:
    if not isinstance(value, str):
        raise ValueError
    # This must precede trimming/NFC/case conversion for NEW registrations.
    if new_registration and not value.isascii():
        raise ValueError
    if not new_registration and len(value) > MAX_KEY_LENGTH:
        raise ValueError
    value.encode("utf-8", errors="strict")
    value = value.strip(ASCII_BOUNDARY_WHITESPACE)
    if not value or len(value) > MAX_KEY_LENGTH or value.count("@") != 1:
        raise ValueError
    return value


def _check_key(key: str) -> None:
    """Mirror the committed PostgreSQL C-collation key CHECK, plus syntax."""
    if (
        not 3 <= len(key) <= MAX_KEY_LENGTH or not key.isascii()
        or any(not 33 <= ord(character) <= 126 for character in key)
        or key != key.translate(ASCII_CASE_MAP) or key.count("@") != 1
        or key.startswith("@") or key.endswith("@")
    ):
        raise ValueError
    _validate_syntax(key, unicode_local=False)


def _domain_ascii(domain: str) -> str:
    return idna.encode(
        domain, strict=True, uts46=True, std3_rules=True, transitional=False,
    ).decode("ascii").translate(ASCII_CASE_MAP)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value.casefold())


def _dotted_i(value: str) -> str:
    # U+0130 and decomposed I + dot fold to i + dot. This explicit, lossy
    # exception preserves reviewed dotted-I collision protection in BOTH parts.
    return unicodedata.normalize("NFC", _fold(value).replace("i\u0307", "i"))


def canonical_registration_key(value: str) -> str:
    """Return one canonical key, not a complete future registration alias bundle.

    Future registration integration must also reserve compatibility aliases
    derived by legacy_email_identity(key), and aggregate conflicts. This function
    alone does not guarantee completeness or authorize existing-account access.
    """
    policy_fingerprint()
    try:
        value = _trim_and_check(value, new_registration=True).translate(ASCII_CASE_MAP)
        _check_key(value)
        _, domain = value.split("@")
        # Accepted ASCII domains must already be canonical A-label spellings;
        # do not silently rewrite a noncanonical or invalid punycode domain.
        if _domain_ascii(domain) != domain:
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise InvalidRegistrationEmail() from None


def legacy_email_identity(value: str) -> LegacyIdentity:
    """Classify one legacy value without changing it or consulting other Users.

    Error reasons are fixed codes, never submitted values/library messages.
    Failed required transformations invalidate the WHOLE result, even if some
    canonical aliases could have been generated or the local part has no ASCII.
    """
    fingerprint = policy_fingerprint()
    try:
        value = _trim_and_check(value, new_registration=False)
        _validate_syntax(value, unicode_local=True)
    except (ValueError, UnicodeError):
        return LegacyIdentity(LegacyClassification.INVALID, (), fingerprint, "invalid_source")

    try:
        local, domain = unicodedata.normalize("NFC", value).split("@")
        canonical_domain = _domain_ascii(domain)
        ulabel = idna.decode(canonical_domain, strict=True, uts46=True, std3_rules=True)
        if _domain_ascii(ulabel) != canonical_domain:
            raise ValueError
        domains = {canonical_domain: False}
        for variant in (_fold(ulabel), _dotted_i(ulabel)):
            alias = _domain_ascii(variant)  # A failure must not be skipped.
            domains[alias] = alias != canonical_domain

        canonical_local = local.translate(ASCII_CASE_MAP) if local.isascii() else None
        locals_: dict[str, bool] = {}
        if canonical_local is not None:
            locals_[canonical_local] = False
        for variant in (_fold(local), _dotted_i(local)):
            if variant.isascii():
                alias = variant.translate(ASCII_CASE_MAP)
                locals_[alias] = alias != canonical_local

        aliases: dict[str, bool] = {}
        for local_alias, local_blocked in locals_.items():
            for domain_alias, domain_blocked in domains.items():
                key = local_alias + "@" + domain_alias
                _check_key(key)
                aliases[key] = aliases.get(key, False) or local_blocked or domain_blocked
        if len(aliases) > MAX_ALIASES:
            raise ValueError
        result = tuple(
            ReservationAlias(key, AliasDisposition.BLOCKED if blocked else AliasDisposition.OWNED)
            for key, blocked in sorted(aliases.items())
        )
        classification = LegacyClassification.ALIASES if result else LegacyClassification.ZERO_ASCII_ALIASES
        return LegacyIdentity(classification, result, fingerprint)
    except (ValueError, UnicodeError):
        return LegacyIdentity(LegacyClassification.UNCLASSIFIABLE, (), fingerprint, "alias_transformation_failed")

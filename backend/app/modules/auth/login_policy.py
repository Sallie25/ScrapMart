"""Buyer login admission checks shared by lookup and Stage 2B admission.

Reservations are collision protection, not sufficient proof of login identity.
Only the stored email's own ASCII V1 key can authorize a Buyer login.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.email_identity_models import EmailIdentityPolicyState as Policy, POLICY_STATE_ID
from app.modules.auth.email_identity_policy import (
    InvalidRegistrationEmail, PolicyVersionMismatch, canonical_registration_key,
    policy_fingerprint,
)

APPROVED_FINGERPRINT = "cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f"


class InvalidBuyerCredentials(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class BuyerLoginUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Buyer login is temporarily unavailable")


def require_ready_registry(db: Session) -> None:
    try:
        if policy_fingerprint() != APPROVED_FINGERPRINT:
            raise BuyerLoginUnavailableError()
    except PolicyVersionMismatch:
        raise BuyerLoginUnavailableError() from None
    state = db.execute(select(Policy.status, Policy.policy_version).where(
        Policy.id == POLICY_STATE_ID,
    ).with_for_update(read=True)).one_or_none()
    if state is None or state.status != "ready" or state.policy_version != 1:
        raise BuyerLoginUnavailableError()


def stored_email_matches(email: str, key: str) -> bool:
    try:
        return canonical_registration_key(email) == key
    except InvalidRegistrationEmail:
        return False
    except PolicyVersionMismatch:
        raise BuyerLoginUnavailableError() from None

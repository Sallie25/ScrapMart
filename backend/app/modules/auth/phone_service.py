"""Shared phone OTP: keyed hashes, bounded guessing, atomic consumption."""
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from sqlalchemy import select
from app.infrastructure.sms import SmsDelivery
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.security import _decode_canonical_random_value
from app.modules.auth.session_service import SessionAuthenticationError, _utc
from app.modules.auth.vendor_authorization import VendorAuthorizationService

_PHONE = re.compile(r'\+[1-9][0-9]{7,14}', re.ASCII)
_CODE = re.compile(r'[0-9]{6}', re.ASCII)


class PhoneRateLimited(ValueError):
    def __init__(self, retry_after):
        self.retry_after = max(1, int(retry_after))
        super().__init__('Phone verification is temporarily limited')


def current_phone(value):
    # E.164 only; do not guess a country or reinterpret a stored local number.
    return value if isinstance(value, str) and _PHONE.fullmatch(value) else None


def otp_key(settings):
    try:
        raw = _decode_canonical_random_value(settings.phone_otp_secret.get_secret_value())
        if len(set(raw)) < 16:
            raise ValueError()
        return raw
    except (AttributeError, ValueError):
        raise VerificationInfrastructureUnavailable() from None


def digest_code(key, user_id, nonce, phone, code):
    return hmac.digest(key, f'{user_id}\0{nonce}\0{phone}\0{code}'.encode(), hashlib.sha256)


def phone_is_verified(db, user_id, phone):
    phone = current_phone(phone)
    if phone is None:
        return False
    row = db.execute(select(PhoneVerification.phone_number, PhoneVerification.verified_at).where(
        PhoneVerification.user_id == user_id)).one_or_none()
    return bool(row and row.verified_at is not None and row.phone_number == phone)


class PhoneVerificationService(VendorAuthorizationService):
    def _identity(self, db, claims):
        user = self._lock_user(db, claims.user_id)
        self._active_user(user)
        session = self._lock_session(db, claims.user_id, claims.session_id)
        now = self._now(db)
        self._active_session(db, session, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        return user, now

    def send_code(self, claims, delivery: SmsDelivery, settings):
        self._claims(claims)
        key = otp_key(settings)
        # Generated once, outside retried transactions. Never returned/logged.
        code = f'{secrets.randbelow(1_000_000):06d}'
        nonce = uuid.uuid4()

        def operation(db):
            user, now = self._identity(db, claims)
            phone = current_phone(user.phone_number)
            if phone is None:
                return None
            row = db.get(PhoneVerification, user.id)
            if row is None:
                row = PhoneVerification(user_id=user.id, attempts=0, sends=0)
                db.add(row)
            if row.sent_at and (now - _utc(row.sent_at, db)).total_seconds() < 60:
                raise PhoneRateLimited(60 - (now - _utc(row.sent_at, db)).total_seconds())
            if row.window_start is None or now >= _utc(row.window_start, db) + timedelta(hours=1):
                row.window_start, row.sends = now, 0
            if row.sends >= 6:
                raise PhoneRateLimited((_utc(row.window_start, db) + timedelta(hours=1) - now).total_seconds())
            # A fresh challenge requires fresh proof; it cannot coexist with
            # an earlier verified result.
            row.phone_number, row.verified_at = phone, None
            row.nonce, row.code_digest = nonce, digest_code(key, user.id, nonce, phone, code)
            row.expires_at, row.sent_at, row.attempts = now + timedelta(minutes=5), now, 0
            row.sends += 1
            db.flush()
            return phone
        phone = self._transaction(operation)
        if phone is None:
            return
        try:
            # Outside locks/transaction retries; provider must honor idempotency.
            delivery.send_code(phone, code, idempotency_key=str(nonce))
        except Exception:
            def invalidate(db):
                self._lock_user(db, claims.user_id)
                row = db.get(PhoneVerification, claims.user_id)
                if row is not None and row.nonce == nonce:
                    row.code_digest, row.expires_at, row.verified_at = None, None, None
            try:
                self._transaction(invalidate)
            except Exception:
                # No delivery success or verification is asserted. A pending
                # short-lived keyed challenge is never ownership evidence.
                pass
            raise VerificationInfrastructureUnavailable() from None

    def verify_code(self, claims, code, settings) -> bool:
        self._claims(claims)
        key = otp_key(settings)
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise ValueError('Invalid verification code')

        def operation(db):
            user, now = self._identity(db, claims)
            row = db.get(PhoneVerification, user.id)
            phone = current_phone(user.phone_number)
            if row is None or row.code_digest is None or row.phone_number != phone or row.expires_at is None:
                return False
            if now >= _utc(row.expires_at, db) or row.attempts >= 5:
                row.code_digest, row.expires_at = None, None
                return False
            row.attempts += 1
            match = hmac.compare_digest(row.code_digest, digest_code(key, user.id, row.nonce, phone, code))
            if match:
                row.code_digest, row.expires_at, row.verified_at = None, None, now
            elif row.attempts >= 5:
                row.code_digest, row.expires_at = None, None
            # Failures return normally so the attempt increment commits.
            return match
        return self._transaction(operation)

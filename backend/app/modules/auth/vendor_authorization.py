"""Live Vendor capabilities, safe reads, and transaction-bound selling admission.

JWT verification belongs to the HTTP boundary. Read authorization is a snapshot,
not permission to mutate later. Mutations must use run_approved_vendor_operation;
its callback shares the authorization transaction and may be retried in full.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.security import AccessTokenClaims
from app.modules.auth.session_models import AuthSession
from app.modules.auth.session_service import SessionService, SessionAuthenticationError, _require_uuid, _utc
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor

PROFILE_STATUSES = frozenset({"pending", "approved", "rejected", "suspended"})


class VendorPermissionError(ValueError):
    def __init__(self) -> None:
        super().__init__("Account operation is not permitted")


@dataclass(frozen=True)
class VendorIdentity:
    user_id: uuid.UUID
    vendor_id: uuid.UUID


@dataclass(frozen=True)
class VendorProfile:
    business_name: str = field(repr=False)
    verification_status: str
    full_name: str = field(repr=False)
    email: str = field(repr=False)
    phone_number: str | None = field(repr=False)
    created_at: datetime


@dataclass(frozen=True)
class AccountCapabilities:
    buyer: bool
    vendor: bool
    vendor_verification_status: str | None


_T = TypeVar("_T")


class VendorAuthorizationService(SessionService):
    @staticmethod
    def _claims(claims: AccessTokenClaims) -> None:
        if not isinstance(claims, AccessTokenClaims):
            raise SessionAuthenticationError()
        _require_uuid(claims.user_id)
        _require_uuid(claims.session_id)

    def _snapshot(self, db: Session, claims: AccessTokenClaims):
        # Explicit safe projection: never select password_hash or refresh history.
        row = db.execute(select(
            User.is_active, User.full_name, User.email, User.phone_number,
            AuthSession, BuyerProfile.id.label("buyer_id"),
            Vendor.id.label("vendor_id"), Vendor.business_name,
            Vendor.verification_status, Vendor.created_at.label("vendor_created_at"),
        ).select_from(User).join(AuthSession, AuthSession.user_id == User.id).outerjoin(
            BuyerProfile, BuyerProfile.user_id == User.id,
        ).outerjoin(Vendor, Vendor.user_id == User.id).where(
            User.id == claims.user_id, AuthSession.id == claims.session_id,
        )).one_or_none()
        if row is None or not row.is_active:
            raise SessionAuthenticationError()
        now = self._now(db)
        self._active_session(db, row.AuthSession, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        return row

    @staticmethod
    def _require_profile(vendor_id, status, *, selling: bool = False) -> None:
        if vendor_id is None or status not in PROFILE_STATUSES:
            raise VendorPermissionError()
        if selling and status != "approved":
            raise VendorPermissionError()

    def get_vendor_profile(self, claims: AccessTokenClaims) -> VendorProfile:
        self._claims(claims)

        def operation(db):
            row = self._snapshot(db, claims)
            self._require_profile(row.vendor_id, row.verification_status)
            return VendorProfile(row.business_name, row.verification_status,
                                 row.full_name, row.email, row.phone_number,
                                 _utc(row.vendor_created_at, db))
        return self._transaction(operation)

    def get_account_capabilities(self, claims: AccessTokenClaims) -> AccountCapabilities:
        self._claims(claims)

        def operation(db):
            row = self._snapshot(db, claims)
            if row.vendor_id is not None:
                self._require_profile(row.vendor_id, row.verification_status)
            return AccountCapabilities(row.buyer_id is not None, row.vendor_id is not None,
                                       row.verification_status)
        return self._transaction(operation)

    def require_approved_vendor(self, claims: AccessTokenClaims) -> VendorIdentity:
        """Live read authorization only; never reuse as a later mutation grant."""
        self._claims(claims)

        def operation(db):
            row = self._snapshot(db, claims)
            self._require_profile(row.vendor_id, row.verification_status, selling=True)
            from app.modules.vendors.evidence import require_approved_evidence
            require_approved_evidence(db, claims.user_id, row.vendor_id, self._settings)
            return VendorIdentity(claims.user_id, row.vendor_id)
        return self._transaction(operation)

    def run_approved_vendor_operation(
        self, claims: AccessTokenClaims,
        operation: Callable[[Session, VendorIdentity], _T],
    ) -> _T:
        """Run a database mutation under live approval/session locks.

        Order: User version update -> session UPDATE lock -> Vendor SHARE lock
        -> operation-specific resource locks. Approval changes must update the
        same Vendor row; their UPDATE conflicts with SHARE until commit. Existing
        session revocation follows the same User/session order. Time is sampled
        after all admission locks. Strong-isolation conflicts use shared retries.

        Callback must enforce ownership using identity.vendor_id, plus operation
        rules, and perform all writes on db. It must not commit/rollback, start a
        new transaction, return ORM objects, or perform external side effects:
        serialization/deadlock retries rerun the callback. Returns only after
        commit. SQLite tests cannot prove PostgreSQL row-lock semantics.
        """
        self._claims(claims)

        def authorized(db):
            self._active_user(self._lock_user(db, claims.user_id))
            session = self._lock_session(db, claims.user_id, claims.session_id)
            vendor = db.execute(select(Vendor.id, Vendor.verification_status).where(
                Vendor.user_id == claims.user_id,
            ).with_for_update(read=True)).one_or_none()
            now = self._now(db)
            self._active_session(db, session, now)
            if claims.expires_at <= now:
                raise SessionAuthenticationError()
            self._require_profile(None if vendor is None else vendor.id,
                                  None if vendor is None else vendor.verification_status,
                                  selling=True)
            from app.modules.vendors.evidence import require_approved_evidence
            require_approved_evidence(db, claims.user_id, vendor.id, self._settings)
            # Storage checks may take time: sample expiry again before writes.
            now = self._now(db)
            self._active_session(db, session, now)
            if claims.expires_at <= now:
                raise SessionAuthenticationError()
            return operation(db, VendorIdentity(claims.user_id, vendor.id))
        return self._transaction(authorized)

    def revoke_all_vendor_sessions(self, claims: AccessTokenClaims) -> None:
        """Authorize and revoke in one transaction, across both experiences.

        User version update -> current session UPDATE -> Vendor SHARE -> bulk
        revocation. Recheck session/JWT expiry after every admission lock. All
        recognized statuses may log out; approval is deliberately not required.
        """
        self._claims(claims)

        def operation(db):
            self._active_user(self._lock_user(db, claims.user_id))
            session = self._lock_session(db, claims.user_id, claims.session_id)
            vendor = db.execute(select(Vendor.id, Vendor.verification_status).where(
                Vendor.user_id == claims.user_id,
            ).with_for_update(read=True)).one_or_none()
            now = self._now(db)
            self._active_session(db, session, now)
            if claims.expires_at <= now:
                raise SessionAuthenticationError()
            self._require_profile(None if vendor is None else vendor.id,
                                  None if vendor is None else vendor.verification_status)
            self._revoke_all_session_records(db, claims.user_id, now)

        self._transaction(operation)

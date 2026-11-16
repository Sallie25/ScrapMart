"""Trusted operator utility; never exposed through HTTP or public role selection.

Run with a separately authorized provisioning database role, not the runtime role.
Runtime must have SELECT only on verification_reviewers, with no INSERT/UPDATE/
DELETE. All grant/revoke writers must lock the target User via this utility.
Use a ticket/operator reference, never identity evidence or credentials.
"""
import argparse
import uuid
from sqlalchemy import select
from app.modules.auth.session_service import SessionService
from app.modules.vendors.review_models import VerificationReviewer


def provision_reviewer(engine, user_id: uuid.UUID, reference: str, *, revoke=False):
    if not isinstance(user_id, uuid.UUID) or not isinstance(reference, str) or not reference.strip() or len(reference) > 200:
        raise ValueError('A User UUID and provisioning reference are required')
    service = SessionService(engine)
    def operation(db):
        user = service._lock_user(db, user_id)
        if not revoke:
            service._active_user(user)
        row = db.get(VerificationReviewer, user_id)
        now = service._now(db)
        if row is None:
            if revoke:
                return
            row = VerificationReviewer(user_id=user_id, granted_at=now, provisioning_reference=reference.strip())
            db.add(row)
        if revoke:
            row.revoked_at = now
        else:
            row.granted_at, row.revoked_at = now, None
        row.provisioning_reference = reference.strip()
    service._transaction(operation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', type=uuid.UUID, required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    from app.infrastructure.database.session import get_engine
    provision_reviewer(get_engine(), args.user_id, args.reference, revoke=args.revoke)
    print('Reviewer permission updated')


if __name__ == '__main__':
    main()

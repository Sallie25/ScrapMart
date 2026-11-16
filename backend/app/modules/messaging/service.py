"""Participant-isolated HTTP messaging using shared session transactions."""
import uuid
from sqlalchemy import select, or_, func
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.auth.session_service import SessionAuthenticationError, _utc
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor
from app.modules.listings.models import Listing
from app.modules.vendors.evidence import require_approved_evidence
from app.modules.listings.service import cursor_encode, older
from app.modules.messaging.models import Conversation, Message

class ConversationNotFound(ValueError): pass
class MessagingConflict(ValueError): pass

class MessagingService(VendorAuthorizationService):
    def _live(self,db,claims,session):
        now=self._now(db)
        self._active_session(db,session,now)
        if claims.expires_at<=now: raise SessionAuthenticationError()
        return now

    def _buyer(self,db,claims,owner_id=None):
        users={}
        for user_id in sorted({claims.user_id}|({owner_id} if owner_id else set()),key=lambda value:value.int):
            users[user_id]=self._lock_user(db,user_id)
        self._active_user(users[claims.user_id])
        session=self._lock_session(db,claims.user_id,claims.session_id)
        profile=db.scalar(select(BuyerProfile.id).where(BuyerProfile.user_id==claims.user_id).with_for_update(read=True))
        self._live(db,claims,session)
        if profile is None: raise SessionAuthenticationError()
        return profile,session,users

    def _identity(self, db, claims):
        self._active_user(self._lock_user(db, claims.user_id))
        session = self._lock_session(db, claims.user_id, claims.session_id)
        self._live(db, claims, session)
        buyer = db.scalar(select(BuyerProfile.id).where(BuyerProfile.user_id == claims.user_id))
        vendor = db.scalar(select(Vendor.id).where(Vendor.user_id == claims.user_id))
        if buyer is None and vendor is None: raise ConversationNotFound()
        return buyer, vendor, session

    @staticmethod
    def _scope(buyer, vendor):
        return or_(Conversation.buyer_profile_id == buyer if buyer else False,
                   Conversation.vendor_id == vendor if vendor else False)

    @staticmethod
    def _message(row, db):
        return dict(id=row.id, content=row.content, sender=row.sender_side,
                    created_at=_utc(row.created_at, db), read_at=_utc(row.read_at, db) if row.read_at else None)

    def _dto(self, db, row, side):
        unread = db.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == row.id, Message.sender_side != side, Message.read_at.is_(None)))
        return dict(id=row.id, listing_id=row.listing_id, created_at=_utc(row.created_at, db), unread_count=unread)

    def start(self, claims, request):
        self._claims(claims)
        def operation(db):
            owner = db.scalar(select(Vendor.user_id).join(Listing, Listing.vendor_id == Vendor.id).where(Listing.id == request.listing_id))
            buyer, session, users = self._buyer(db, claims, owner)
            existing = db.scalar(select(Conversation).where(Conversation.buyer_profile_id == buyer, Conversation.listing_id == request.listing_id))
            if existing: return self._dto(db, existing, 'buyer')
            if owner is None: raise ConversationNotFound()
            if owner == claims.user_id: raise MessagingConflict()
            vendor = db.scalar(select(Vendor).where(Vendor.user_id == owner).with_for_update(read=True))
            if vendor is None or not users[owner].is_active: raise VendorPermissionError()
            self._require_profile(vendor.id, vendor.verification_status, selling=True)
            require_approved_evidence(db, owner, vendor.id, self._settings)
            listing = db.scalar(select(Listing).where(Listing.id == request.listing_id, Listing.vendor_id == vendor.id).with_for_update(read=True))
            if listing is None or listing.status != 'active': raise MessagingConflict()
            now = self._live(db, claims, session)
            row = Conversation(id=uuid.uuid4(), listing_id=listing.id, buyer_profile_id=buyer, vendor_id=vendor.id, created_at=now)
            db.add(row); db.flush()
            return self._dto(db, row, 'buyer')
        return self._transaction(operation)

    def run(self, claims, action, *, key=None, value=None, limit=20, cursor=None):
        self._claims(claims)
        def operation(db):
            buyer, vendor, session = self._identity(db, claims)
            if action in {'list', 'unread'}:
                query = select(Conversation).where(self._scope(buyer, vendor))
                if action == 'unread':
                    incoming = or_((Conversation.buyer_profile_id == buyer) & (Message.sender_side == 'vendor') if buyer else False,
                                   (Conversation.vendor_id == vendor) & (Message.sender_side == 'buyer') if vendor else False)
                    result = {'unread_count': db.scalar(select(func.count()).select_from(Message).join(Conversation).where(self._scope(buyer, vendor), incoming, Message.read_at.is_(None)))}
                else:
                    if cursor: query = query.where(older(Conversation.created_at, Conversation.id, cursor))
                    rows = db.scalars(query.order_by(Conversation.created_at.desc(), Conversation.id.desc()).limit(limit+1)).all()
                    result = {'conversations': [self._dto(db, r, 'buyer' if r.buyer_profile_id == buyer else 'vendor') for r in rows[:limit]],
                              'next_cursor': cursor_encode(rows[limit-1].created_at, rows[limit-1].id) if len(rows)>limit else None}
            else:
                row = db.scalar(select(Conversation).where(Conversation.id == key, self._scope(buyer, vendor)).with_for_update())
                if row is None: raise ConversationNotFound()
                side = 'buyer' if row.buyer_profile_id == buyer else 'vendor'
                if action == 'send':
                    message = db.scalar(select(Message).where(Message.conversation_id == key, Message.sender_side == side, Message.request_id == value.request_id)) if value.request_id else None
                    if message and message.content != value.content: raise MessagingConflict()
                    if message is None:
                        message = Message(id=uuid.uuid4(), conversation_id=key, sender_side=side, content=value.content, request_id=value.request_id, created_at=self._live(db, claims, session))
                        db.add(message); db.flush()
                    result = self._message(message, db)
                elif action == 'read':
                    message = db.scalar(select(Message).where(Message.id == value.message_id, Message.conversation_id == key, Message.sender_side != side).with_for_update())
                    if message is None: raise ConversationNotFound()
                    if message.read_at is None: message.read_at = self._live(db, claims, session)
                    db.flush(); result = self._message(message, db)
                else:
                    query = select(Message).where(Message.conversation_id == key)
                    if cursor: query = query.where(older(Message.created_at, Message.id, cursor))
                    rows = db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit+1)).all()
                    result = {'messages': [self._message(m, db) for m in rows[:limit]],
                              'next_cursor': cursor_encode(rows[limit-1].created_at, rows[limit-1].id) if len(rows)>limit else None}
            self._live(db, claims, session)
            return result
        return self._transaction(operation)

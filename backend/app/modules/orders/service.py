"""Owned, inventory-locked COD orders. Delivery and Buyer receipt are not payment."""
import uuid
from decimal import Decimal,ROUND_HALF_UP,localcontext
from sqlalchemy import select
from app.modules.auth.models import User
from app.modules.auth.session_service import SessionAuthenticationError,SessionPersistenceError,_utc
from app.modules.auth.vendor_authorization import VendorAuthorizationService
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor
from app.modules.vendors.evidence import require_approved_evidence
from app.modules.listings.models import Listing
from app.modules.categories.models import Category
from app.modules.listings.service import MarketplaceService,ListingConflict,cursor_encode,older
from app.modules.orders.models import Order,OrderItem
from app.modules.orders.inventory import available_quantity


class OrderNotFound(ValueError): pass
class OrderConflict(ValueError): pass
class InvalidOrder(ValueError): pass


class OrderService(VendorAuthorizationService):
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

    def _vendor_read(self,db,claims):
        self._active_user(self._lock_user(db,claims.user_id))
        session=self._lock_session(db,claims.user_id,claims.session_id)
        vendor=db.scalar(select(Vendor).where(Vendor.user_id==claims.user_id).with_for_update(read=True))
        self._live(db,claims,session)
        self._require_profile(None if vendor is None else vendor.id,None if vendor is None else vendor.verification_status)
        return vendor.id,session

    @staticmethod
    def _item(db,order):
        item=db.scalar(select(OrderItem).where(OrderItem.order_id==order.id))
        if item is None: raise SessionPersistenceError()
        return item

    def _dto(self,db,order):
        item=self._item(db,order)
        result={'id':order.id,'request_id':order.request_id,'status':order.status,'currency':order.currency,
                'payment_method':order.payment_method,'total_amount':format(order.total_amount,'.2f'),
                'vendor_business_name':order.vendor_business_name,
                'item':{'listing_id':item.listing_id,'title':item.listing_title,'quantity':format(item.quantity,'.3f'),
                        'quantity_unit':item.quantity_unit,'listing_price':format(item.listing_price,'.2f'),
                        'price_type':item.price_type,'line_total':format(item.line_total,'.2f')}}
        for key in ('created_at','updated_at','accepted_at','preparing_at','delivered_at','completed_at','cancelled_at','rejected_at'):
            value=getattr(order,key); result[key]=_utc(value,db) if value else None
        return result

    def place(self,claims,request):
        self._claims(claims)
        def operation(db):
            owner_id=db.scalar(select(Vendor.user_id).join(Listing,Listing.vendor_id==Vendor.id).where(Listing.id==request.listing_id))
            buyer,session,users=self._buyer(db,claims,owner_id)
            existing=db.scalar(select(Order).where(Order.buyer_profile_id==buyer,Order.request_id==request.request_id))
            if existing:
                item=self._item(db,existing)
                if item.listing_id!=request.listing_id or item.quantity!=request.quantity: raise OrderConflict()
                return self._dto(db,existing)
            if owner_id is None: raise OrderNotFound()
            if owner_id==claims.user_id: raise OrderConflict()
            vendor=db.scalar(select(Vendor).where(Vendor.user_id==owner_id).with_for_update(read=True))
            if vendor is None or not users[owner_id].is_active or vendor.verification_status!='approved': raise OrderConflict()
            from app.modules.auth.vendor_authorization import VendorPermissionError
            try: require_approved_evidence(db,owner_id,vendor.id,self._settings)
            except VendorPermissionError: raise OrderConflict() from None
            listing=db.scalar(select(Listing).where(Listing.id==request.listing_id,Listing.vendor_id==vendor.id).with_for_update())
            if listing is None or listing.status!='active' or listing.price is None or listing.quantity is None or not listing.quantity_unit:
                raise OrderConflict()
            category=db.scalar(select(Category).where(Category.id==listing.category_id).with_for_update(read=True))
            if category is None or not category.is_active: raise OrderConflict()
            try: MarketplaceService(self._engine,settings=self._settings)._images(db,listing,required=True)
            except ListingConflict: raise OrderConflict() from None
            if request.quantity>available_quantity(db,listing): raise OrderConflict()
            if listing.quantity_unit=='pieces' and request.quantity!=request.quantity.to_integral_value(): raise InvalidOrder()
            if listing.price_type=='total' and request.quantity!=listing.quantity: raise InvalidOrder()
            with localcontext() as context:
                context.prec=40
                raw=listing.price if listing.price_type=='total' else listing.price*request.quantity
                total=raw.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if listing.price>0 and total==0: raise InvalidOrder()
            now=self._live(db,claims,session)
            order=Order(id=uuid.uuid4(),buyer_profile_id=buyer,vendor_id=vendor.id,request_id=request.request_id,
                        vendor_business_name=vendor.business_name,status='pending',currency='NGN',payment_method='pay_on_delivery',
                        total_amount=total,created_at=now,updated_at=now)
            db.add(order); db.flush()
            db.add(OrderItem(order_id=order.id,listing_id=listing.id,listing_title=listing.title,
                             quantity=request.quantity,quantity_unit=listing.quantity_unit,listing_price=listing.price,
                             price_type=listing.price_type,line_total=total))
            db.flush(); return self._dto(db,order)
        return self._transaction(operation)

    def read(self,claims,*,vendor=False,order_id=None,limit=20,cursor=None):
        self._claims(claims)
        def operation(db):
            if vendor:
                owner,session=self._vendor_read(db,claims)
                scope=Order.vendor_id==owner
            else:
                owner,session,_=self._buyer(db,claims)
                scope=Order.buyer_profile_id==owner
            query=select(Order).where(scope)
            if order_id:
                row=db.scalar(query.where(Order.id==order_id))
                if row is None: raise OrderNotFound()
                result=self._dto(db,row)
            else:
                if cursor: query=query.where(older(Order.created_at,Order.id,cursor))
                rows=db.scalars(query.order_by(Order.created_at.desc(),Order.id.desc()).limit(limit+1)).all()
                result={'orders':[self._dto(db,row) for row in rows[:limit]],
                        'next_cursor':cursor_encode(rows[limit-1].created_at,rows[limit-1].id) if len(rows)>limit else None}
            self._live(db,claims,session)
            return result
        return self._transaction(operation)

    def buyer_transition(self,claims,order_id,action):
        self._claims(claims)
        if action not in {'cancel','complete'}: raise InvalidOrder()
        def operation(db):
            target=None
            if action=='cancel':
                target=db.execute(select(OrderItem.listing_id,Vendor.user_id).join(Order,Order.id==OrderItem.order_id).join(
                    Vendor,Vendor.id==Order.vendor_id).join(BuyerProfile,BuyerProfile.id==Order.buyer_profile_id).where(
                    Order.id==order_id,BuyerProfile.user_id==claims.user_id)).one_or_none()
            buyer,session,_=self._buyer(db,claims,target.user_id if target else None)
            if action=='cancel':
                if target is None: raise OrderNotFound()
                listing=db.scalar(select(Listing).where(Listing.id==target.listing_id).with_for_update())
                if listing is None: raise OrderNotFound()
            order=db.scalar(select(Order).where(Order.id==order_id,Order.buyer_profile_id==buyer).with_for_update())
            if order is None: raise OrderNotFound()
            now=self._live(db,claims,session)
            if action=='cancel':
                if order.status not in {'pending','accepted'}: raise OrderConflict()
                order.status,order.cancelled_at='cancelled',now
            else:
                if order.status!='delivered': raise OrderConflict()
                order.status,order.completed_at='completed',now
            order.updated_at=now; db.flush(); return self._dto(db,order)
        return self._transaction(operation)

    def vendor_transition(self,claims,order_id,action):
        changes={'accept':('pending','accepted','accepted_at'),'reject':('pending','rejected','rejected_at'),
                 'prepare':('accepted','preparing','preparing_at'),'deliver':('preparing','delivered','delivered_at')}
        if action not in changes: raise InvalidOrder()
        def operation(db,identity):
            listing_id=db.scalar(select(OrderItem.listing_id).join(Order,Order.id==OrderItem.order_id).where(Order.id==order_id,Order.vendor_id==identity.vendor_id))
            if listing_id is None: raise OrderNotFound()
            listing=db.scalar(select(Listing).where(Listing.id==listing_id,Listing.vendor_id==identity.vendor_id).with_for_update())
            if listing is None: raise OrderNotFound()
            order=db.scalar(select(Order).where(Order.id==order_id,Order.vendor_id==identity.vendor_id).with_for_update())
            if order is None: raise OrderNotFound()
            before,after,stamp=changes[action]
            if order.status!=before: raise OrderConflict()
            session=self._lock_session(db,claims.user_id,claims.session_id)  # already held by authorization wrapper
            now=self._live(db,claims,session)
            order.status,order.updated_at=after,now
            setattr(order,stamp,now); db.flush(); return self._dto(db,order)
        return self.run_approved_vendor_operation(claims,operation)

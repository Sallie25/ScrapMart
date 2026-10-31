"""Transaction-bound Vendor listings and bounded, live-verified public reads."""
import base64
import io
import json
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from PIL import Image
from sqlalchemy import select, or_, and_, func, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.auth.session_service import _utc, SessionAuthenticationError
from app.modules.auth.session_models import AuthSession
from app.modules.vendors.evidence import require_approved_evidence
from app.modules.vendors.models import Vendor
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.listings.models import Listing, ListingImage
from app.infrastructure.storage.listing_photos import get_listing_photo_storage, safe_photo_url, sanitize_photo, ListingPhotoUnavailable


class ListingNotFound(ValueError): pass
class ListingConflict(ValueError): pass
class InvalidListing(ValueError): pass


FIELDS=('title','category_id','description','price','price_type','is_negotiable','quantity','quantity_unit',
        'condition','location_summary','lga','area','latitude','longitude','location_visibility','directions_allowed')
LOCATION_FIELDS={'location_summary','lga','area','latitude','longitude','location_visibility','directions_allowed'}


def cursor_encode(when,identifier):
    if when.tzinfo is None: when=when.replace(tzinfo=timezone.utc)
    return base64.urlsafe_b64encode(json.dumps([when.astimezone(timezone.utc).isoformat(),str(identifier)]).encode()).decode().rstrip('=')


def cursor_decode(value):
    if value is None: return None
    try:
        if len(value)>300: raise ValueError()
        date,identifier=json.loads(base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True))
        when=datetime.fromisoformat(date); key=uuid.UUID(identifier)
        if when.tzinfo is None or str(key)!=identifier: raise ValueError()
        return when.astimezone(timezone.utc),key
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise InvalidListing('Invalid cursor') from None


def older(column,identifier,cursor):
    return or_(column<cursor[0],and_(column==cursor[0],identifier<cursor[1]))


class MarketplaceService(VendorAuthorizationService):
    def _write_time(self, db, claims):
        # The shared authorization wrapper already holds User/session locks.
        # Resource/category/photo waits can still outlive the JWT/session clock.
        session = db.get(AuthSession, claims.session_id)
        now = self._now(db)
        if session is None or session.user_id != claims.user_id:
            raise SessionAuthenticationError()
        self._active_session(db, session, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        return now

    def _photos(self):
        return get_listing_photo_storage(self._settings or get_settings())

    @staticmethod
    def _owned(db,listing_id,vendor_id):
        row=db.scalar(select(Listing).where(Listing.id==listing_id,Listing.vendor_id==vendor_id).with_for_update())
        if row is None: raise ListingNotFound()
        return row

    @staticmethod
    def _category(db,category_id):
        if category_id is not None:
            row=db.scalar(select(Category).where(Category.id==category_id).with_for_update(read=True))
            if row is None or not row.is_active: raise InvalidListing('Choose an active category')

    @staticmethod
    def _values(row): return {key:getattr(row,key) for key in FIELDS}

    def _validate(self,db,values,*,consent=False,public=False):
        self._category(db,values.get('category_id'))
        quantity=values.get('quantity')
        if quantity is not None and values.get('quantity_unit')=='pieces' and quantity != quantity.to_integral_value():
            raise InvalidListing('Pieces must be a whole quantity')
        lat,lon=values.get('latitude'),values.get('longitude')
        if (lat is None)!=(lon is None): raise InvalidListing('Coordinates must be paired')
        visibility=values.get('location_visibility','approximate')
        if visibility=='hidden' and lat is not None: raise InvalidListing('Hidden locations cannot include coordinates')
        if values.get('directions_allowed') and (visibility!='public_site' or lat is None):
            raise InvalidListing('Directions require an explicitly public site')
        if visibility=='approximate' and lat is not None:
            values['latitude']=lat.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            values['longitude']=lon.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if public:
            if not consent: raise InvalidListing('Explicit public location consent is required')
            if visibility=='hidden' or any(values.get(key) is None for key in (
                'category_id','description','price','quantity','quantity_unit','condition','location_summary','latitude','longitude',
            )): raise InvalidListing('Complete listing information is required before publication')

    def _images(self,db,row,*,required=False):
        images=db.scalars(select(ListingImage).where(ListingImage.listing_id==row.id).order_by(ListingImage.position).limit(5)).all()
        if not images:
            if required: raise ListingConflict('At least one stored photo is required')
            return []
        storage=self._photos(); result=[]
        try:
            for image in images:
                if image.content_type!='image/jpeg' or not storage.exists(image.object_key): continue
                result.append({'id':image.id,'url':safe_photo_url(storage,image.object_key),'position':image.position,
                               'width':image.width,'height':image.height})
        except ListingPhotoUnavailable: raise
        except Exception: raise ListingPhotoUnavailable() from None
        if required and not result: raise ListingConflict('At least one stored photo is required')
        return result

    def _dto(self,db,row,*,public=False,images=None):
        result={key:getattr(row,key) for key in FIELDS}
        result.update(id=row.id,status=row.status,currency='NGN',created_at=_utc(row.created_at,db),
                      updated_at=_utc(row.updated_at,db),published_at=_utc(row.published_at,db) if row.published_at else None,
                      photos=self._images(db,row) if images is None else images)
        # Money/quantity stay exact strings in JSON, never binary floats.
        result['price']=format(row.price,'.2f') if row.price is not None else None
        result['quantity']=format(row.quantity,'.3f') if row.quantity is not None else None
        for field in ('latitude','longitude'):
            result[field]=format(getattr(row,field),'.6f') if getattr(row,field) is not None else None
        category=db.get(Category,row.category_id) if row.category_id else None
        result['category']={'id':category.id,'name':category.name,'slug':category.slug} if category else None
        if public:
            vendor=db.execute(select(Vendor.business_name).where(Vendor.id==row.vendor_id)).one()
            # Never project the private Vendor.shop_location or shop_address.
            result['vendor']={'business_name':vendor.business_name,'shop_location':row.location_summary,'verified':True}
        return result

    def create(self,claims,value):
        values=value.model_dump(exclude_unset=True,exclude={'public_location_consent'})
        values.setdefault('price_type','total'); values.setdefault('is_negotiable',False)
        values.setdefault('location_visibility','approximate'); values.setdefault('directions_allowed',False)
        def operation(db,identity):
            self._validate(db,values)
            self._write_time(db,claims)
            row=Listing(id=uuid.uuid4(),vendor_id=identity.vendor_id,status='draft',**values)
            db.add(row); db.flush()
            return self._dto(db,row)
        return self.run_approved_vendor_operation(claims,operation)

    def edit(self,claims,listing_id,value):
        patch=value.model_dump(exclude_unset=True,exclude={'public_location_consent'})
        if not patch: raise InvalidListing('Provide listing fields')
        def operation(db,identity):
            row=self._owned(db,listing_id,identity.vendor_id)
            if row.status not in {'draft','active','inactive'}: raise ListingConflict('This listing cannot be edited')
            values={**self._values(row),**patch}
            self._validate(db,values,consent=value.public_location_consent or not (set(patch)&LOCATION_FIELDS),public=row.status=='active')
            if row.status=='active': self._images(db,row,required=True)
            self._write_time(db,claims)
            for key in FIELDS: setattr(row,key,values.get(key))
            db.flush(); return self._dto(db,row)
        return self.run_approved_vendor_operation(claims,operation)

    def transition(self,claims,listing_id,action,*,consent=False):
        allowed={'publish':({'draft','inactive'},'active'),'pause':({'active'},'inactive'),
                 'sold':({'active','inactive'},'sold'),'archive':({'draft','active','inactive','sold'},'removed')}
        def operation(db,identity):
            row=self._owned(db,listing_id,identity.vendor_id)
            if action=='archive' and row.status=='removed':
                self._write_time(db,claims)
                return None
            states,target=allowed[action]
            if row.status not in states: raise ListingConflict('Invalid listing transition')
            if action=='publish':
                values=self._values(row); self._validate(db,values,consent=consent,public=True)
                self._images(db,row,required=True)
                now=self._write_time(db,claims)
                for key in FIELDS: setattr(row,key,values.get(key))
                row.published_at=now
            else:
                self._write_time(db,claims)
            row.status=target; db.flush()
            if action=='archive': return None
            if action!='publish':
                return {'id':row.id,'status':row.status,'published_at':_utc(row.published_at,db) if row.published_at else None}
            return self._dto(db,row)
        return self.run_approved_vendor_operation(claims,operation)

    def _owner(self,db,claims):
        row=self._snapshot(db,claims)
        self._require_profile(row.vendor_id,row.verification_status,selling=True)
        require_approved_evidence(db,claims.user_id,row.vendor_id,self._settings)
        return row.vendor_id

    def own(self,claims,listing_id=None,*,limit=20,cursor=None,status=None):
        self._claims(claims)
        def operation(db):
            vendor_id=self._owner(db,claims)
            if listing_id:
                row=db.scalar(select(Listing).where(Listing.id==listing_id,Listing.vendor_id==vendor_id))
                if row is None: raise ListingNotFound()
                return self._dto(db,row)
            query=select(Listing).where(Listing.vendor_id==vendor_id)
            query=query.where(Listing.status==status) if status else query.where(Listing.status!='removed')
            if cursor: query=query.where(older(Listing.created_at,Listing.id,cursor))
            rows=db.scalars(query.order_by(Listing.created_at.desc(),Listing.id.desc()).limit(limit+1)).all()
            return {'listings':[self._dto(db,row) for row in rows[:limit]],
                    'next_cursor':cursor_encode(rows[limit-1].created_at,rows[limit-1].id) if len(rows)>limit else None}
        return self._transaction(operation)

    def upload_photo(self,claims,listing_id,content):
        def authorize(db,identity):
            row=self._owned(db,listing_id,identity.vendor_id)
            if row.status not in {'draft','inactive'}: raise ListingConflict('Pause listing before changing photos')
            if db.scalar(select(func.count()).select_from(ListingImage).where(ListingImage.listing_id==row.id)) >= 5:
                raise ListingConflict('At most five photos are allowed')
            self._write_time(db,claims)
        self.run_approved_vendor_operation(claims,authorize)
        sanitized=sanitize_photo(content)
        with Image.open(io.BytesIO(sanitized)) as image: width,height=image.size
        storage=self._photos(); key=f'listings/{listing_id.hex}/{secrets.token_hex(32)}.jpg'
        try:
            storage.put(key,sanitized); url=safe_photo_url(storage,key)
        except Exception:
            try: storage.delete(key)
            except Exception: pass
            raise ListingPhotoUnavailable() from None
        def operation(db,identity):
            row=self._owned(db,listing_id,identity.vendor_id)
            if row.status not in {'draft','inactive'}: raise ListingConflict('Pause listing before changing photos')
            positions=set(db.scalars(select(ListingImage.position).where(ListingImage.listing_id==row.id)))
            position=next((p for p in range(5) if p not in positions),None)
            if position is None: raise ListingConflict('At most five photos are allowed')
            self._write_time(db,claims)
            photo=ListingImage(id=uuid.uuid4(),listing_id=row.id,object_key=key,position=position,
                               content_type='image/jpeg',size_bytes=len(sanitized),width=width,height=height)
            db.add(photo); db.flush()
            return {'id':photo.id,'url':url,'position':position,'width':width,'height':height}
        try: return self.run_approved_vendor_operation(claims,operation)
        except Exception:
            try:
                with Session(self._engine) as db:
                    exists=db.scalar(select(ListingImage.id).where(ListingImage.object_key==key).limit(1))
                if exists is None: storage.delete(key)
            except Exception: pass
            raise

    def delete_photo(self,claims,listing_id,image_id):
        def operation(db,identity):
            row=self._owned(db,listing_id,identity.vendor_id)
            if row.status not in {'draft','inactive'}: raise ListingConflict('Pause listing before changing photos')
            image=db.scalar(select(ListingImage).where(ListingImage.id==image_id,ListingImage.listing_id==row.id))
            if image is None: raise ListingNotFound()
            self._write_time(db,claims)
            key=image.object_key; db.delete(image); db.flush(); return key
        key=self.run_approved_vendor_operation(claims,operation)
        try:
            with Session(self._engine) as db:
                referenced=db.scalar(select(ListingImage.id).where(ListingImage.object_key==key).limit(1))
            if referenced is None: self._photos().delete(key)
        except Exception: pass  # Leave unadvertised objects for reconciliation.

    def _public_query(self):
        return select(Listing).join(Vendor,Vendor.id==Listing.vendor_id).join(User,User.id==Vendor.user_id).join(
            Category,Category.id==Listing.category_id).where(Listing.status=='active',Vendor.verification_status=='approved',
            Vendor.approval_review_id.is_not(None),User.is_active.is_(True),Category.is_active.is_(True),
            select(ListingImage.id).where(ListingImage.listing_id==Listing.id).exists())

    def browse(self,*,listing_id=None,limit=20,cursor=None,q=None,category=None,location=None,condition=None,min_price=None,max_price=None):
        def operation(db):
            if db.get_bind().dialect.name=='postgresql': db.execute(text("SET LOCAL statement_timeout='5s'"))
            query=self._public_query()
            if listing_id: query=query.where(Listing.id==listing_id)
            if cursor: query=query.where(older(Listing.published_at,Listing.id,cursor))
            if q: query=query.where(or_(Listing.title.icontains(q,autoescape=True),Listing.description.icontains(q,autoescape=True)))
            if category: query=query.where(Listing.category_id==category)
            if location: query=query.where(or_(*(column.icontains(location,autoescape=True) for column in (Listing.location_summary,Listing.lga,Listing.area))))
            if condition: query=query.where(Listing.condition==condition)
            if min_price is not None: query=query.where(Listing.price>=min_price)
            if max_price is not None: query=query.where(Listing.price<=max_price)
            rows=db.scalars(query.order_by(Listing.published_at.desc(),Listing.id.desc()).limit(1 if listing_id else 26)).all()
            approved={}; result=[]; last=None; processed=0
            for row in rows[:25]:
                processed+=1; last=row
                if row.vendor_id not in approved:
                    owner_id=db.scalar(select(Vendor.user_id).where(Vendor.id==row.vendor_id))
                    try: require_approved_evidence(db,owner_id,row.vendor_id,self._settings)
                    except VendorPermissionError: approved[row.vendor_id]=False
                    else: approved[row.vendor_id]=True
                if not approved[row.vendor_id]: continue
                try: images=self._images(db,row,required=True)
                except ListingConflict: continue
                result.append(self._dto(db,row,public=True,images=images))
                if len(result)>=limit: break
            if listing_id:
                if not result: raise ListingNotFound()
                return result[0]
            return {'listings':result,'next_cursor':cursor_encode(last.published_at,last.id) if last and processed<len(rows) else None}
        return self._transaction(operation)

    def categories(self,*,after=None,limit=100):
        def operation(db):
            query=select(Category.id,Category.name,Category.slug).where(Category.is_active.is_(True)).order_by(Category.id).limit(limit+1)
            if after: query=query.where(Category.id>after)
            rows=db.execute(query).all()
            return {'categories':[{'id':r.id,'name':r.name,'slug':r.slug} for r in rows[:limit]],
                    'next_cursor':str(rows[limit-1].id) if len(rows)>limit else None}
        return self._transaction(operation)

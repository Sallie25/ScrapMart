"""Offline listings MVP with real verification guards and isolated photo storage."""
import io
import math
import uuid
from decimal import Decimal
from unittest.mock import Mock
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from PIL import Image

from app.modules.categories.models import Category
from app.modules.listings.models import Listing,ListingImage
from app.modules.vendors.models import Vendor
from app.modules.auth.models import User
from app.infrastructure.storage.listing_photos import ListingPhotoUnavailable,get_listing_photo_storage
from tests.test_verification_review import store as review_store,private_store,onboarding_store,account_store,login_store,http_store,encoded_password,approved
from tests.test_vendor_account import issue
from tests.test_buyer_login_http import HEADERS
from tests.review_support import prepare_case

OWN='/api/v1/vendor/listings'
PUBLIC='/api/v1/listings'


class PublicPhotos:
    def __init__(self): self.objects={}
    def put(self,key,content):
        assert key.startswith('listings/')
        self.objects[key]=content
    def exists(self,key): return key in self.objects
    def public_url(self,key): return 'https://photos.example.test/'+key
    def delete(self,key): self.objects.pop(key,None)


@pytest.fixture
def store(review_store,monkeypatch):
    engine=review_store.engine
    # Keep production metadata unchanged: SQLite lacks deferred UNIQUE.
    metadata=sa.MetaData()
    for model in (User,Vendor,Category,Listing,ListingImage):
        table=model.__table__.to_metadata(metadata)
        for constraint in table.constraints:
            if isinstance(constraint,sa.UniqueConstraint): constraint.deferrable=None; constraint.initially=None
    metadata.create_all(engine,tables=[metadata.tables[n] for n in ('categories','listings','listing_images')])
    with engine.connect() as db: db.connection.driver_connection.create_function('trunc',1,math.trunc)
    review_store.photos=PublicPhotos()
    monkeypatch.setattr('app.api.v1.marketplace.get_engine',lambda:engine)
    monkeypatch.setattr('app.modules.listings.service.get_listing_photo_storage',lambda settings:review_store.photos)
    approved(review_store)
    with Session(engine) as db,db.begin():
        category=Category(id=uuid.uuid4(),name='Metal',slug='metal')
        other=Category(id=uuid.uuid4(),name='Plastic',slug='plastic')
        inactive=Category(id=uuid.uuid4(),name='Old category',slug='old',is_active=False)
        db.add_all([category,other,inactive])
        review_store.category=category.id; review_store.other_category=other.id; review_store.inactive_category=inactive.id
    return review_store


def payload(store,**changes):
    return {'title':'Aluminium scrap','category_id':str(store.category),'price':'1000.50',
        'description':'Clean reusable metal scrap','condition':'used','quantity':'2.000','quantity_unit':'kilograms',
        'location_summary':'Public Ikeja','lga':'Ikeja','area':'Industrial zone',
        'latitude':'6.601800','longitude':'3.351500','location_visibility':'approximate',**changes}


def headers(store,token=None): return {**HEADERS,'Authorization':'Bearer '+(token or store.owner_access)}


def create(store,body=None):
    return store.client.post(OWN,json=payload(store) if body is None else body,headers=headers(store))


def photo_bytes():
    output=io.BytesIO(); Image.new('RGB',(20,20),'white').save(output,format='PNG'); return output.getvalue()


def upload(store,key,content=None):
    return store.client.post(OWN+f'/{key}/photos?public_consent=true',content=photo_bytes() if content is None else content,
        headers={**headers(store),'Content-Type':'image/png'})


def action(store,key,name,body=None):
    return store.client.post(OWN+f'/{key}/{name}',json=({'public_location_consent':True} if name=='publish' else {}) if body is None else body,headers=headers(store))


def active(store,**changes):
    response=create(store,payload(store,**changes)); assert response.status_code==201,response.text
    key=response.json()['id']; assert upload(store,key).status_code==201
    response=action(store,key,'publish'); assert response.status_code==200,response.text
    return key,response


def test_create_edit_publish_safe_ngn_and_public_projection(store):
    response=create(store); assert response.status_code==201,response.text
    row=response.json(); key=row['id']
    assert row['status']=='draft' and row['price']=='1000.50' and row['currency']=='NGN'
    assert row['latitude']=='6.600000' and row['longitude']=='3.350000'
    assert store.client.get(PUBLIC+f'/{key}').status_code==404
    edit=store.client.patch(OWN+f'/{key}',json={'price':'999.99','title':'  Updated   Aluminium  '},headers=headers(store))
    assert edit.status_code==200 and edit.json()['price']=='999.99' and edit.json()['title']=='Updated Aluminium'
    assert upload(store,key).status_code==201
    published=action(store,key,'publish'); assert published.status_code==200,published.text
    public=store.client.get(PUBLIC+f'/{key}')
    assert public.status_code==200
    assert public.json()['vendor']=={'business_name':'Shop','shop_location':'Public Ikeja','verified':True}
    for secret in ('Private address','identity_document','approval_review','verified_at','phone_number','password','evidence_revision','reviewer_id','object_key'):
        assert secret not in public.text
    assert public.headers['cache-control']=='no-store'
    assert store.client.get(OWN,headers=headers(store)).json()['listings'][0]['id']==key
    assert store.client.get(OWN+f'/{key}',headers=headers(store)).status_code==200


@pytest.mark.parametrize('status',['pending','rejected','suspended'])
def test_nonapproved_cannot_manage_listings(store,status):
    key,_=active(store)
    with Session(store.engine) as db,db.begin(): db.get(Vendor,store.review.vendor_id).verification_status=status
    assert create(store).status_code==403
    assert store.client.patch(OWN+f'/{key}',json={'title':'Changed'},headers=headers(store)).status_code==403
    assert action(store,key,'pause').status_code==403
    assert store.client.get(OWN,headers=headers(store)).status_code==403
    assert store.client.get(PUBLIC).json()['listings']==[]
    assert store.client.get(PUBLIC+f'/{key}').status_code==404


@pytest.mark.parametrize('invalid',['phone','shop','document','approval'])
def test_invalid_evidence_hides_public_and_denies_selling(store,invalid):
    key,_=active(store)
    with Session(store.engine) as db,db.begin():
        if invalid=='phone': db.get(User,store.review.owner.user_id).phone_number='+2348099999999'
        if invalid=='shop': db.get(Vendor,store.review.vendor_id).shop_address='Changed private address'
        if invalid=='approval': db.get(Vendor,store.review.vendor_id).approval_review_id=None
    if invalid=='document': store.storage.objects.clear()
    assert create(store).status_code==403
    assert store.client.get(PUBLIC).json()['listings']==[]
    assert store.client.get(PUBLIC+f'/{key}').status_code==404


def test_cross_vendor_ownership_is_hidden(store,monkeypatch):
    key,_=active(store)
    token,claims=issue(store,'missing'); prepare_case(store,claims,monkeypatch,approve=True)
    assert store.client.get(OWN+f'/{key}',headers=headers(store,token)).status_code==404
    assert store.client.patch(OWN+f'/{key}',json={'title':'Stolen'},headers=headers(store,token)).status_code==404
    assert store.client.delete(OWN+f'/{key}',headers=headers(store,token)).status_code==404
    assert store.client.get(OWN,headers=headers(store,token)).json()['listings']==[]


def test_lifecycle_draft_inactive_sold_removed_and_archive_retains_record(store):
    key,_=active(store)
    assert action(store,key,'pause').json()['status']=='inactive'
    assert store.client.get(PUBLIC).json()['listings']==[]
    assert action(store,key,'publish').json()['status']=='active'
    assert action(store,key,'sold').json()['status']=='sold'
    assert store.client.get(PUBLIC+f'/{key}').status_code==404
    assert action(store,key,'publish').status_code==409
    assert store.client.patch(OWN+f'/{key}',json={'title':'Changed sold'},headers=headers(store)).status_code==409
    assert store.client.delete(OWN+f'/{key}',headers=headers(store)).status_code==204
    assert store.client.delete(OWN+f'/{key}',headers=headers(store)).status_code==204
    with Session(store.engine) as db:
        assert db.get(Listing,uuid.UUID(key)).status=='removed'
        assert db.scalar(sa.select(sa.func.count()).select_from(ListingImage))==1


def test_invalid_transitions_and_minimum_publish_information(store):
    response=create(store,{'title':'Draft only'}); assert response.status_code==201
    key=response.json()['id']
    assert action(store,key,'pause').status_code==409
    assert action(store,key,'sold').status_code==409
    assert action(store,key,'publish').status_code==422
    key=create(store).json()['id']
    assert action(store,key,'publish').status_code==409
    assert upload(store,key).status_code==201
    assert action(store,key,'publish',{}).status_code==422
    assert action(store,key,'publish',{'public_location_consent':1}).status_code==422
    assert action(store,key,'publish').status_code==200
    assert action(store,key,'publish').status_code==409
    assert store.client.patch(OWN+f'/{key}',json={'location_summary':'New public place'},headers=headers(store)).status_code==422
    assert store.client.patch(OWN+f'/{key}',json={'location_summary':'New public place','public_location_consent':True},headers=headers(store)).status_code==200


@pytest.mark.parametrize('changes',[{'price':'-1'},{'price':'1.001'},{'price':1.25},{'price':'NaN'},
    {'price':'1000000000000'},{'quantity':'0'},{'quantity':'1.0001'},{'quantity':'1.5','quantity_unit':'pieces'},
    {'category_id':'bad'},{'condition':'new'},{'status':'active'},{'vendor_id':'attacker'},
    {'currency':'USD'},{'title':' '},{'latitude':None},{'directions_allowed':True}])
def test_invalid_fields_and_mass_assignment(store,changes):
    response=create(store,payload(store,**changes))
    assert response.status_code==422,response.text


def test_nonexistent_inactive_category_and_category_browse(store):
    assert create(store,payload(store,category_id=str(uuid.uuid4()))).status_code==422
    assert create(store,payload(store,category_id=str(store.inactive_category))).status_code==422
    response=store.client.get('/api/v1/categories?limit=1'); assert response.status_code==200
    first=response.json(); assert len(first['categories'])==1 and first['next_cursor']
    second=store.client.get('/api/v1/categories',params={'after':first['next_cursor']}).json()
    assert len(second['categories'])==1
    assert {first['categories'][0]['slug'],second['categories'][0]['slug']}=={'metal','plastic'}


def test_search_filters_literal_wildcards_recent_sort_and_pagination(store):
    first,_=active(store,title='Aluminium pieces',price='10.25')
    second,_=active(store,title='Plastic drums',category_id=str(store.other_category),price='30.50',condition='damaged',description='Blue recycling containers')
    third,_=active(store,title='Copper cable',price='20.00',location_summary='Public Yaba',lga='Yaba')
    def ids(**filters):
        response=store.client.get(PUBLIC,params=filters); assert response.status_code==200,response.text
        return [row['id'] for row in response.json()['listings']]
    assert ids(q='RECYCLING')==[second]
    assert ids(category_id=str(store.category),min_price='15.00',max_price='25.00')==[third]
    assert ids(location='IKEJA',condition='damaged')==[second]
    assert ids(q='%')==[]
    assert set(ids(verified_only='false'))=={first,second,third}
    seen=[]; cursor=None
    for _ in range(4):
        response=store.client.get(PUBLIC,params={'limit':1,**({'cursor':cursor} if cursor else {})}).json()
        seen.extend(row['id'] for row in response['listings']); cursor=response['next_cursor']
        if not cursor: break
    assert len(seen)==3 and len(set(seen))==3
    assert seen==ids()
    assert store.client.get(PUBLIC,params={'limit':21}).status_code==422
    assert store.client.get(PUBLIC,params={'cursor':'bad-cursor'}).status_code==422
    assert store.client.get(PUBLIC,params={'min_price':'30','max_price':'10'}).status_code==422


def test_photo_validation_rollback_provider_blocker_and_separate_namespace(store,monkeypatch):
    key=create(store).json()['id']
    assert upload(store,key,b'<svg/>').status_code==422
    assert upload(store,key,b'x'*(3*1024*1024+1)).status_code==413
    assert upload(store,key).status_code==201
    assert len(store.photos.objects)==1 and all(k.startswith('listings/') for k in store.photos.objects)
    assert 'a'*64 not in store.photos.objects
    existing=set(store.photos.objects)
    def failure(connection,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO listing_images'): raise sa.exc.SQLAlchemyError('private database detail')
    sa.event.listen(store.engine,'before_cursor_execute',failure)
    try: response=upload(store,key)
    finally: sa.event.remove(store.engine,'before_cursor_execute',failure)
    assert response.status_code==503 and set(store.photos.objects)==existing
    monkeypatch.setattr('app.modules.listings.service.get_listing_photo_storage',get_listing_photo_storage)
    assert upload(store,key).status_code==503
    assert action(store,key,'publish').status_code==503


def test_five_photo_limit_active_photo_edit_restrictions_and_removal(store):
    key=create(store).json()['id']; images=[]
    for _ in range(5):
        response=upload(store,key); assert response.status_code==201
        images.append(response.json()['id'])
    assert upload(store,key).status_code==409 and len(store.photos.objects)==5
    assert action(store,key,'publish').status_code==200
    assert upload(store,key).status_code==409
    assert store.client.delete(OWN+f'/{key}/photos/{images[0]}',headers=headers(store)).status_code==409
    assert action(store,key,'pause').status_code==200
    assert store.client.delete(OWN+f'/{key}/photos/{images[0]}',headers=headers(store)).status_code==204
    assert len(store.photos.objects)==4


def test_transaction_rollback_and_security_guards(store):
    response=create(store); key=response.json()['id']
    def fail(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE listings'): raise sa.exc.SQLAlchemyError('private listing detail')
    sa.event.listen(store.engine,'before_cursor_execute',fail)
    try: response=store.client.patch(OWN+f'/{key}',json={'title':'Changed'},headers=headers(store))
    finally: sa.event.remove(store.engine,'before_cursor_execute',fail)
    assert response.status_code==503 and 'private listing detail' not in response.text
    assert store.client.get(OWN+f'/{key}',headers=headers(store)).json()['title']=='Aluminium scrap'
    assert store.client.post(OWN,json=payload(store)).status_code==403
    assert store.client.post(OWN,json=payload(store),headers=HEADERS).status_code==401
    assert store.client.post(OWN,content='x'*16385,headers=HEADERS).status_code==413
    assert store.client.get(OWN).status_code==401
    assert store.client.options(OWN+f'/{key}',headers={'Origin':HEADERS['Origin'],'Access-Control-Request-Method':'DELETE','Access-Control-Request-Headers':'Authorization, X-ScrapMart-CSRF'}).status_code==200


def test_listing_resource_wait_rechecks_jwt_expiry_before_write(store):
    from datetime import datetime,timezone,timedelta
    from app.modules.listings.service import MarketplaceService
    from app.modules.listings.schemas import ListingPatch
    from app.modules.auth.session_service import SessionAuthenticationError
    key=create(store).json()['id']
    claims=store.review.owner
    moments=iter([datetime.now(timezone.utc),datetime.now(timezone.utc),claims.expires_at+timedelta(seconds=1)])
    service=MarketplaceService(store.engine,settings=store.settings,clock=lambda:next(moments))
    with pytest.raises(SessionAuthenticationError):
        service.edit(claims,uuid.UUID(key),ListingPatch(title='Too late'))
    with Session(store.engine) as db: assert db.get(Listing,uuid.UUID(key)).title=='Aluminium scrap'


def test_pause_archive_dont_require_public_photo_delivery(store,monkeypatch):
    key,_=active(store)
    monkeypatch.setattr('app.modules.listings.service.get_listing_photo_storage',get_listing_photo_storage)
    assert action(store,key,'pause').status_code==200
    assert store.client.delete(OWN+f'/{key}',headers=headers(store)).status_code==204


def test_missing_photo_inactive_category_and_corrupt_evidence_hide_public(store):
    key,_=active(store)
    store.photos.objects.clear()
    assert store.client.get(PUBLIC).json()['listings']==[]
    assert store.client.get(PUBLIC+f'/{key}').status_code==404
    assert action(store,key,'pause').status_code==200
    assert upload(store,key).status_code==201
    assert action(store,key,'publish').status_code==200
    with Session(store.engine) as db,db.begin(): db.get(Category,store.category).is_active=False
    assert store.client.get(PUBLIC).json()['listings']==[]
    with Session(store.engine) as db,db.begin(): db.get(Category,store.category).is_active=True
    store.storage.objects['a'*64]=b'corrupt private evidence'
    assert store.client.get(PUBLIC).json()['listings']==[]
    assert create(store).status_code==403


def test_photo_failure_and_invalid_public_url_never_commit_metadata(store,monkeypatch):
    key=create(store).json()['id']
    original_put=store.photos.put
    monkeypatch.setattr(store.photos,'put',Mock(side_effect=OSError('private backend detail')))
    response=upload(store,key)
    assert response.status_code==503 and 'private backend detail' not in response.text
    monkeypatch.setattr(store.photos,'put',original_put)
    monkeypatch.setattr(store.photos,'public_url',lambda key:'javascript:bad')
    assert upload(store,key).status_code==503 and not store.photos.objects
    with Session(store.engine) as db: assert db.scalar(sa.select(sa.func.count()).select_from(ListingImage))==0


def test_invalid_sessions_and_buyer_only_cannot_sell(store):
    from app.modules.auth.session_models import AuthSession
    from datetime import datetime,timezone
    token,_=issue(store,'legacy')
    assert store.client.post(OWN,json=payload(store),headers=headers(store,token)).status_code==403
    with Session(store.engine) as db,db.begin():
        db.get(AuthSession,store.review.owner.session_id).revoked_at=datetime.now(timezone.utc)
    assert create(store).status_code==401
    assert store.client.get(OWN,headers=headers(store)).status_code==401

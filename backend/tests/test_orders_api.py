"""Offline COD orders: ownership, immutable snapshots, stock serialization and lifecycle."""
import importlib.util
import io
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.modules.orders.models import Order,OrderItem
from app.modules.orders.service import OrderService,OrderConflict
from app.modules.orders.schemas import PlaceOrderRequest
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession
from app.modules.auth.session_service import SessionService,SessionAuthenticationError
from app.modules.auth.security import create_access_token,verify_access_token
from app.modules.buyers.models import BuyerProfile
from app.modules.listings.models import Listing
from app.modules.vendors.models import Vendor
from tests.test_marketplace_api import store as marketplace_store,review_store,private_store,onboarding_store,account_store,login_store,http_store,encoded_password,active,headers,OWN,PUBLIC
from tests.test_vendor_account import issue
from tests.test_buyer_login_http import HEADERS
from tests.review_support import prepare_case

BUYER='/api/v1/buyer/orders'
VENDOR='/api/v1/vendor/orders'


def migration():
    path=Path(__file__).parents[1]/'alembic/versions/a06d8f2345bc_add_pay_on_delivery_orders.py'
    spec=importlib.util.spec_from_file_location('orders_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(marketplace_store,monkeypatch):
    monkeypatch.setattr('app.api.v1.orders.get_engine',lambda:marketplace_store.engine)
    token,claims=issue(marketplace_store,'legacy')
    marketplace_store.buyer_token=token;marketplace_store.buyer_claims=claims
    with marketplace_store.engine.begin() as connection,Operations.context(MigrationContext.configure(connection)):
        migration().install_guards()
    return marketplace_store


def buyer_headers(store,token=None): return {**HEADERS,'Authorization':'Bearer '+(token or store.buyer_token)}


def place(store,listing_id,quantity='1',request_id=None,token=None,**changes):
    return store.client.post(BUYER,json={'listing_id':listing_id,'quantity':quantity,'request_id':request_id or str(uuid.uuid4()),**changes},headers=buyer_headers(store,token))


def buyer_action(store,order_id,action,token=None):
    return store.client.post(BUYER+f'/{order_id}/{action}',json={},headers=buyer_headers(store,token))


def vendor_action(store,order_id,action,token=None):
    return store.client.post(VENDOR+f'/{order_id}/{action}',json={},headers=headers(store,token))


def stock(store,**changes): return active(store,price_type='per_unit',**changes)[0]


def test_place_snapshot_idempotency_and_no_client_money(store):
    listing=stock(store)
    request_id=str(uuid.uuid4())
    response=place(store,listing,'1.500',request_id)
    assert response.status_code==201,response.text
    order=response.json()
    assert order['status']=='pending' and order['total_amount']=='1500.75'
    assert order['payment_method']=='pay_on_delivery' and order['currency']=='NGN'
    assert order['item']=={'listing_id':listing,'title':'Aluminium scrap','quantity':'1.500','quantity_unit':'kilograms','listing_price':'1000.50','price_type':'per_unit','line_total':'1500.75'}
    for field in ('payment_status','paid_at','buyer_profile_id','phone_number','identity_document','evidence_revision','password'):
        assert field not in response.text
    assert response.headers['cache-control']=='no-store'
    changed=store.client.patch(OWN+f'/{listing}',json={'price':'2000.00','title':'New title'},headers=headers(store))
    assert changed.status_code==200
    retry=place(store,listing,'1.500',request_id)
    assert retry.status_code==201 and retry.json()['id']==order['id']
    assert retry.json()['item']['listing_price']=='1000.50' and retry.json()['item']['title']=='Aluminium scrap'
    assert place(store,listing,'1.000',request_id).status_code==409
    assert store.client.get(BUYER+f"/{order['id']}",headers=buyer_headers(store)).json()['total_amount']=='1500.75'
    with Session(store.engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Order))==1
        assert db.scalar(sa.select(sa.func.count()).select_from(OrderItem))==1


def test_lifecycle_only_buyer_confirms_receipt_and_never_payment(store):
    listing=stock(store);order=place(store,listing).json()['id']
    assert buyer_action(store,order,'complete').status_code==409
    assert vendor_action(store,order,'deliver').status_code==409
    assert vendor_action(store,order,'accept').json()['status']=='accepted'
    assert vendor_action(store,order,'accept').status_code==409
    assert vendor_action(store,order,'prepare').json()['status']=='preparing'
    assert buyer_action(store,order,'cancel').status_code==409
    delivered=vendor_action(store,order,'deliver')
    assert delivered.status_code==200 and delivered.json()['status']=='delivered'
    assert delivered.json()['delivered_at'] and delivered.json()['completed_at'] is None
    assert vendor_action(store,order,'complete').status_code==404
    completed=buyer_action(store,order,'complete')
    assert completed.status_code==200 and completed.json()['status']=='completed'
    assert completed.json()['completed_at'] and 'payment_status' not in completed.json()
    assert buyer_action(store,order,'complete').status_code==409
    assert vendor_action(store,order,'reject').status_code==409


@pytest.mark.parametrize('action',['cancel','reject','cancel_after_accept'])
def test_cancellation_rejection_release_inventory_once(store,action):
    listing=stock(store)
    order=place(store,listing,'2').json()['id']
    assert store.client.get(PUBLIC+f'/{listing}').status_code==404
    assert place(store,listing).status_code==409
    if action=='cancel_after_accept':
        assert vendor_action(store,order,'accept').status_code==200
        result=buyer_action(store,order,'cancel');repeat=buyer_action(store,order,'cancel')
    elif action=='cancel': result=buyer_action(store,order,'cancel');repeat=buyer_action(store,order,'cancel')
    else: result=vendor_action(store,order,'reject');repeat=vendor_action(store,order,'reject')
    assert result.status_code==200 and repeat.status_code==409
    assert store.client.get(PUBLIC+f'/{listing}').json()['available_quantity']=='2.000'
    assert place(store,listing,'2').status_code==201


@pytest.mark.parametrize('status_action',['pause','sold','archive'])
def test_unavailable_listing_cannot_receive_new_orders(store,status_action):
    listing=stock(store)
    if status_action=='archive': response=store.client.delete(OWN+f'/{listing}',headers=headers(store))
    else: response=store.client.post(OWN+f'/{listing}/{status_action}',json={},headers=headers(store))
    assert response.status_code in (200,204)
    assert place(store,listing).status_code==409


def test_order_history_survives_archive_and_price_change(store):
    listing=stock(store);order=place(store,listing).json()['id']
    assert store.client.delete(OWN+f'/{listing}',headers=headers(store)).status_code==204
    assert store.client.get(BUYER+f'/{order}',headers=buyer_headers(store)).json()['item']['title']=='Aluminium scrap'
    for action in ('accept','prepare','deliver'): assert vendor_action(store,order,action).status_code==200
    assert buyer_action(store,order,'complete').status_code==200
    with pytest.raises(sa.exc.IntegrityError),store.engine.begin() as db:
        db.execute(sa.delete(Listing).where(Listing.id==uuid.UUID(listing)))


@pytest.mark.parametrize('quantity',['0','-1','1.0001','NaN',None,1.5])
def test_invalid_quantities(store,quantity):
    listing=stock(store)
    assert place(store,listing,quantity).status_code==422


def test_pieces_lot_price_rounding_and_minimum_charge(store):
    listing=stock(store,quantity_unit='pieces')
    assert place(store,listing,'1.5').status_code==422
    assert place(store,listing,'3').status_code==409
    lot,_=active(store,price_type='total',price='1000.50')
    assert place(store,lot,'1').status_code==422
    assert place(store,lot,'2').json()['total_amount']=='1000.50'
    tiny=stock(store,price='1.00')
    assert place(store,tiny,'0.005').json()['total_amount']=='0.01'
    below=stock(store,price='0.01')
    assert place(store,below,'0.001').status_code==422


def test_buyer_profile_vendor_ownership_and_self_order_isolation(store,monkeypatch):
    listing=stock(store);order=place(store,listing).json()['id']
    assert place(store,listing,token=store.owner_access).status_code==409
    only_vendor,other_claims=issue(store,'missing')
    assert place(store,listing,token=only_vendor).status_code==401
    assert store.client.get(BUYER,headers=buyer_headers(store,only_vendor)).status_code==401
    assert vendor_action(store,order,'accept',store.buyer_token).status_code==403
    # A second approved Vendor is still not the owner of this order.
    prepare_case(store,other_claims,monkeypatch,approve=True)
    assert vendor_action(store,order,'accept',only_vendor).status_code==404
    assert store.client.get(VENDOR+f'/{order}',headers=headers(store,only_vendor)).status_code==404
    # The Seller's Buyer profile cannot read another Buyer's receipt.
    assert store.client.get(BUYER+f'/{order}',headers=buyer_headers(store,store.owner_access)).status_code==404
    assert buyer_action(store,order,'cancel',store.owner_access).status_code==404


@pytest.mark.parametrize('state',['suspended','rejected','pending','invalid_phone','invalid_document'])
def test_vendor_ineligibility_blocks_new_orders_and_transitions_but_not_buyer_history(store,state):
    listing=stock(store);order=place(store,listing).json()['id']
    with Session(store.engine) as db,db.begin():
        if state in ('suspended','rejected','pending'): db.get(Vendor,store.review.vendor_id).verification_status=state
        if state=='invalid_phone': db.get(User,store.review.owner.user_id).phone_number='+2348099999999'
    if state=='invalid_document': store.storage.objects.clear()
    assert place(store,listing).status_code==409
    assert vendor_action(store,order,'accept').status_code==403
    assert store.client.get(BUYER+f'/{order}',headers=buyer_headers(store)).status_code==200
    assert store.client.get(VENDOR+f'/{order}',headers=headers(store)).status_code==200
    assert buyer_action(store,order,'cancel').status_code==200


def test_stock_floor_and_unit_changes_cannot_bypass_reservations(store):
    listing=stock(store);order=place(store,listing,'1.500').json()['id']
    assert store.client.get(PUBLIC+f'/{listing}').json()['available_quantity']=='0.500'
    assert store.client.patch(OWN+f'/{listing}',json={'quantity':'1'},headers=headers(store)).status_code==422
    assert store.client.patch(OWN+f'/{listing}',json={'quantity_unit':'tonnes'},headers=headers(store)).status_code==422
    assert store.client.patch(OWN+f'/{listing}',json={'price_type':'total'},headers=headers(store)).status_code==422
    assert store.client.patch(OWN+f'/{listing}',json={'quantity':'3'},headers=headers(store)).status_code==200
    assert store.client.get(PUBLIC+f'/{listing}').json()['available_quantity']=='1.500'
    for action in ('accept','prepare','deliver'): assert vendor_action(store,order,action).status_code==200
    assert buyer_action(store,order,'complete').status_code==200
    assert store.client.get(PUBLIC+f'/{listing}').json()['available_quantity']=='1.500'


def new_buyer(store):
    user_id=uuid.uuid4();now=datetime.now(timezone.utc)
    with Session(store.engine) as db,db.begin():
        db.add(User(id=user_id,email=f'{user_id.hex}@example.test',password_hash='test-only-no-login',full_name='Second Buyer'))
        db.flush();db.add(BuyerProfile(user_id=user_id,created_at=now,signup_completed_at=now))
    credentials=SessionService(store.engine,settings=store.settings).create_session(user_id)
    token=create_access_token(user_id,credentials.session_id,settings=store.settings)
    return token,verify_access_token(token,settings=store.settings)


def test_concurrent_orders_cannot_oversell(store):
    listing=stock(store)
    _,second=new_buyer(store)
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    @sa.event.listens_for(engine,'connect')
    def setup(connection,_):
        connection.execute('PRAGMA foreign_keys=ON');connection.create_function('trunc',1,math.trunc)
    barrier=threading.Barrier(2);local=threading.local()
    def sync(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE users') and not getattr(local,'started',False): local.started=True;barrier.wait(timeout=10)
    sa.event.listen(engine,'before_cursor_execute',sync)
    def order(claims):
        try:
            OrderService(engine,settings=store.settings).place(claims,PlaceOrderRequest(listing_id=uuid.UUID(listing),request_id=uuid.uuid4(),quantity='2'))
            return 'placed'
        except OrderConflict: return 'conflict'
    try:
        with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(order,[store.buyer_claims,second]))==['conflict','placed']
    finally: sa.event.remove(engine,'before_cursor_execute',sync);engine.dispose()
    with Session(store.engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Order))==1
        assert db.scalar(sa.select(sa.func.sum(OrderItem.quantity)))==Decimal('2.000')


@pytest.mark.parametrize('failure',['item_insert','commit'])
def test_placement_rollback_does_not_reserve_or_send_payment(store,failure):
    listing=stock(store)
    def fail_sql(connection,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO order_items'): raise sa.exc.SQLAlchemyError('private database detail')
    def fail_commit(connection): raise sa.exc.SQLAlchemyError('private commit detail')
    event='commit' if failure=='commit' else 'before_cursor_execute';handler=fail_commit if failure=='commit' else fail_sql
    sa.event.listen(store.engine,event,handler)
    try: response=place(store,listing)
    finally: sa.event.remove(store.engine,event,handler)
    assert response.status_code==503 and 'private' not in response.text
    with Session(store.engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Order))==0
        assert db.scalar(sa.select(sa.func.count()).select_from(OrderItem))==0
    assert store.client.get(PUBLIC+f'/{listing}').json()['available_quantity']=='2.000'


def test_snapshot_db_guards_and_invalid_transitions(store):
    listing=stock(store);order=place(store,listing).json()['id']
    statements=[sa.update(Order).values(total_amount=Decimal('1')),sa.update(OrderItem).values(listing_price=Decimal('1')),
                sa.update(Order).values(status='completed',completed_at=datetime.now(timezone.utc))]
    for statement in statements:
        with pytest.raises(sa.exc.DBAPIError),store.engine.begin() as db: db.execute(statement)
    assert store.client.get(BUYER+f'/{order}',headers=buyer_headers(store)).json()['total_amount']=='1000.50'


def test_pagination_input_guards_and_price_injection(store):
    listing=stock(store,quantity='5')
    for _ in range(3): assert place(store,listing).status_code==201
    page=store.client.get(BUYER+'?limit=2',headers=buyer_headers(store)).json()
    assert len(page['orders'])==2 and page['next_cursor']
    tail=store.client.get(BUYER,params={'limit':2,'cursor':page['next_cursor']},headers=buyer_headers(store)).json()
    assert len(tail['orders'])==1 and tail['next_cursor'] is None
    assert store.client.get(VENDOR,headers=headers(store)).status_code==200
    assert place(store,listing,price='0',vendor_id=str(store.review.vendor_id),payment_status='paid').status_code==422
    assert store.client.post(BUYER,json={}).status_code==403
    assert store.client.post(BUYER,content='x'*16385,headers=HEADERS).status_code==413
    assert store.client.get(BUYER).status_code==401
    assert store.client.get(BUYER+'?limit=51',headers=buyer_headers(store)).status_code==422


def test_order_migration_offline_and_roundtrip():
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})):
        migration().upgrade();migration().downgrade()
    sql=output.getvalue()
    assert 'NUMERIC(26, 2)' in sql and 'guard_order_agreement' in sql and 'immutable_order_item' in sql
    assert 'pay_on_delivery' in sql and 'INSERT INTO' not in sql
    assert migration().down_revision=='f95c7e1234ab'
    engine=sa.create_engine('sqlite://')
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE buyer_profiles (id CHAR(32) PRIMARY KEY)')
        db.exec_driver_sql('CREATE TABLE vendors (id CHAR(32) PRIMARY KEY)')
        db.exec_driver_sql('CREATE TABLE listings (id CHAR(32) PRIMARY KEY, title TEXT)')
        db.exec_driver_sql("INSERT INTO listings VALUES ('old', 'Historical listing')")
        db.connection.driver_connection.create_function('trunc',1,math.trunc)
        with Operations.context(MigrationContext.configure(db)):
            migration().upgrade()
            assert db.exec_driver_sql('SELECT * FROM listings').one()==('old','Historical listing')
            assert db.exec_driver_sql('SELECT count(*) FROM orders').scalar()==0
            migration().downgrade()
            assert db.exec_driver_sql('SELECT * FROM listings').one()==('old','Historical listing')
    engine.dispose()


def test_whole_lot_quantity_cannot_change_while_committed(store):
    listing,_=active(store,price_type='total')
    order=place(store,listing,'2').json()['id']
    assert store.client.patch(OWN+f'/{listing}',json={'quantity':'3'},headers=headers(store)).status_code==422
    assert buyer_action(store,order,'cancel').status_code==200
    assert store.client.patch(OWN+f'/{listing}',json={'quantity':'3'},headers=headers(store)).status_code==200
    assert place(store,listing,'3').status_code==201


def test_concurrent_same_request_creates_only_one_order(store):
    listing=stock(store);request_id=uuid.uuid4()
    request=PlaceOrderRequest(listing_id=uuid.UUID(listing),quantity='1',request_id=request_id)
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    @sa.event.listens_for(engine,'connect')
    def setup(connection,_):
        connection.execute('PRAGMA foreign_keys=ON');connection.create_function('trunc',1,math.trunc)
    barrier=threading.Barrier(2);local=threading.local()
    def sync(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE users') and not getattr(local,'started',False): local.started=True;barrier.wait(timeout=10)
    sa.event.listen(engine,'before_cursor_execute',sync)
    try:
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(OrderService(engine,settings=store.settings).place,store.buyer_claims,request) for _ in range(2)]
            result=[future.result(timeout=30)['id'] for future in futures]
        assert result[0]==result[1]
    finally: sa.event.remove(engine,'before_cursor_execute',sync);engine.dispose()
    with Session(store.engine) as db: assert db.scalar(sa.select(sa.func.count()).select_from(Order))==1


def test_buyer_receipt_confirmation_survives_seller_suspension(store):
    listing=stock(store);order=place(store,listing).json()['id']
    for action in ('accept','prepare','deliver'): assert vendor_action(store,order,action).status_code==200
    with Session(store.engine) as db,db.begin(): db.get(Vendor,store.review.vendor_id).verification_status='suspended'
    assert buyer_action(store,order,'complete').status_code==200
    assert vendor_action(store,order,'deliver').status_code==403


def test_transition_rollback_does_not_release_stock(store):
    listing=stock(store);order=place(store,listing,'2').json()['id']
    def failure(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE orders'): raise sa.exc.SQLAlchemyError('private transition detail')
    sa.event.listen(store.engine,'before_cursor_execute',failure)
    try: response=buyer_action(store,order,'cancel')
    finally: sa.event.remove(store.engine,'before_cursor_execute',failure)
    assert response.status_code==503 and 'private transition detail' not in response.text
    assert place(store,listing).status_code==409
    assert store.client.get(BUYER+f'/{order}',headers=buyer_headers(store)).json()['status']=='pending'
    assert buyer_action(store,order,'cancel').status_code==200


def test_expired_revoked_buyer_session_and_post_lock_expiry(store):
    from app.modules.auth.security import create_access_token
    listing=stock(store)
    with Session(store.engine) as db,db.begin(): db.get(AuthSession,store.buyer_claims.session_id).revoked_at=datetime.now(timezone.utc)
    assert place(store,listing).status_code==401
    assert store.client.get(BUYER,headers=buyer_headers(store)).status_code==401
    token,claims=issue(store,'legacy')
    times=iter([datetime.now(timezone.utc),claims.expires_at+timedelta(seconds=1)])
    svc=OrderService(store.engine,settings=store.settings,clock=lambda:next(times))
    with pytest.raises(SessionAuthenticationError):
        svc.place(claims,PlaceOrderRequest(listing_id=uuid.UUID(listing),quantity='1',request_id=uuid.uuid4()))
    with Session(store.engine) as db: assert db.scalar(sa.select(sa.func.count()).select_from(Order))==0

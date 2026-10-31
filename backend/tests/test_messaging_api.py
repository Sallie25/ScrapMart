"""Offline participant, persistence, retry and HTTP security regressions."""
import uuid
import json
import threading
import math
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.modules.messaging.models import Conversation, Message
from app.modules.messaging.service import MessagingService
from app.modules.messaging.schemas import StartConversation
from app.modules.auth.session_models import AuthSession
from app.modules.vendors.models import Vendor
from tests.test_orders_api import store as orders_store, marketplace_store, review_store, private_store, onboarding_store, account_store, login_store, http_store, encoded_password, buyer_headers, stock, new_buyer
from tests.test_marketplace_api import headers, OWN
from tests.test_vendor_account import issue
from tests.review_support import prepare_case

ROOT='/api/v1/conversations'


def migration():
    spec=importlib.util.spec_from_file_location('messaging_migration',Path(__file__).parents[1]/'alembic/versions/b17e9a3456cd_add_messaging.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(orders_store, monkeypatch):
    monkeypatch.setattr('app.api.v1.messaging.get_engine',lambda:orders_store.engine)
    Conversation.__table__.create(orders_store.engine)
    Message.__table__.create(orders_store.engine)
    with orders_store.engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        migration().install_guards()
    return orders_store


def start(store, listing=None, token=None, **extra):
    return store.client.post(ROOT,json={'listing_id':listing or stock(store),**extra},headers=buyer_headers(store,token))


def send(store,key,text='Hello 👋',token=None,**extra):
    return store.client.post(ROOT+f'/{key}/messages',content=json.dumps({'content':text,**extra}),headers={**buyer_headers(store,token),'Content-Type':'application/json'})


def test_start_reuse_and_safe_projection(store):
    listing=stock(store);first=start(store,listing)
    assert first.status_code==201,first.text
    assert start(store,listing).json()['id']==first.json()['id']
    assert set(first.json())=={'id','listing_id','created_at','unread_count'}
    assert first.headers['cache-control']=='no-store'
    assert start(store,listing,buyer_id=str(uuid.uuid4())).status_code==422
    assert start(store,listing,store.owner_access).status_code==409
    assert store.client.get(ROOT,headers=headers(store)).json()['conversations'][0]['id']==first.json()['id']


def test_read_unread_and_idempotency(store):
    key=start(store).json()['id'];request_id=str(uuid.uuid4())
    message=send(store,key,request_id=request_id).json()
    assert send(store,key,request_id=request_id).json()==message
    assert send(store,key,'Different',request_id=request_id).status_code==409
    assert store.client.get(ROOT+'/unread',headers=headers(store)).json()=={'unread_count':1}
    assert store.client.get(ROOT+'/unread',headers=buyer_headers(store)).json()=={'unread_count':0}
    url=ROOT+f'/{key}/read'
    assert store.client.post(url,json={'message_id':message['id']},headers=buyer_headers(store)).status_code==404
    read=store.client.post(url,json={'message_id':message['id']},headers=headers(store))
    assert read.status_code==200 and read.json()['read_at']
    assert store.client.post(url,json={'message_id':message['id']},headers=headers(store)).json()==read.json()
    assert store.client.get(ROOT+'/unread',headers=headers(store)).json()=={'unread_count':0}
    reply=send(store,key,'Reply',store.owner_access)
    assert reply.json()['sender']=='vendor'
    assert store.client.get(ROOT,headers=buyer_headers(store)).json()['conversations'][0]['unread_count']==1


@pytest.mark.parametrize('text',['','  \n','x'*4001,'\x00','\ud800',123,None])
def test_invalid_text(store,text):
    key=start(store).json()['id']
    assert send(store,key,text).status_code==422


def test_unicode_ordering_and_pagination(store):
    key=start(store).json()['id'];ids=[]
    for text in ['Ẹ káàrọ̀','你好','<script>alert(1)</script>','👩🏽‍🔧']:
        response=send(store,key,text);assert response.status_code==201;ids.append(response.json()['id'])
    url=ROOT+f'/{key}/messages'
    first=store.client.get(url+'?limit=2',headers=buyer_headers(store)).json()
    second=store.client.get(url,params={'limit':2,'cursor':first['next_cursor']},headers=headers(store)).json()
    assert [m['id'] for m in first['messages']+second['messages']]==list(reversed(ids))
    assert second['next_cursor'] is None
    for query in ['limit=101','limit=0','cursor=invalid','sender_id=1','limit=2&limit=3']:
        assert store.client.get(url+'?'+query,headers=buyer_headers(store)).status_code==422


def test_isolation_spoofing_and_authentication(store,monkeypatch):
    key=start(store).json()['id'];token,claims=new_buyer(store)
    vendor_token,vendor_claims=issue(store,'missing');prepare_case(store,vendor_claims,monkeypatch,approve=True)
    for outsider in [token,vendor_token]:
        assert store.client.get(ROOT+f'/{key}/messages',headers=buyer_headers(store,outsider)).status_code==404
        assert send(store,key,token=outsider).status_code==404
        assert store.client.get(ROOT,headers=buyer_headers(store,outsider)).json()['conversations']==[]
    assert send(store,key,sender_id=str(claims.user_id)).status_code==422
    assert send(store,key,recipient_id=str(uuid.uuid4())).status_code==422
    assert store.client.get(ROOT).status_code==401
    assert store.client.post(ROOT,json={}).status_code==403
    assert store.client.post(ROOT,content='x'*16385,headers=buyer_headers(store)).status_code==413
    with Session(store.engine) as db,db.begin(): db.get(AuthSession,store.buyer_claims.session_id).revoked_at=datetime.now(timezone.utc)
    assert send(store,key).status_code==401
    assert store.client.get(ROOT,headers=buyer_headers(store)).status_code==401


@pytest.mark.parametrize('state',['archive','inactive','sold','suspended','expiry'])
def test_existing_access_survives_listing_and_vendor_changes(store,state):
    listing=stock(store);key=start(store,listing).json()['id'];other=stock(store)
    if state=='archive': assert store.client.delete(OWN+f'/{listing}',headers=headers(store)).status_code==204
    elif state in {'inactive','sold'}:
        action='pause' if state=='inactive' else 'sold'
        assert store.client.post(OWN+f'/{listing}/{action}',json={},headers=headers(store)).status_code==200
    elif state=='suspended':
        with Session(store.engine) as db,db.begin(): db.get(Vendor,store.review.vendor_id).verification_status='suspended'
    else: store.storage.objects.clear()
    assert start(store,listing).json()['id']==key
    assert send(store,key).status_code==201
    assert send(store,key,token=store.owner_access).status_code==201
    assert store.client.get(ROOT+f'/{key}/messages',headers=headers(store)).status_code==200
    if state in {'suspended','expiry'}: assert start(store,other).status_code==403
    else:
        token,_=new_buyer(store)
        assert start(store,listing,token).status_code==409


@pytest.mark.parametrize('failure',['conversation','message','commit'])
def test_rollback(store,failure):
    listing=stock(store)
    key=start(store,listing).json()['id'] if failure!='conversation' else None
    def sql(connection,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO '+('conversations' if failure=='conversation' else 'messages')): raise sa.exc.SQLAlchemyError('secret detail')
    def commit(connection): raise sa.exc.SQLAlchemyError('secret detail')
    event='commit' if failure=='commit' else 'before_cursor_execute';handler=commit if failure=='commit' else sql
    sa.event.listen(store.engine,event,handler)
    try: response=start(store,listing) if failure=='conversation' else send(store,key)
    finally: sa.event.remove(store.engine,event,handler)
    assert response.status_code==503 and 'secret detail' not in response.text
    with Session(store.engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Message))==0
        assert db.scalar(sa.select(sa.func.count()).select_from(Conversation))==(0 if failure=='conversation' else 1)


def test_concurrent_creation(store):
    listing=stock(store);request=StartConversation(listing_id=listing)
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
            futures=[pool.submit(MessagingService(engine,settings=store.settings).start,store.buyer_claims,request) for _ in range(2)]
            assert len({f.result(timeout=30)['id'] for f in futures})==1
    finally: engine.dispose()
    with Session(store.engine) as db: assert db.scalar(sa.select(sa.func.count()).select_from(Conversation))==1


def test_migration_roundtrip_and_postgresql_sql(store):
    import io
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output,'version_table_schema':'messaging_test'})):
        migration().upgrade();migration().downgrade()
    sql=output.getvalue()
    assert 'messaging_test.conversations' in sql and 'guard_conversation' in sql
    assert 'uq_message_request' in sql and 'ON DELETE RESTRICT' in sql
    with store.engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        migration().downgrade()
        migration().upgrade()
        assert db.exec_driver_sql('SELECT count(*) FROM messages').scalar()==0
        assert db.exec_driver_sql('SELECT count(*) FROM listings').scalar()==0


def test_database_participants_and_references(store):
    listing=stock(store);key=start(store,listing).json()['id']
    with pytest.raises(sa.exc.IntegrityError),store.engine.begin() as db:
        db.execute(sa.update(Conversation).values(vendor_id=uuid.uuid4()))
    from app.modules.listings.models import Listing
    with pytest.raises(sa.exc.IntegrityError),store.engine.begin() as db:
        db.execute(sa.delete(Listing).where(Listing.id==uuid.UUID(listing)))


def test_concurrent_message_retry(store):
    from app.modules.messaging.schemas import SendMessage
    key=uuid.UUID(start(store).json()['id'])
    value=SendMessage(content='One delivery',request_id=uuid.uuid4())
    # HTTP fixtures share one connection; concurrency needs independent connections.
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    @sa.event.listens_for(engine,'connect')
    def setup(connection,_): connection.execute('PRAGMA foreign_keys=ON')
    try:
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(MessagingService(engine,settings=store.settings).run,store.buyer_claims,'send',key=key,value=value) for _ in range(2)]
            assert len({f.result(timeout=30)['id'] for f in futures})==1
    finally: engine.dispose()
    with Session(store.engine) as db: assert db.scalar(sa.select(sa.func.count()).select_from(Message))==1


def test_cannot_read_message_from_another_conversation(store):
    first=start(store).json()['id'];second=start(store).json()['id']
    message=send(store,first).json()['id']
    assert store.client.post(ROOT+f'/{second}/read',json={'message_id':message},headers=headers(store)).status_code==404
    assert store.client.get(ROOT+'/unread',headers=headers(store)).json()['unread_count']==1

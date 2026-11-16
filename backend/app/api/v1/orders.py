"""Owned single-listing COD orders; only the Buyer confirms receipt/completion."""
import json
from typing import Annotated
from fastapi import APIRouter,Depends,Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_account import access_claims,invalid_authentication
from app.api.v1.buyer_sessions import session_guard,SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail
from app.api.v1.marketplace import identifier,query_params,page
from app.core.config import Settings,get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.infrastructure.storage.listing_photos import ListingPhotoUnavailable
from app.modules.auth.security import AccessTokenClaims,SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError,SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.orders.schemas import PlaceOrderRequest,EmptyOrderRequest
from app.modules.orders.service import OrderService,OrderNotFound,OrderConflict,InvalidOrder

router=APIRouter(tags=['Pay-on-delivery orders'])
BUYER='/buyer/orders'
VENDOR='/vendor/orders'


def perform(settings,operation):
    try: return operation(OrderService(get_engine(),settings=settings))
    except SessionAuthenticationError: invalid_authentication()
    except VendorPermissionError: fail(403,'order_forbidden','Current approved Vendor evidence is required')
    except OrderNotFound: fail(404,'order_not_found','Order or listing is not available')
    except OrderConflict: fail(409,'order_conflict','Order state or listing availability does not permit this operation')
    except InvalidOrder: fail(422,'validation_error','Invalid order quantity or pricing basis')
    except (SessionPersistenceError,SecurityConfigurationError,SQLAlchemyError,OSError,VerificationInfrastructureUnavailable,ListingPhotoUnavailable):
        fail(503,'order_unavailable','Order operation is temporarily unavailable')


async def order_input(request:Request,_:Annotated[None,Depends(session_guard)]):
    model=PlaceOrderRequest if request.url.path.rstrip('/')=='/api/v1/buyer/orders' else EmptyOrderRequest
    body=await request.body()
    if not body and model is EmptyOrderRequest: return EmptyOrderRequest()
    types=request.headers.getlist('content-type')
    if len(types)!=1 or types[0].split(';',1)[0].strip().lower()!='application/json':
        fail(415,'unsupported_media_type','Use application/json')
    try: return model.model_validate(json.loads(body))
    except (ValidationError,ValueError,UnicodeError,RecursionError):
        fail(422,'validation_error','Invalid order fields')


@router.post(BUYER,status_code=201,openapi_extra={'parameters':SECURITY_PARAMETERS,'requestBody':{'required':True,'content':{'application/json':{'schema':PlaceOrderRequest.model_json_schema()}}}})
def place(value:Annotated[PlaceOrderRequest,Depends(order_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    return perform(settings,lambda service:service.place(claims,value))


def listing(request,claims,settings,*,vendor):
    params=query_params(request,{'limit','cursor'});limit,cursor=page(params,50)
    return perform(settings,lambda service:service.read(claims,vendor=vendor,limit=limit,cursor=cursor))


@router.get(BUYER)
def buyer_orders(request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    return listing(request,claims,settings,vendor=False)


@router.get(VENDOR)
def vendor_orders(request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    return listing(request,claims,settings,vendor=True)


@router.get(BUYER+'/{order_id}')
def buyer_detail(order_id:str,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(order_id)
    return perform(settings,lambda service:service.read(claims,order_id=key))


@router.get(VENDOR+'/{order_id}')
def vendor_detail(order_id:str,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(order_id)
    return perform(settings,lambda service:service.read(claims,vendor=True,order_id=key))


@router.post(BUYER+'/{order_id}/{action}',openapi_extra={'parameters':SECURITY_PARAMETERS})
def buyer_transition(order_id:str,action:str,value:Annotated[EmptyOrderRequest,Depends(order_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    if action not in {'cancel','complete'}: fail(404,'order_not_found','Order operation is not available')
    key=identifier(order_id)
    return perform(settings,lambda service:service.buyer_transition(claims,key,action))


@router.post(VENDOR+'/{order_id}/{action}',openapi_extra={'parameters':SECURITY_PARAMETERS})
def vendor_transition(order_id:str,action:str,value:Annotated[EmptyOrderRequest,Depends(order_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    if action not in {'accept','reject','prepare','deliver'}: fail(404,'order_not_found','Order operation is not available')
    key=identifier(order_id)
    return perform(settings,lambda service:service.vendor_transition(claims,key,action))

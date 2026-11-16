"""Vendor listing ownership/mutations and public live-verified marketplace reads."""
import json
import uuid
from typing import Annotated
from fastapi import APIRouter,Depends,Request,Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from app.api.v1.buyer_account import access_claims,invalid_authentication
from app.api.v1.buyer_sessions import session_guard,SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail
from app.core.config import Settings,get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable,InvalidDocument
from app.infrastructure.storage.listing_photos import ListingPhotoUnavailable
from app.modules.auth.security import AccessTokenClaims,SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError,SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.listings.schemas import ListingCreate,ListingPatch,EmptyRequest,PublishRequest,exact_decimal,normalized
from app.modules.listings.service import MarketplaceService,ListingNotFound,ListingConflict,InvalidListing,cursor_decode

router=APIRouter(tags=['Marketplace'])
VENDOR='/vendor/listings'


def identifier(value):
    try:
        result=uuid.UUID(value)
        if str(result)!=value: raise ValueError()
        return result
    except (ValueError,TypeError,AttributeError):
        fail(422,'validation_error','Invalid resource identifier')


def perform(settings,operation):
    try: return operation(MarketplaceService(get_engine(),settings=settings))
    except SessionAuthenticationError: invalid_authentication()
    except VendorPermissionError: fail(403,'selling_forbidden','Current approved Vendor evidence is required')
    except ListingNotFound: fail(404,'listing_not_found','Listing is not available')
    except ListingConflict: fail(409,'listing_conflict','Listing state or photos do not permit this operation')
    except (InvalidListing,InvalidDocument): fail(422,'validation_error','Invalid listing fields or photo content')
    except (ListingPhotoUnavailable,VerificationInfrastructureUnavailable,SessionPersistenceError,SecurityConfigurationError,SQLAlchemyError,OSError):
        fail(503,'marketplace_unavailable','Marketplace operation is temporarily unavailable')


async def listing_input(request:Request,_:Annotated[None,Depends(session_guard)]):
    path=request.url.path
    model=ListingPatch if request.method=='PATCH' else ListingCreate if path.rstrip('/')=='/api/v1/vendor/listings' and request.method=='POST' else PublishRequest if path.endswith('/publish') else EmptyRequest
    body=await request.body()
    if not body and model is EmptyRequest: return EmptyRequest()
    types=request.headers.getlist('content-type')
    if len(types)!=1 or types[0].split(';',1)[0].strip().lower()!='application/json':
        fail(415,'unsupported_media_type','Use application/json')
    try: return model.model_validate(json.loads(body))
    except (ValidationError,ValueError,UnicodeError,RecursionError):
        fail(422,'validation_error','Invalid listing fields')


def query_params(request,allowed):
    values=request.query_params
    if set(values)-set(allowed) or any(len(values.getlist(key))!=1 for key in values):
        fail(422,'validation_error','Invalid listing filters')
    return values


def page(values,maximum):
    try:
        limit=int(values.get('limit','20'))
        if not 1<=limit<=maximum: raise ValueError()
        return limit,cursor_decode(values.get('cursor'))
    except (ValueError,InvalidListing): fail(422,'validation_error','Invalid pagination')


@router.post(VENDOR,status_code=201,openapi_extra={'parameters':SECURITY_PARAMETERS,'requestBody':{'required':True,'content':{'application/json':{'schema':ListingCreate.model_json_schema()}}}})
def create(value:Annotated[ListingCreate,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    return perform(settings,lambda service:service.create(claims,value))


@router.get(VENDOR)
def own(request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    values=query_params(request,{'limit','cursor','status'}); limit,cursor=page(values,50)
    status=values.get('status')
    if status and status not in {'draft','active','inactive','sold','removed'}: fail(422,'validation_error','Invalid listing status')
    return perform(settings,lambda service:service.own(claims,limit=limit,cursor=cursor,status=status))


@router.get(VENDOR+'/{listing_id}')
def own_detail(listing_id:str,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.own(claims,key))


@router.patch(VENDOR+'/{listing_id}',openapi_extra={'parameters':SECURITY_PARAMETERS,'requestBody':{'required':True,'content':{'application/json':{'schema':ListingPatch.model_json_schema()}}}})
def edit(listing_id:str,value:Annotated[ListingPatch,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.edit(claims,key,value))


@router.post(VENDOR+'/{listing_id}/publish',openapi_extra={'parameters':SECURITY_PARAMETERS,'requestBody':{'required':True,'content':{'application/json':{'schema':PublishRequest.model_json_schema()}}}})
def publish(listing_id:str,value:Annotated[PublishRequest,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.transition(claims,key,'publish',consent=value.public_location_consent))


@router.post(VENDOR+'/{listing_id}/pause',openapi_extra={'parameters':SECURITY_PARAMETERS})
def pause(listing_id:str,value:Annotated[EmptyRequest,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.transition(claims,key,'pause'))


@router.post(VENDOR+'/{listing_id}/sold',openapi_extra={'parameters':SECURITY_PARAMETERS})
def sold(listing_id:str,value:Annotated[EmptyRequest,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.transition(claims,key,'sold'))


@router.delete(VENDOR+'/{listing_id}',status_code=204,response_class=Response,openapi_extra={'parameters':SECURITY_PARAMETERS})
def archive(listing_id:str,value:Annotated[EmptyRequest,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    perform(settings,lambda service:service.transition(claims,key,'archive'))
    return Response(status_code=204,headers={'Cache-Control':'no-store'})


@router.post(VENDOR+'/{listing_id}/photos',status_code=201,dependencies=[Depends(session_guard)],
    openapi_extra={'parameters':SECURITY_PARAMETERS+[{'in':'query','name':'public_consent','required':True,'schema':{'type':'boolean','const':True}}],
                  'requestBody':{'required':True,'content':{'image/jpeg':{'schema':{'type':'string','format':'binary'}},'image/png':{'schema':{'type':'string','format':'binary'}}}}})
async def upload(listing_id:str,request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    values=query_params(request,{'public_consent'})
    if values.get('public_consent')!='true': fail(422,'validation_error','Public product-photo consent is required')
    types=request.headers.getlist('content-type')
    if len(types)!=1 or types[0].split(';',1)[0].strip().lower() not in {'image/jpeg','image/png'}:
        fail(415,'unsupported_media_type','Use image/jpeg or image/png')
    content=await request.body()
    return await run_in_threadpool(perform,settings,lambda service:service.upload_photo(claims,key,content))


@router.delete(VENDOR+'/{listing_id}/photos/{image_id}',status_code=204,response_class=Response,openapi_extra={'parameters':SECURITY_PARAMETERS})
def remove_photo(listing_id:str,image_id:str,value:Annotated[EmptyRequest,Depends(listing_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id); image=identifier(image_id)
    perform(settings,lambda service:service.delete_photo(claims,key,image))
    return Response(status_code=204,headers={'Cache-Control':'no-store'})


@router.get('/listings')
def browse(request:Request,settings:Annotated[Settings,Depends(get_settings)]):
    values=query_params(request,{'limit','cursor','q','category_id','location','condition','min_price','max_price','verified_only','sort'})
    limit,cursor=page(values,20)
    try:
        q=normalized(values.get('q')); location=normalized(values.get('location'))
        if (q and len(q)>100) or (location and len(location)>100): raise ValueError()
        condition=values.get('condition')
        if condition and condition not in {'good_condition','used','faulty','damaged','for_parts'}: raise ValueError()
        if values.get('sort','recent')!='recent' or values.get('verified_only','true') not in {'true','false'}: raise ValueError()
        low=exact_decimal(values.get('min_price'),2,10**12); high=exact_decimal(values.get('max_price'),2,10**12)
        if low is not None and high is not None and low>high: raise ValueError()
    except ValueError: fail(422,'validation_error','Invalid marketplace filters')
    category=identifier(values['category_id']) if 'category_id' in values else None
    return perform(settings,lambda service:service.browse(limit=limit,cursor=cursor,q=q,category=category,location=location,condition=condition,min_price=low,max_price=high))


@router.get('/listings/{listing_id}')
def public_detail(listing_id:str,settings:Annotated[Settings,Depends(get_settings)]):
    key=identifier(listing_id)
    return perform(settings,lambda service:service.browse(listing_id=key))


@router.get('/categories')
def categories(request:Request,settings:Annotated[Settings,Depends(get_settings)]):
    values=query_params(request,{'after','limit'})
    try:
        limit=int(values.get('limit','100'))
        if not 1<=limit<=100: raise ValueError()
    except ValueError: fail(422,'validation_error','Invalid category pagination')
    after=identifier(values['after']) if 'after' in values else None
    return perform(settings,lambda service:service.categories(after=after,limit=limit))

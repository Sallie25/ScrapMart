"""Explicit reviewer permission, case-specific private evidence and safe decisions."""
from dataclasses import asdict
import json
import re
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_sessions import session_guard, SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.vendors.review_service import VerificationReviewService, ReviewConflict, ReviewCaseNotFound

router=APIRouter(prefix='/auth',tags=['Verification review'])


class SubmissionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)


class DecisionRequest(SubmissionRequest):
    expected_version: int = Field(ge=0)
    expected_evidence_revision: str = Field(pattern=r'^[0-9a-f]{64}$',repr=False)
    reason: str = Field(min_length=1,max_length=500,repr=False)

    @field_validator('reason')
    @classmethod
    def reason_valid(cls,value):
        import unicodedata
        if not value.strip() or any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('Invalid reason')
        return value.strip()


async def review_input(request:Request,_:Annotated[None,Depends(session_guard)]):
    types=request.headers.getlist('content-type')
    if len(types)!=1 or types[0].split(';',1)[0].strip().lower()!='application/json':
        fail(415,'unsupported_media_type','Use application/json')
    try:
        body=await request.json()
        return (SubmissionRequest if request.url.path.endswith('/submit') else DecisionRequest).model_validate(body)
    except (ValidationError,json.JSONDecodeError,UnicodeError,RecursionError):
        fail(422,'validation_error','Invalid verification review request')


def case_id(value):
    try:
        result=uuid.UUID(value)
        if str(result)!=value:
            raise ValueError()
        return result
    except ValueError:
        fail(422,'validation_error','Invalid verification case')


def perform(claims,settings,operation):
    try:
        return operation(VerificationReviewService(get_engine(),settings=settings))
    except SessionAuthenticationError:
        invalid_authentication()
    except VendorPermissionError:
        fail(403,'review_forbidden','Verification operation is not permitted')
    except ReviewCaseNotFound:
        fail(404,'case_not_found','Verification case is not available')
    except ReviewConflict:
        fail(409,'review_conflict','Verification case changed or transition is not permitted')
    except (VerificationInfrastructureUnavailable,SessionPersistenceError,SecurityConfigurationError,SQLAlchemyError,OSError):
        fail(503,'verification_unavailable','Verification is temporarily unavailable')


@router.post('/vendor/verification/submit',status_code=202,openapi_extra={'parameters':SECURITY_PARAMETERS,
    'requestBody':{'required':True,'content':{'application/json':{'schema':SubmissionRequest.model_json_schema()}}}})
def submit(value:Annotated[SubmissionRequest,Depends(review_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    version=perform(claims,settings,lambda service:service.submit_for_review(claims))
    return {'status':'pending','case_version':version}


@router.get('/verification/cases')
def cases(request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    try:
        params=request.query_params
        if set(params)-{'status','after','limit'} or any(len(params.getlist(key))!=1 for key in params):
            raise ValueError()
        status=params.get('status','pending')
        limit=int(params.get('limit','25'))
        if status not in {'pending','approved','rejected','suspended'} or not 1<=limit<=100:
            raise ValueError()
        after=case_id(params['after']) if 'after' in params else None
    except ValueError:
        fail(422,'validation_error','Invalid case filter')
    return {'cases':perform(claims,settings,lambda service:service.list_cases(claims,status=status,after=after,limit=limit))}


@router.get('/verification/cases/{vendor_id}')
def detail(vendor_id:str,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    target=case_id(vendor_id)
    return asdict(perform(claims,settings,lambda service:service.get_case(claims,target)))


@router.get('/verification/cases/{vendor_id}/document')
def document(vendor_id:str,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    target=case_id(vendor_id)
    content=perform(claims,settings,lambda service:service.get_document(claims,target))
    return Response(content,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'Content-Disposition':'attachment; filename="identity-document.jpg"','Content-Security-Policy':"default-src 'none'; sandbox"})


@router.get('/verification/cases/{vendor_id}/history')
def history(vendor_id:str,request:Request,claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    target=case_id(vendor_id)
    try:
        params=request.query_params
        if set(params)-{'after','limit'} or any(len(params.getlist(key))!=1 for key in params):
            raise ValueError()
        after=int(params.get('after','0')); limit=int(params.get('limit','100'))
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError()
    except ValueError:
        fail(422,'validation_error','Invalid audit filter')
    return {'history':perform(claims,settings,lambda service:service.history(claims,target,after=after,limit=limit))}


@router.post('/verification/cases/{vendor_id}/{action}',openapi_extra={'parameters':SECURITY_PARAMETERS,
    'requestBody':{'required':True,'content':{'application/json':{'schema':DecisionRequest.model_json_schema()}}}})
def decide(vendor_id:str,action:str,value:Annotated[DecisionRequest,Depends(review_input)],claims:Annotated[AccessTokenClaims,Depends(access_claims)],settings:Annotated[Settings,Depends(get_settings)]):
    if action not in {'approve','reject','suspend','reopen'}:
        fail(404,'case_not_found','Verification operation is not available')
    target=case_id(vendor_id)
    return perform(claims,settings,lambda service:service.decide(claims,target,action,value.expected_version,value.expected_evidence_revision,value.reason))

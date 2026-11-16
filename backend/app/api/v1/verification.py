"""Private ID submission and shared phone proof. Neither endpoint grants approval."""
import json
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_sessions import session_guard, SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail, client_address
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.sms import get_sms_delivery
from app.infrastructure.storage.private_documents import get_private_document_storage, VerificationInfrastructureUnavailable, InvalidDocument
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.auth.phone_service import PhoneVerificationService, PhoneRateLimited
from app.modules.auth.signup_rate_limit import configured_rate_limiter, SignupRateLimiter, SignupRateLimitedError, RateLimitUnavailableError
from app.modules.vendors.document_service import VendorDocumentService, IdentificationType

router = APIRouter(prefix='/auth', tags=['Verification'])


class PhoneSendLimiter(SignupRateLimiter):
    namespace = 'phone_send'
    limits = {'ip': 10}


class PhoneVerifyLimiter(SignupRateLimiter):
    namespace = 'phone_verify'
    limits = {'ip': 60}


def phone_limit(request, settings, *, verify=False):
    limiter = configured_rate_limiter(PhoneVerifyLimiter if verify else PhoneSendLimiter, settings.phone_otp_secret, settings)
    limiter.check('ip', client_address(request, settings))


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)


class VerifyRequest(EmptyRequest):
    code: SecretStr = Field(repr=False)

    @field_validator('code')
    @classmethod
    def six_digits(cls, value):
        import re
        if not re.fullmatch(r'[0-9]{6}', value.get_secret_value(), re.ASCII):
            raise ValueError('Invalid code')
        return value


async def phone_input(request: Request, _: Annotated[None, Depends(session_guard)]):
    types = request.headers.getlist('content-type')
    if len(types) != 1 or types[0].split(';', 1)[0].strip().lower() != 'application/json':
        fail(415, 'unsupported_media_type', 'Use application/json')
    try:
        body = await request.json()
        return (VerifyRequest if request.url.path.endswith('/verify-code') else EmptyRequest).model_validate(body)
    except (ValidationError, json.JSONDecodeError, UnicodeError, RecursionError):
        fail(422, 'validation_error', 'Invalid phone verification request')


def verification_error(error):
    if isinstance(error, SessionAuthenticationError):
        invalid_authentication()
    if isinstance(error, VendorPermissionError):
        fail(403, 'account_forbidden', 'Account operation is not permitted')
    if isinstance(error, (PhoneRateLimited, SignupRateLimitedError)):
        fail(429, 'rate_limited', 'Too many verification attempts', retry_after=error.retry_after)
    if isinstance(error, InvalidDocument):
        fail(422, 'invalid_document', str(error))
    fail(503, 'verification_unavailable', 'Verification is temporarily unavailable')


ERRORS = (SessionAuthenticationError, VendorPermissionError, PhoneRateLimited, SignupRateLimitedError,
          InvalidDocument, VerificationInfrastructureUnavailable, SessionPersistenceError,
          SecurityConfigurationError, SQLAlchemyError, OSError, RateLimitUnavailableError)


@router.post('/vendor/identity-document', status_code=202, dependencies=[Depends(session_guard)],
             description='Raw JPEG/PNG body, identification_type query enum. Private submission only; not approval. No retrieval URL is returned.',
             openapi_extra={'parameters': SECURITY_PARAMETERS + [{'in':'query','name':'identification_type','required':True,'schema':{'type':'string','enum':[v.value for v in IdentificationType]}}],
                           'requestBody': {'required':True,'content':{'image/jpeg':{'schema':{'type':'string','format':'binary'}},'image/png':{'schema':{'type':'string','format':'binary'}}}}})
async def submit_document(request: Request, claims: Annotated[AccessTokenClaims, Depends(access_claims)],
                          settings: Annotated[Settings, Depends(get_settings)]):
    types = request.headers.getlist('content-type')
    if len(types) != 1 or types[0].split(';',1)[0].strip().lower() not in {'image/jpeg','image/png'}:
        fail(415, 'unsupported_media_type', 'Use image/jpeg or image/png')
    values = request.query_params.getlist('identification_type')
    try:
        if len(values) != 1 or set(request.query_params) != {'identification_type'}:
            raise ValueError()
        kind = IdentificationType(values[0])
    except ValueError:
        fail(422, 'validation_error', 'Unsupported identification type')
    from starlette.concurrency import run_in_threadpool
    try:
        storage = get_private_document_storage(settings)
        content = await request.body()  # bounded by AuthRequestMiddleware first
        await run_in_threadpool(VendorDocumentService(get_engine(), settings=settings).submit, claims, kind, content, storage)
    except ERRORS as error:
        verification_error(error)
    return {'message':'Document submitted for verification'}


@router.post('/phone/send-code', status_code=202, openapi_extra={'parameters':SECURITY_PARAMETERS,
             'requestBody':{'required':True,'content':{'application/json':{'schema':EmptyRequest.model_json_schema()}}}})
def send_code(request: Request, value: Annotated[EmptyRequest, Depends(phone_input)],
              claims: Annotated[AccessTokenClaims, Depends(access_claims)], settings: Annotated[Settings, Depends(get_settings)]):
    try:
        phone_limit(request, settings)
        delivery = get_sms_delivery()
        PhoneVerificationService(get_engine(), settings=settings).send_code(claims, delivery, settings)
    except ERRORS as error:
        verification_error(error)
    return {'message':'If delivery is available, a verification code will be sent'}


@router.post('/phone/verify-code', status_code=204, response_class=Response,
             openapi_extra={'parameters':SECURITY_PARAMETERS,'requestBody':{'required':True,'content':{'application/json':{'schema':VerifyRequest.model_json_schema()}}}})
def verify_code(request: Request, value: Annotated[VerifyRequest, Depends(phone_input)],
                claims: Annotated[AccessTokenClaims, Depends(access_claims)], settings: Annotated[Settings, Depends(get_settings)]):
    try:
        phone_limit(request, settings, verify=True)
        valid = PhoneVerificationService(get_engine(), settings=settings).verify_code(claims, value.code.get_secret_value(), settings)
    except ERRORS as error:
        verification_error(error)
    if not valid:
        fail(400, 'invalid_code', 'Verification code is invalid or expired')
    return Response(status_code=204, headers={'Cache-Control':'no-store'})

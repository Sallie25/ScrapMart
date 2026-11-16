"""Vendor signup and bearer-authenticated, password-confirmed enrollment."""
import json
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_signup import registration_guard, enforce_limit, fail, normalize_signup_email, client_address
from app.api.v1.buyer_login import enforce_limit as enforce_login_limit
from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_sessions import SECURITY_PARAMETERS
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.email_identity_policy import PolicyVersionMismatch
from app.modules.auth.http_security import require_origin_csrf
from app.modules.auth.registration_schemas import BuyerSignupAcknowledgment
from app.modules.auth.registration_service import RegistrationUnavailableError
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_schemas import VendorSignupRequest, VendorEnrollmentRequest
from app.modules.auth.vendor_service import VendorRegistrationService, VendorEnrollmentService

router = APIRouter(prefix="/auth/vendor", tags=["Authentication"])


async def signup_input(request: Request, _: Annotated[None, Depends(registration_guard)]) -> VendorSignupRequest:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        fail(422, "validation_error", "Invalid registration request")
    # Count email attempts before password/other field validation. Invalid email
    # syntax still consumes the IP budget, without storing any submitted value.
    if isinstance(body, dict) and isinstance(body.get("email"), str):
        try:
            email = normalize_signup_email(body["email"])
        except PolicyVersionMismatch:
            fail(503, "registration_unavailable", "Registration is temporarily unavailable")
        except ValueError:
            pass
        else:
            await run_in_threadpool(enforce_limit, "email", email)
    try:
        return VendorSignupRequest.model_validate(body)
    except PolicyVersionMismatch:
        fail(503, "registration_unavailable", "Registration is temporarily unavailable")
    except ValidationError as error:
        known = {"email", "password", "full_name", "phone_number", "business_name"}
        fields = sorted({str(e["loc"][0]) for e in error.errors()
                         if e["loc"] and e["loc"][0] in known})
        # Do not serialize Pydantic input, ctx, or attacker-controlled field names.
        fail(422, "validation_error", "Invalid registration fields", fields=fields)


@router.post("/signup", status_code=202, response_model=BuyerSignupAcknowledgment,
             openapi_extra={"parameters": SECURITY_PARAMETERS, "requestBody": {
                 "required": True, "content": {"application/json": {"schema": VendorSignupRequest.model_json_schema()}}}})
def signup(value: Annotated[VendorSignupRequest, Depends(signup_input)]) -> BuyerSignupAcknowledgment:
    try:
        VendorRegistrationService(get_engine()).register(value)
    except RegistrationUnavailableError:
        fail(503, "registration_unavailable", "Registration is temporarily unavailable")
    return BuyerSignupAcknowledgment()


def enrollment_guard(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    require_origin_csrf(request, settings)
    types = request.headers.getlist("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        fail(415, "unsupported_media_type", "Use application/json")
    enforce_login_limit("ip", client_address(request, settings))


async def enrollment_input(request: Request, _: Annotated[None, Depends(enrollment_guard)]) -> VendorEnrollmentRequest:
    try:
        return VendorEnrollmentRequest.model_validate(await request.json())
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        fail(422, "validation_error", "Invalid enrollment fields")


@router.post("/enroll", status_code=204, response_class=Response,
             openapi_extra={"parameters": SECURITY_PARAMETERS, "requestBody": {
                 "required": True, "content": {"application/json": {"schema": VendorEnrollmentRequest.model_json_schema()}}}})
def enroll(value: Annotated[VendorEnrollmentRequest, Depends(enrollment_input)],
           claims: Annotated[AccessTokenClaims, Depends(access_claims)],
           settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    # Account-bound budget prevents distributed password guessing. The existing
    # HMAC limiter never stores the UUID itself in Redis keys.
    enforce_login_limit("email", str(claims.user_id))
    try:
        VendorEnrollmentService(get_engine(), settings=settings).enroll(claims, value)
    except SessionAuthenticationError:
        invalid_authentication()
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

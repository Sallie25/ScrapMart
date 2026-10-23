"""Buyer login HTTP boundary; authentication and admission remain in Phase 1."""
import json
import math
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.v1.buyer_signup import client_address, fail
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.email_identity_policy import PolicyVersionMismatch, canonical_registration_key
from app.modules.auth.login_policy import BuyerLoginUnavailableError, InvalidBuyerCredentials
from app.modules.auth.login_rate_limit import get_login_rate_limiter
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.login_service import BuyerLoginService
from app.modules.auth.security import SecurityConfigurationError, _token_config, create_access_token
from app.modules.auth.signup_rate_limit import RateLimitUnavailableError, SignupRateLimitedError

router = APIRouter(prefix="/auth", tags=["Authentication"])
REFRESH_COOKIE = "__Secure-scrapmart_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


class BuyerLoginResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


def unavailable():
    fail(503, "login_unavailable", "Buyer login is temporarily unavailable")


def enforce_limit(kind: str, value: str) -> None:
    try:
        get_login_rate_limiter().check(kind, value)
    except SignupRateLimitedError as error:
        fail(429, "rate_limited", "Too many login attempts", retry_after=error.retry_after)
    except RateLimitUnavailableError:
        unavailable()


def login_guard(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in settings.auth_allowed_origins:
        fail(403, "origin_rejected", "Request origin is not permitted")
    if request.headers.getlist("x-scrapmart-csrf") != ["1"]:
        fail(403, "csrf_rejected", "Required request header is missing or invalid")
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
        fail(415, "unsupported_media_type", "Use application/json")
    enforce_limit("ip", client_address(request, settings))


async def login_input(request: Request, _: Annotated[None, Depends(login_guard)]) -> BuyerLoginRequest:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        fail(422, "validation_error", "Invalid login request")
    # Account-independent counters include attempts with invalid passwords.
    if isinstance(body, dict) and isinstance(body.get("email"), str):
        try:
            email = canonical_registration_key(body["email"])
        except PolicyVersionMismatch:
            unavailable()
        except ValueError:
            pass
        else:
            await run_in_threadpool(enforce_limit, "email", email)
    try:
        return BuyerLoginRequest.model_validate(body)
    except PolicyVersionMismatch:
        unavailable()
    except ValidationError as error:
        fields = sorted({str(e["loc"][0]) for e in error.errors()
                         if e["loc"] and e["loc"][0] in {"email", "password"}})
        fail(422, "validation_error", "Invalid login fields", fields=fields)


@router.post(
    "/buyer/login", response_model=BuyerLoginResponse,
    description=("Returns an access JWT and sets a host-only __Secure-scrapmart_refresh cookie "
                 "with Secure, HttpOnly, SameSite=Lax and Path=/api/v1/auth. "
                 "Refresh tokens are never returned in JSON. All responses use Cache-Control: no-store."),
    responses={status: {"description": description} for status, description in {
        401: "Invalid email or password", 403: "Origin or CSRF rejected", 413: "Request too large",
        415: "JSON required", 422: "Safe field validation error", 429: "Rate limit exceeded; Retry-After",
        503: "Login temporarily unavailable", 500: "Unexpected safe error",
    }.items()},
    openapi_extra={
        "parameters": [
            {"in": "header", "name": "Origin", "required": True, "schema": {"type": "string"}},
            {"in": "header", "name": "X-ScrapMart-CSRF", "required": True,
             "schema": {"type": "string", "enum": ["1"]}},
        ],
        "requestBody": {"required": True, "content": {
            "application/json": {"schema": BuyerLoginRequest.model_json_schema()},
        }},
    },
)
def buyer_login(login: Annotated[BuyerLoginRequest, Depends(login_input)], response: Response,
                settings: Annotated[Settings, Depends(get_settings)]) -> BuyerLoginResponse:
    try:
        # Validate signing configuration before committing a session. Token
        # issuance itself uses the existing Stage 2A helper after admission.
        token_config = _token_config(settings)
        credentials = BuyerLoginService(get_engine(), settings=settings).login(login)
        access = create_access_token(credentials.user_id, credentials.session_id, settings=settings)
    except InvalidBuyerCredentials:
        raise HTTPException(401, detail={"code": "invalid_credentials", "message": "Invalid email or password", "fields": []},
                            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"}) from None
    except (BuyerLoginUnavailableError, SecurityConfigurationError):
        unavailable()
    remaining = max(0, math.floor((credentials.expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(REFRESH_COOKIE, credentials.refresh_token, max_age=remaining,
                        expires=credentials.expires_at, path=REFRESH_COOKIE_PATH,
                        secure=True, httponly=True, samesite="lax")
    return BuyerLoginResponse(access_token=access, expires_in=token_config.lifetime_seconds)

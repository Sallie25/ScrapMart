"""Public Buyer registration only. No login, cookies, or token issuance."""
import ipaddress
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.email_identity_policy import PolicyVersionMismatch
from app.modules.auth.http_security import require_origin_csrf
from app.modules.auth.registration_schemas import (
    BuyerSignupAcknowledgment, BuyerSignupRequest, normalize_signup_email,
)
from app.modules.auth.registration_service import BuyerRegistrationService, RegistrationUnavailableError
from app.modules.auth.signup_rate_limit import (
    RateLimitUnavailableError, SignupRateLimitedError, get_signup_rate_limiter,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def fail(status: int, code: str, message: str, *, fields: list[str] | None = None,
         retry_after: int | None = None) -> None:
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    raise HTTPException(status, detail={
        "code": code, "message": message, "fields": fields or [],
    }, headers=headers)


def client_address(request: Request, settings: Settings) -> str:
    # Uvicorn must run with --no-proxy-headers, so scope.client is the socket peer.
    try:
        if request.client is None:
            raise ValueError
        peer = ipaddress.ip_address(request.client.host)
        networks = [ipaddress.ip_network(value) for value in settings.auth_trusted_proxy_cidrs]
        trusted = lambda address: any(address in network for network in networks)
        if trusted(peer):
            forwarded = request.headers.getlist("x-forwarded-for")
            if len(forwarded) > 1:
                raise ValueError
            if forwarded:
                hops = forwarded[0].split(",")
                if not 1 <= len(hops) <= 32:
                    raise ValueError
                for hop in reversed(hops):
                    if not trusted(peer):
                        break
                    peer = ipaddress.ip_address(hop.strip())
        if isinstance(peer, ipaddress.IPv6Address) and peer.ipv4_mapped is not None:
            peer = peer.ipv4_mapped
        return str(peer)
    except ValueError:
        fail(400, "invalid_client_address", "Unable to identify the client address")


def enforce_limit(kind: str, value: str) -> None:
    try:
        get_signup_rate_limiter().check(kind, value)
    except SignupRateLimitedError as error:
        fail(429, "rate_limited", "Too many registration attempts", retry_after=error.retry_after)
    except RateLimitUnavailableError:
        fail(503, "registration_unavailable", "Registration is temporarily unavailable")


def registration_guard(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    require_origin_csrf(request, settings)
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
        fail(415, "unsupported_media_type", "Use application/json")
    enforce_limit("ip", client_address(request, settings))


async def signup_input(request: Request, _: Annotated[None, Depends(registration_guard)]) -> BuyerSignupRequest:
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
        return BuyerSignupRequest.model_validate(body)
    except PolicyVersionMismatch:
        fail(503, "registration_unavailable", "Registration is temporarily unavailable")
    except ValidationError as error:
        known = {"email", "password", "full_name", "phone_number"}
        fields = sorted({str(e["loc"][0]) for e in error.errors()
                         if e["loc"] and e["loc"][0] in known})
        # Do not serialize Pydantic input, ctx, or attacker-controlled field names.
        fail(422, "validation_error", "Invalid registration fields", fields=fields)


@router.post(
    "/buyer/signup", status_code=202, response_model=BuyerSignupAcknowledgment,
    responses={status: {"description": description} for status, description in {
        403: "Origin or CSRF rejected", 413: "Request too large", 415: "JSON required",
        422: "Safe field validation error", 429: "Rate limit exceeded; Retry-After header",
        503: "Registration temporarily unavailable", 500: "Unexpected safe error",
    }.items()},
    openapi_extra={
        "parameters": [
            {"in": "header", "name": "Origin", "required": True, "schema": {"type": "string"}},
            {"in": "header", "name": "X-ScrapMart-CSRF", "required": True,
             "schema": {"type": "string", "enum": ["1"]}},
        ],
        "requestBody": {"required": True, "content": {
            "application/json": {"schema": BuyerSignupRequest.model_json_schema()},
        }},
    },
)
def buyer_signup(signup: Annotated[BuyerSignupRequest, Depends(signup_input)]) -> BuyerSignupAcknowledgment:
    try:
        BuyerRegistrationService(get_engine()).register(signup)
    except RegistrationUnavailableError:
        fail(503, "registration_unavailable", "Registration is temporarily unavailable")
    return BuyerSignupAcknowledgment()

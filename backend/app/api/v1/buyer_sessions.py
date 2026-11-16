"""Cookie-only session lifecycle; no JSON, URL or Authorization token input."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.api.v1.buyer_login import BuyerLoginResponse
from app.api.v1.buyer_signup import fail
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.http_security import REFRESH_COOKIE, clear_refresh_cookie, require_origin_csrf, set_refresh_cookie
from app.modules.auth.security import InvalidRefreshTokenError, SecurityConfigurationError, _token_config, create_access_token, digest_refresh_token
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError, SessionService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def session_guard(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    require_origin_csrf(request, settings)


def credential_cookie(request: Request) -> str | None:
    # Reject ambiguous duplicate cookies rather than silently selecting one.
    values = []
    for header in request.headers.getlist("cookie"):
        for part in header.split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name == REFRESH_COOKIE:
                values.append(value)
    if len(values) != 1:
        return None
    try:
        digest_refresh_token(values[0])
    except InvalidRefreshTokenError:
        return None
    return values[0]


def invalid_session() -> JSONResponse:
    response = JSONResponse(status_code=401, content={"detail": {
        "code": "invalid_session", "message": "Authentication session is invalid", "fields": [],
    }}, headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"})
    clear_refresh_cookie(response)
    return response


SECURITY_PARAMETERS = [
    {"in": "header", "name": "Origin", "required": True, "schema": {"type": "string"}},
    {"in": "header", "name": "X-ScrapMart-CSRF", "required": True, "schema": {"type": "string", "enum": ["1"]}},
]


@router.post("/refresh", response_model=BuyerLoginResponse,
             description="Rotates the refresh cookie without extending session expiry. No request body or bearer-token input. Replay revokes the session.",
             responses={401: {"description": "Invalid session; refresh cookie cleared"},
                        403: {"description": "Origin or CSRF rejected"}, 413: {"description": "Request too large"},
                        503: {"description": "Session service unavailable; retry without discarding cookie"}},
             openapi_extra={"parameters": SECURITY_PARAMETERS})
def refresh(request: Request, response: Response, _: Annotated[None, Depends(session_guard)],
            settings: Annotated[Settings, Depends(get_settings)]):
    token = credential_cookie(request)
    if token is None:
        return invalid_session()
    try:
        config = _token_config(settings)  # Fail before consuming a valid refresh credential.
        credentials = SessionService(get_engine(), settings=settings).rotate_refresh_token(token)
        access = create_access_token(credentials.user_id, credentials.session_id, settings=settings)
    except SessionAuthenticationError:
        return invalid_session()
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")
    set_refresh_cookie(response, credentials)
    return BuyerLoginResponse(access_token=access, expires_in=config.lifetime_seconds)


@router.post("/logout", status_code=204, response_class=Response,
             description="Revokes the cookie's session and clears the cookie. Missing/invalid/already-revoked credentials return the same empty 204. No request body.",
             responses={403: {"description": "Origin or CSRF rejected"}, 413: {"description": "Request too large"},
                        503: {"description": "Revocation could not be confirmed; cookie retained for retry"}},
             openapi_extra={"parameters": SECURITY_PARAMETERS})
def logout(request: Request, _: Annotated[None, Depends(session_guard)],
           settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    token = credential_cookie(request)
    if token is not None:
        try:
            SessionService(get_engine(), settings=settings).revoke_refresh_session(token)
        except SessionAuthenticationError:
            pass  # Invalid credentials never disclose session existence.
        except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
            fail(503, "session_unavailable", "Session operation is temporarily unavailable")
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_refresh_cookie(response)
    return response

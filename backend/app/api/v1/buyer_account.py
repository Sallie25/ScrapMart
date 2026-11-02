"""Authenticated Buyer information and logout-all; no caller-supplied identity."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.buyer_sessions import SECURITY_PARAMETERS, session_guard
from app.api.v1.buyer_signup import fail
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.http_security import clear_refresh_cookie
from app.modules.auth.security import AccessTokenClaims, InvalidAccessTokenError, SecurityConfigurationError, verify_access_token
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError, SessionService

router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer = HTTPBearer(auto_error=False)


class BuyerProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(repr=False)
    full_name: str = Field(repr=False)
    phone_number: str | None = Field(repr=False)
    signup_completed_at: datetime


def invalid_authentication() -> None:
    raise HTTPException(401, detail={
        "code": "invalid_session", "message": "Authentication session is invalid", "fields": [],
    }, headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"}) from None


def access_claims(request: Request,
                  credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                  settings: Annotated[Settings, Depends(get_settings)]) -> AccessTokenClaims:
    headers = request.headers.getlist("authorization")
    # HTTPBearer supplies OpenAPI security metadata; reject duplicates and
    # ambiguous whitespace before handing credentials to the existing verifier.
    if len(headers) != 1 or credentials is None:
        invalid_authentication()
    parts = headers[0].split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        invalid_authentication()
    try:
        return verify_access_token(parts[1], settings=settings)
    except InvalidAccessTokenError:
        invalid_authentication()
    except SecurityConfigurationError:
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")


@router.get("/me", response_model=BuyerProfileResponse,
            description="Returns only email, full_name, phone_number and signup_completed_at for an active Buyer with a live session. Bearer authentication only.",
            responses={401: {"description": "Generic authentication failure"},
                       503: {"description": "Session service unavailable"}})
def me(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
       settings: Annotated[Settings, Depends(get_settings)]) -> BuyerProfileResponse:
    try:
        profile = SessionService(get_engine(), settings=settings).get_buyer_profile(claims)
    except SessionAuthenticationError:
        invalid_authentication()
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")
    return BuyerProfileResponse(email=profile.email, full_name=profile.full_name,
                                phone_number=profile.phone_number,
                                signup_completed_at=profile.signup_completed_at)


@router.post("/logout-all", status_code=204, response_class=Response,
             dependencies=[Depends(session_guard)],
             description="Revokes every active session of the authenticated Buyer, including the current session, and clears the refresh cookie. A revoked bearer token cannot repeat the operation.",
             responses={401: {"description": "Generic authentication failure"},
                        403: {"description": "Origin or CSRF rejected"}, 413: {"description": "Request too large"},
                        503: {"description": "Revocation could not be confirmed"}},
             openapi_extra={"parameters": SECURITY_PARAMETERS})
def logout_all(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
               settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    try:
        SessionService(get_engine(), settings=settings).revoke_all_buyer_sessions(claims)
    except SessionAuthenticationError:
        invalid_authentication()
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_refresh_cookie(response)
    return response

"""Bearer-authenticated Vendor profile and shared account-experience discovery."""
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_signup import fail
from app.api.v1.buyer_sessions import session_guard, SECURITY_PARAMETERS
from app.modules.auth.http_security import clear_refresh_cookie
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError

router = APIRouter(prefix="/auth", tags=["Authentication"])
VerificationStatus = Literal["pending", "approved", "rejected", "suspended"]


class VendorProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(repr=False)
    verification_status: VerificationStatus
    full_name: str = Field(repr=False)
    email: str = Field(repr=False)
    phone_number: str | None = Field(repr=False)
    created_at: datetime


class AccountCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buyer: bool
    vendor: bool
    vendor_verification_status: VerificationStatus | None


def account_operation(method, claims, settings):
    try:
        service = VendorAuthorizationService(get_engine(), settings=settings)
        return getattr(service, method)(claims)
    except SessionAuthenticationError:
        invalid_authentication()
    except VendorPermissionError:
        fail(403, "account_forbidden", "Account operation is not permitted")
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")


@router.get("/vendor/me", response_model=VendorProfileResponse,
            description="Safe Vendor profile, including current verification status and Vendor registration timestamp. All recognized states may read; this does not grant selling permission.",
            responses={401: {"description": "Invalid authentication"},
                       403: {"description": "Vendor profile required"},
                       503: {"description": "Session service unavailable"}})
def vendor_me(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
              settings: Annotated[Settings, Depends(get_settings)]) -> VendorProfileResponse:
    return VendorProfileResponse(**asdict(account_operation("get_vendor_profile", claims, settings)))


@router.get("/capabilities", response_model=AccountCapabilitiesResponse,
            description="Lists existing Buyer/Vendor experiences and current Vendor status. Read only; no profile creation, session mode, or verification permission is granted.",
            responses={401: {"description": "Invalid authentication"},
                       403: {"description": "Unrecognized profile state"},
                       503: {"description": "Session service unavailable"}})
def capabilities(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
                 settings: Annotated[Settings, Depends(get_settings)]) -> AccountCapabilitiesResponse:
    return AccountCapabilitiesResponse(**asdict(account_operation("get_account_capabilities", claims, settings)))


@router.post("/vendor/logout-all", status_code=204, response_class=Response,
             dependencies=[Depends(session_guard)],
             description="Revokes all active sessions for the authenticated Vendor's shared User across Buyer and Vendor experiences. All recognized verification states may log out. Clears the shared refresh cookie.",
             responses={401: {"description": "Invalid authentication"},
                        403: {"description": "Origin/CSRF rejected or Vendor profile required"},
                        413: {"description": "Request too large"},
                        503: {"description": "Revocation could not be confirmed; cookie retained"}},
             openapi_extra={"parameters": SECURITY_PARAMETERS})
def vendor_logout_all(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
                      settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    account_operation("revoke_all_vendor_sessions", claims, settings)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_refresh_cookie(response)
    return response

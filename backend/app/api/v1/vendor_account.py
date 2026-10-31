"""Bearer-authenticated Vendor profile and shared account-experience discovery."""
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_signup import fail
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


def account_read(method, claims, settings):
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
    return VendorProfileResponse(**asdict(account_read("get_vendor_profile", claims, settings)))


@router.get("/capabilities", response_model=AccountCapabilitiesResponse,
            description="Lists existing Buyer/Vendor experiences and current Vendor status. Read only; no profile creation, session mode, or verification permission is granted.",
            responses={401: {"description": "Invalid authentication"},
                       403: {"description": "Unrecognized profile state"},
                       503: {"description": "Session service unavailable"}})
def capabilities(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
                 settings: Annotated[Settings, Depends(get_settings)]) -> AccountCapabilitiesResponse:
    return AccountCapabilitiesResponse(**asdict(account_read("get_account_capabilities", claims, settings)))

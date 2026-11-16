"""Private, authenticated shop drafts. No verification submissions or approval."""
from dataclasses import asdict
import json
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_signup import fail
from app.api.v1.buyer_sessions import SECURITY_PARAMETERS, session_guard
from app.api.v1.vendor_account import VerificationStatus
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.vendors.onboarding_schemas import ShopInformationPatch
from app.modules.vendors.onboarding_service import VendorOnboardingService

router = APIRouter(prefix="/auth/vendor", tags=["Vendor onboarding"])


class ShopInformationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(repr=False)
    shop_location: str | None = Field(repr=False)
    shop_address: str | None = Field(repr=False)
    verification_status: VerificationStatus


async def patch_input(request: Request, _: Annotated[None, Depends(session_guard)]) -> ShopInformationPatch:
    types = request.headers.getlist("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        fail(415, "unsupported_media_type", "Use application/json")
    try:
        return ShopInformationPatch.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError, UnicodeError, RecursionError):
        fail(422, "validation_error", "Invalid shop information")


def perform(claims, settings, patch=None):
    try:
        service = VendorOnboardingService(get_engine(), settings=settings)
        result = service.get_shop_information(claims) if patch is None else service.update_shop_information(claims, patch)
        return ShopInformationResponse(**asdict(result))
    except SessionAuthenticationError:
        invalid_authentication()
    except VendorPermissionError:
        fail(403, "account_forbidden", "Account operation is not permitted")
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "session_unavailable", "Session operation is temporarily unavailable")


@router.get("/onboarding", response_model=ShopInformationResponse,
            description="Private shop information for the authenticated Vendor; never public location consent.")
def onboarding(claims: Annotated[AccessTokenClaims, Depends(access_claims)],
               settings: Annotated[Settings, Depends(get_settings)]) -> ShopInformationResponse:
    return perform(claims, settings)


@router.patch("/onboarding", response_model=ShopInformationResponse,
              description="Updates supplied shop draft fields for pending/rejected Vendors only. Status is preserved; this does not submit verification or grant approval.",
              openapi_extra={"parameters": SECURITY_PARAMETERS, "requestBody": {
                  "required": True, "content": {"application/json": {"schema": ShopInformationPatch.model_json_schema()}}}})
def update_onboarding(patch: Annotated[ShopInformationPatch, Depends(patch_input)],
                      claims: Annotated[AccessTokenClaims, Depends(access_claims)],
                      settings: Annotated[Settings, Depends(get_settings)]) -> ShopInformationResponse:
    return perform(claims, settings, patch)

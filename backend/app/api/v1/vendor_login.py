"""Vendor login reuses shared browser guards, input validation and rate budgets."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_login import BuyerLoginResponse, login_input
from app.api.v1.buyer_sessions import SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.modules.auth.http_security import set_refresh_cookie
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.security import SecurityConfigurationError, _token_config, create_access_token
from app.modules.auth.vendor_login_service import (
    VendorLoginService, InvalidVendorCredentials, VendorLoginUnavailableError,
)

router = APIRouter(prefix="/auth/vendor", tags=["Authentication"])


@router.post("/login", response_model=BuyerLoginResponse,
             description="Authenticates an active identity with a Vendor profile in any recognized verification state. Suspended login is provisional and restricted; authentication never grants selling or review permissions. Sets the shared secure HttpOnly refresh cookie.",
             responses={401: {"description": "Invalid email or password"},
                        403: {"description": "Origin or CSRF rejected"},
                        413: {"description": "Request too large"},
                        415: {"description": "JSON required"},
                        422: {"description": "Safe input validation error"},
                        429: {"description": "Shared login limit exceeded"},
                        503: {"description": "Login temporarily unavailable"}},
             openapi_extra={"parameters": SECURITY_PARAMETERS, "requestBody": {
                 "required": True, "content": {"application/json": {"schema": BuyerLoginRequest.model_json_schema()}}}})
def vendor_login(login: Annotated[BuyerLoginRequest, Depends(login_input)], response: Response,
                 settings: Annotated[Settings, Depends(get_settings)]) -> BuyerLoginResponse:
    try:
        config = _token_config(settings)
        credentials = VendorLoginService(get_engine(), settings=settings).login(login)
        access = create_access_token(credentials.user_id, credentials.session_id, settings=settings)
    except InvalidVendorCredentials:
        raise HTTPException(401, detail={"code": "invalid_credentials", "message": "Invalid email or password", "fields": []},
                            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"}) from None
    except (VendorLoginUnavailableError, SecurityConfigurationError, SQLAlchemyError, OSError):
        fail(503, "login_unavailable", "Vendor login is temporarily unavailable")
    set_refresh_cookie(response, credentials)
    return BuyerLoginResponse(access_token=access, expires_in=config.lifetime_seconds)

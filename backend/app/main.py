from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.orders import router as orders_router
from app.api.v1.marketplace import router as marketplace_router
from app.api.v1.buyer_signup import router as buyer_signup_router
from app.api.v1.buyer_login import router as buyer_login_router
from app.api.v1.buyer_sessions import router as buyer_sessions_router
from app.api.v1.buyer_account import router as buyer_account_router
from app.api.v1.verification_review import router as verification_review_router
from app.api.v1.verification import router as verification_router
from app.api.v1.vendor_onboarding import router as vendor_onboarding_router
from app.api.v1.vendor_account import router as vendor_account_router
from app.api.v1.vendor_login import router as vendor_login_router
from app.api.v1.vendor_registration import router as vendor_registration_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.modules.auth.http_security import AuthNoStoreMiddleware, AuthRequestMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Backend API for the ScrapMart marketplace.",
        version=settings.app_version,
    )

    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(marketplace_router, prefix="/api/v1")
    app.include_router(verification_review_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(vendor_onboarding_router, prefix="/api/v1")
    app.include_router(vendor_account_router, prefix="/api/v1")
    app.include_router(vendor_login_router, prefix="/api/v1")
    app.include_router(vendor_registration_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(buyer_signup_router, prefix="/api/v1")
    app.include_router(buyer_login_router, prefix="/api/v1")
    app.include_router(buyer_sessions_router, prefix="/api/v1")
    app.include_router(buyer_account_router, prefix="/api/v1")
    app.add_middleware(AuthRequestMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.auth_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-ScrapMart-CSRF", "Authorization"],
        expose_headers=["Retry-After"],
    )
    app.add_middleware(AuthNoStoreMiddleware)

    return app


app = create_app()

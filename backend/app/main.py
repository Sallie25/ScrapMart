from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Backend API for the ScrapMart marketplace.",
        version=settings.app_version,
    )

    app.include_router(health_router, prefix="/api/v1")

    return app


app = create_app()

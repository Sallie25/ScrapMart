from fastapi import APIRouter, HTTPException, status

from app.infrastructure.database.check import check_database_connection

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "scrapmart-backend",
    }


@router.get("/health/ready")
def readiness_check():
    if not check_database_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )

    return {
        "status": "ready",
        "database": "connected",
    }
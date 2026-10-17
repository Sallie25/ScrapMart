from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "scrapmart-backend",
    }


def test_readiness_check_database_available():
    with patch(
        "app.api.v1.health.check_database_connection",
        return_value=True,
    ):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


def test_readiness_check_database_unavailable():
    with patch(
        "app.api.v1.health.check_database_connection",
        return_value=False,
    ):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database is unavailable",
    }

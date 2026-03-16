from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    # Status is "degraded" when running without a live DB (expected in unit tests).
    assert body["status"] in {"ok", "degraded"}
    assert isinstance(body["uptime_seconds"], (int, float))
    assert isinstance(body["database"], bool)
    assert isinstance(body["ai_service"], bool)
    assert body["version"] == "1.0.0"
    # X-Request-Id header must be present
    assert "x-request-id" in response.headers

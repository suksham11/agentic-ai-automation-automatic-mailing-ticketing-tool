from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import APIKeyAuthMiddleware, RateLimitMiddleware


def _build_app(*, auth_enabled: bool, rate_enabled: bool, max_requests: int = 2, window_seconds: int = 60) -> FastAPI:
    app = FastAPI()

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/v1/secure")
    def secure() -> dict:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        enabled=rate_enabled,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    app.add_middleware(
        APIKeyAuthMiddleware,
        enabled=auth_enabled,
        api_key="secret-key",
        header_name="X-API-Key",
    )
    return app


def test_api_key_middleware_rejects_missing_key() -> None:
    client = TestClient(_build_app(auth_enabled=True, rate_enabled=False))

    response = client.get("/v1/secure")

    assert response.status_code == 401


def test_api_key_middleware_allows_valid_key() -> None:
    client = TestClient(_build_app(auth_enabled=True, rate_enabled=False))

    response = client.get("/v1/secure", headers={"X-API-Key": "secret-key"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_key_middleware_skips_health_endpoint() -> None:
    client = TestClient(_build_app(auth_enabled=True, rate_enabled=False))

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_middleware_blocks_after_threshold() -> None:
    client = TestClient(_build_app(auth_enabled=False, rate_enabled=True, max_requests=2, window_seconds=60))

    r1 = client.get("/v1/secure")
    r2 = client.get("/v1/secure")
    r3 = client.get("/v1/secure")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_rate_limit_middleware_skips_health_endpoint() -> None:
    client = TestClient(_build_app(auth_enabled=False, rate_enabled=True, max_requests=1, window_seconds=60))

    r1 = client.get("/v1/health")
    r2 = client.get("/v1/health")

    assert r1.status_code == 200
    assert r2.status_code == 200

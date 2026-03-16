import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging_config import configure_logging, request_id_var
from app.services.persistence import init_database

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a unique request_id per request, inject it into the logging
    context, log request start/finish with duration, and expose the id as a
    response header (``X-Request-Id``)."""

    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        token = request_id_var.set(req_id)
        request.state.request_id = req_id
        start = time.perf_counter()
        logger.info(
            "request_started",
            extra={"method": request.method, "path": request.url.path},
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception(
                "request_error",
                extra={"path": request.url.path, "duration_ms": duration_ms},
            )
            raise
        finally:
            request_id_var.reset(token)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "request_finished",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-Id"] = req_id
        return response


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, enabled: bool, api_key: str, header_name: str) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.api_key = api_key
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        if request.url.path == "/v1/health":
            return await call_next(request)

        provided = request.headers.get(self.header_name, "")
        if not self.api_key or provided != self.api_key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, enabled: bool, max_requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        if request.url.path == "/v1/health":
            return await call_next(request)

        now = time.time()
        client_ip = request.client.host if request.client else "unknown"

        with self._lock:
            bucket = self._events[client_ip]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(self.window_seconds)},
                )

            bucket.append(now)

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_time = time.time()
    # Best-effort DB init – API stays up even if DB is temporarily unavailable.
    initialized = init_database(settings)
    if not initialized:
        logger.warning("Database initialization failed during startup; continuing in degraded mode")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch any unhandled exception from route handlers and return a
    structured JSON 500 response with the request_id for correlation."""
    req_id = getattr(request.state, "request_id", "-")
    logger.exception(
        "unhandled_exception",
        extra={"req_id": req_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred. Please try again.",
            "request_id": req_id,
        },
    )


# Middlewares are applied in LIFO order (last added = outermost = first to run).
# Execution order for an incoming request:
#   CORSMiddleware → RequestContext → APIKeyAuth → RateLimit → route handler
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    max_requests=max(1, settings.rate_limit_requests),
    window_seconds=max(1, settings.rate_limit_window_seconds),
)
app.add_middleware(
    APIKeyAuthMiddleware,
    enabled=settings.api_auth_enabled,
    api_key=settings.api_key,
    header_name=settings.api_key_header,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

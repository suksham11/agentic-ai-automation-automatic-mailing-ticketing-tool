import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.services.persistence import init_database

settings = get_settings()
logger = logging.getLogger(__name__)


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
async def lifespan(_: FastAPI):
	# Best-effort DB init. API still runs if DB is temporarily unavailable.
	initialized = init_database(settings)
	if not initialized:
		logger.warning("Database initialization failed during startup; continuing in degraded mode")
	yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
app.include_router(router)

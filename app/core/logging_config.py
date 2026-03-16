"""Structured JSON logging and per-request context helpers."""
import contextvars
import json
import logging
import sys
from typing import Any

# Per-request context variable – set by RequestContextMiddleware in main.py.
# Every log record emitted during a request will automatically carry this ID.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Fields that are already captured in the base payload or are internal
# logging artefacts and should not be re-emitted as extra structured fields.
_SKIP_FIELDS = frozenset(
    {
        "ts", "level", "logger", "request_id", "message",
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName", "exc_info", "exc_text",
        "taskName",
    }
)


class StructuredFormatter(logging.Formatter):
    """Emit every log record as a single-line JSON object.

    The ``request_id`` field is injected automatically from the active
    async context variable so every log line is traceable to its request.
    Callers can attach arbitrary structured key/value pairs via ``extra``::

        logger.info("ticket_saved", extra={"ticket_id": tid, "intent": intent})
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get("-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Forward any caller-supplied extra fields into the JSON envelope.
        for key, value in record.__dict__.items():
            if key not in _SKIP_FIELDS:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """Replace root logger handlers with a single structured JSON stream handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # Quieten uvicorn's built-in access log – we emit richer timing lines.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

import json
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def _build_engine(settings: Settings):
    return create_engine(settings.postgres_dsn, pool_pre_ping=True, future=True)


def init_database(settings: Settings) -> bool:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _build_engine(settings)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

    # Import model metadata lazily to avoid circular imports.
    from app.models.ticket_event import TicketEvent  # noqa: F401

    try:
        Base.metadata.create_all(bind=_engine)
        return True
    except Exception:
        return False


@contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def to_json_list(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


def from_json_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []

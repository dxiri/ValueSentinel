"""Database session and engine management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from valuesentinel.config import get_config
from valuesentinel.models import Base

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        connect_args = {}
        if cfg.db.url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(cfg.db.url, connect_args=connect_args, echo=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def init_db() -> None:
    """Create all tables (for development / SQLite). Use Alembic for production."""
    Base.metadata.create_all(get_engine())


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Yield a database session with automatic commit/rollback."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

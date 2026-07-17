"""
SQLite / PostgreSQL connection helpers via SQLAlchemy.

Phase 1 defaults to a local SQLite file under `data/`.
Switch to PostgreSQL by setting DATABASE_URL in `.env`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from database.schema import BASE_SCHEMA_SQL

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine."""
    global _engine, _SessionLocal

    if _engine is None:
        settings.ensure_directories()
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            # Required for Streamlit multi-thread access to SQLite.
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            settings.database_url,
            future=True,
            echo=False,
            connect_args=connect_args,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the configured session factory, initializing the engine if needed."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create application tables if they do not already exist."""
    engine = get_engine()
    with engine.begin() as conn:
        for statement in BASE_SCHEMA_SQL:
            conn.execute(text(statement))


def execute_sql(sql: str, params: dict | None = None) -> Iterator:
    """Execute a raw SQL statement and yield rows (utility for simple inserts)."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        if result.returns_rows:
            yield from result.mappings()

"""Database engine and session management.

Provides factory functions for creating SQLAlchemy engines and sessions.
Supports both SQLite (dev) and PostgreSQL (production) via the DATABASE_URL
setting.

Usage:
    from trading_crew.db import get_engine, get_session

    engine = get_engine()
    with get_session(engine) as session:
        session.query(OrderRecord).all()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from trading_crew.db.models import Base

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)

_engines: dict[str, Engine] = {}


def get_engine(
    database_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
) -> Engine:
    """Create or return a cached SQLAlchemy engine for the given URL.

    Engines are cached by URL so that different URLs (e.g. test vs prod)
    get separate engine instances, preventing cross-environment contamination.

    For non-SQLite databases (e.g. PostgreSQL) the connection pool is
    configured using ``pool_size``, ``max_overflow``, and ``pool_timeout``.
    SQLite uses ``check_same_thread=False`` and skips explicit pool config
    because SQLite's single-writer model doesn't benefit from connection pooling.

    Args:
        database_url: Database connection string. If None, reads from settings.
            Accepts SQLite and PostgreSQL URLs.
        pool_size: Max number of persistent connections (non-SQLite only).
        max_overflow: Extra connections allowed above pool_size (non-SQLite only).
        pool_timeout: Seconds to wait for a free connection (non-SQLite only).

    Returns:
        A SQLAlchemy Engine instance.
    """
    if database_url is None:
        from trading_crew.config.settings import get_settings

        s = get_settings()
        database_url = s.database_url
        if pool_size is None:
            pool_size = s.database_pool_size
        if max_overflow is None:
            max_overflow = s.database_max_overflow
        if pool_timeout is None:
            pool_timeout = s.database_pool_timeout

    if database_url in _engines:
        return _engines[database_url]

    is_sqlite = database_url.startswith("sqlite")
    connect_args: dict[str, object] = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine_kwargs: dict[str, object] = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        engine_kwargs["pool_size"] = pool_size or 5
        engine_kwargs["max_overflow"] = max_overflow if max_overflow is not None else 10
        engine_kwargs["pool_timeout"] = pool_timeout or 30

    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    _engines[database_url] = engine
    logger.info("Database engine created: %s", database_url.split("@")[-1])
    return engine


def reset_engines() -> None:
    """Dispose all cached engines. Intended for test teardown."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def init_db(engine: Engine | None = None) -> None:
    """Create all tables if they don't exist.

    This is a convenience for development. In production, use Alembic
    migrations via ``make db-upgrade``.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized")


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Provide a transactional database session.

    Commits on successful exit, rolls back on exception.

    Usage:
        with get_session() as session:
            session.add(record)
    """
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

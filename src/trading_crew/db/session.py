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


def get_engine(database_url: str | None = None) -> Engine:
    """Create or return a cached SQLAlchemy engine for the given URL.

    Engines are cached by URL so that different URLs (e.g. test vs prod)
    get separate engine instances, preventing cross-environment contamination.

    Args:
        database_url: Database connection string. If None, reads from settings.
            Accepts SQLite and PostgreSQL URLs.

    Returns:
        A SQLAlchemy Engine instance.
    """
    if database_url is None:
        from trading_crew.config.settings import get_settings

        database_url = get_settings().database_url

    if database_url in _engines:
        return _engines[database_url]

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False,
        pool_pre_ping=True,
    )

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

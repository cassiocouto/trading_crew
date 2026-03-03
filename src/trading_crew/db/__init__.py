"""Database layer.

Provides SQLAlchemy ORM models and session management. The actual tables
mirror the Pydantic domain models but are optimized for relational storage.

Usage:
    from trading_crew.db import get_engine, get_session, Base
"""

from trading_crew.db.models import Base
from trading_crew.db.session import get_engine, get_session, reset_engines

__all__ = ["Base", "get_engine", "get_session", "reset_engines"]

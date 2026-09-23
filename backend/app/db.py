from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    """Metadata shared by Alembic and repository tests."""


@lru_cache(maxsize=4)
def create_engine_for_url(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def session_factory(current_settings: Settings):
    return sessionmaker(
        bind=create_engine_for_url(current_settings.database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

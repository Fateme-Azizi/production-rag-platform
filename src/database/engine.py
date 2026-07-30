from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings


def _build_database_url() -> str | None:
    """Create a SQLAlchemy async URL when database settings are present."""
    if settings.database_use_uri and settings.database_uri:
        return settings.database_uri

    if settings.database_server and settings.database_name:
        username = settings.database_username or "postgres"
        password = settings.database_password or ""
        host = settings.database_server
        port = settings.database_port or 5432
        return (
            f"postgresql+psycopg://{username}:{password}@{host}:{port}/"
            f"{settings.database_name}"
        )

    return None


@dataclass
class DatabaseSessionManager:
    """Simple async DB session provider for FastAPI dependency injection."""

    engine: AsyncEngine | None = field(default=None, init=False)
    session_factory: async_sessionmaker[AsyncSession] | None = field(
        default=None, init=False
    )

    def initialize(self) -> None:
        database_url = _build_database_url()
        if not database_url:
            self.engine = None
            self.session_factory = None
            return

        self.engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            future=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def get_db(self) -> AsyncIterator[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError(
                "Database is not configured. Set database_uri or database_* "
                "settings before using the API."
            )

        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


DBSessionManager = DatabaseSessionManager()

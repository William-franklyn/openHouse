from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base


def normalize_database_url(url: str) -> str:
    """Managed Postgres providers (Render, Heroku, ...) hand out a plain
    postgres:// or postgresql:// connection string with no driver in it.
    SQLAlchemy's async engine needs the driver named in the scheme, so a
    bare URL would otherwise fail to pick the (installed) asyncpg driver."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


class Database:
    def __init__(self, database_url: str):
        database_url = normalize_database_url(database_url)
        connect_args = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_async_engine(database_url, connect_args=connect_args)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

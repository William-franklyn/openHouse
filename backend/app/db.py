from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

# libpq-only query params some managed Postgres providers (Neon, Render,
# Heroku, ...) put in their connection strings. asyncpg's connect() has no
# such keyword arguments and raises TypeError if they're left in the URL -
# "needs SSL" has to be expressed via connect_args={"ssl": True} instead.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}


def normalize_database_url(url: str) -> tuple[str, dict]:
    """Returns (cleaned_url, extra_connect_args).

    Managed Postgres providers hand out a plain postgres:// or
    postgresql:// connection string with no async driver named - SQLAlchemy
    needs that in the scheme to pick asyncpg - and often append sslmode=
    (and sometimes channel_binding=), which asyncpg rejects outright. Both
    get normalized away here so a provider's connection string can be
    pasted in as-is.
    """
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif not url.startswith("postgresql+asyncpg://"):
        return url, {}

    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)

    needs_ssl = False
    kept_pairs = []
    for key, value in pairs:
        if key == "sslmode":
            needs_ssl = value.lower() not in ("disable", "")
            continue
        if key in _LIBPQ_ONLY_PARAMS:
            continue
        kept_pairs.append((key, value))

    cleaned_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(kept_pairs), parts.fragment)
    )
    return cleaned_url, ({"ssl": True} if needs_ssl else {})


class Database:
    def __init__(self, database_url: str):
        database_url, extra_connect_args = normalize_database_url(database_url)
        connect_args = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        connect_args.update(extra_connect_args)
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

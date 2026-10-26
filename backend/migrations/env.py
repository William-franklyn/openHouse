import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db import normalize_database_url
from app.models import Base

config = context.config
settings = get_settings()
# Managed Postgres providers (Neon, etc.) hand out a plain postgresql://
# URL with sslmode=/channel_binding= query params - asyncpg needs the
# +asyncpg dialect named explicitly and rejects those libpq-only params
# outright. db.py's app-server startup already normalizes this; migrations
# need the exact same treatment or they pick a driver that isn't even
# installed (psycopg) instead of failing closed with a clear message.
database_url, connect_args = normalize_database_url(settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

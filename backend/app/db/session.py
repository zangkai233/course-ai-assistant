from collections.abc import AsyncGenerator

from pgvector.psycopg import register_vector_async

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base


engine = create_async_engine(
    settings.database_url,

    pool_size=settings.db_pool_size,

    max_overflow=settings.db_max_overflow,

    pool_pre_ping=True,

    echo=False,
)


# Register PostgreSQL vector type with Psycopg
@event.listens_for(engine.sync_engine, "connect")
def register_vector_types(dbapi_connection, connection_record):
    dbapi_connection.run_async(register_vector_async)


SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:

    async with SessionLocal() as session:
        yield session


async def init_db() -> None:

    # Important: import models so SQLAlchemy knows the tables
    import app.db.models  # noqa

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()

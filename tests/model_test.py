from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sync_engine = create_engine(
    "sqlite:///./test.db", echo=False, connect_args={"timeout": 15}, poolclass=NullPool
)

async_engine = create_async_engine(
    "sqlite+aiosqlite:///./test.db",
    echo=False,
    connect_args={"timeout": 15},
    poolclass=NullPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=sync_engine,
)

TestingAsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

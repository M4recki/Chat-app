import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Database setup
# Prefer `DATABASE_URL` from environment (set by docker-compose / CI, or .env).
# Fallback to a sensible default for local development.
database_url = os.getenv("DATABASE_URL")
if not database_url:
    database_url = URL.create(
        drivername="postgresql",
        username="postgres",
        password="postgres",
        host="localhost",
        database="chat_app",
        port=5432,
    )

# Sync engine – kept for backward compatibility (context processors, tests)

engine = create_engine(
    database_url,
    pool_size=20,
    max_overflow=50,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations.

    Yields a database session that is automatically closed when the
    context manager exits.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """FastAPI dependency that yields a database session.

    Yields:
        Session: A SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Async engine – used in route handlers to avoid blocking the event loop
# ---------------------------------------------------------------------------

def _async_url(url: str | URL) -> str | URL:
    """Replace the database driver with its async counterpart."""
    if isinstance(url, URL):
        url_str = url.render_as_string(hide_password=False)
    else:
        url_str = url
    if url_str.startswith("postgresql://"):
        return url_str.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url_str.startswith("sqlite://"):
        return url_str.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url_str


async_engine = create_async_engine(
    _async_url(database_url),
    pool_size=20,
    max_overflow=50,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def async_session_scope():
    """Provide an async transactional scope around a series of operations.

    Yields an async database session that is automatically closed when the
    context manager exits.
    """
    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Async FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


Base = declarative_base()

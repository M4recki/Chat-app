import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from dotenv import load_dotenv

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
        database="Chat app",
        port=5432,
    )

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


Base = declarative_base()

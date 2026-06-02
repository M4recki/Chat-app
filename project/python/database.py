import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

# Database setup
# Prefer `DATABASE_URL` from environment (set by docker-compose / CI).
# Fallback to a sensible default for local development.
database_url = os.getenv(
    "DATABASE_URL",
    str(
        URL.create(
            drivername="postgresql",
            username="postgres",
            password="postgres",
            host="localhost",
            database="chatapp",
            port=5432,
        )
    ),
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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base = declarative_base()

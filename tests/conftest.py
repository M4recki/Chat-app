from contextlib import asynccontextmanager, contextmanager
from importlib import import_module
from os import environ
from pathlib import Path
from sys import path
from warnings import filterwarnings

import pytest
from fastapi.testclient import TestClient

filterwarnings("ignore", message="unclosed database", category=ResourceWarning)

project_root = Path(__file__).parent.parent
path.insert(0, str(project_root))

from tests.model_test import (
    async_engine as test_async_engine,
    sync_engine as test_engine,
    TestingAsyncSessionLocal,
    TestingSessionLocal,
)

prod_db = import_module("project.python.database")
prod_db.engine = test_engine
prod_db.SessionLocal = TestingSessionLocal
prod_db.async_engine = test_async_engine
prod_db.AsyncSessionLocal = TestingAsyncSessionLocal

from project.python import models

models.Base.metadata.create_all(bind=test_engine)

environ["TESTING"] = "1"
environ["CHAT_SECRET_KEY"] = "test-secret"

from project.python.main import app

client = TestClient(app)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations.

    Yields a database session for use in with block. The session is
    automatically committed or rolled back based on exception.
    """
    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def async_session_scope():
    """Provide an async transactional scope for test use."""
    async with TestingAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def clear_tables():
    """Reset test database by dropping and recreating all tables."""
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    """Provide a fresh DB session to tests and ensure teardown/cleanup."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        clear_tables()

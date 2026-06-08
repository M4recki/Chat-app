from importlib import import_module
from os import environ
from sys import path
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from contextlib import contextmanager

project_root = Path(__file__).parent.parent
path.insert(0, str(project_root))

from tests.model_test import (
    engine as test_engine,
    TestingSessionLocal,
)

prod_db = import_module("project.python.database")
prod_db.engine = test_engine
prod_db.SessionLocal = TestingSessionLocal

from project.python import models

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


def clear_tables():
    """Reset test database by dropping and recreating all tables."""
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    """Provide a fresh DB session to tests and ensure teardown/cleanup."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        clear_tables()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session
from database import Base
from contextlib import contextmanager
from model_test import engine
from project.python.main import app


# Test client


client = TestClient(app)


@contextmanager
def session_scope():
    """
    Provide a transactional scope around a series of operations.

    Yields a database session for use in with block. The session is
    automatically committed or rolled back based on exception.
    """
    session = sessionmaker(bind=engine)()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def clear_tables():
    """
    Clear contents of database tables before tests run.

    Drops contents of all tables to ensure clean state for each test.
    """
    with session_scope() as session:
        for table in Base.metadata.sorted_tables:
            session.execute(text("DELETE FROM user_test;"))
        session.commit()


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    """
    Return a new database session for a test.

    Each test method will use a separate transaction, and tables
    will be cleared between tests.
    """
    try:
        yield engine
    finally:
        clear_tables()

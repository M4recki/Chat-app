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
    with session_scope() as session:
        for table in Base.metadata.sorted_tables:
            session.execute(text(f"DELETE FROM user_test;"))
        session.commit()


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    try:
        yield engine
    finally:
        clear_tables()

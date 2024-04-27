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
    """_summary_

    Yields:
        _type_: _description_
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
    """_summary_"""
    with session_scope() as session:
        for table in Base.metadata.sorted_tables:
            session.execute(text("DELETE FROM user_test;"))
        session.commit()


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    """_summary_

    Yields:
        _type_: _description_
    """
    try:
        yield engine
    finally:
        clear_tables()

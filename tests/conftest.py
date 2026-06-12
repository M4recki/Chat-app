from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from importlib import import_module
from io import BytesIO
from os import environ
from pathlib import Path
from sys import path
from uuid import uuid4
from warnings import filterwarnings

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

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


def create_user(
    db: Session,
    name: str,
    surname: str,
    email: str,
    password: str,
    avatar_path: str,
):
    """Create a new user and save to the database.

    Args:
        db (Session): The database session
        name (str): The user's name
        surname (str): The user's surname
        email (str): The user's email
        password (str): The user's password
        avatar_path (str): Path to the user's avatar image

    Returns:
        User: The new user object
    """
    img = Image.open(avatar_path)

    if img.mode == "RGBA":
        img = img.convert("RGB")
    img_binary = BytesIO()
    img.save(img_binary, format="JPEG")
    img_binary = img_binary.getvalue()

    user = models.User(
        name=name,
        surname=surname,
        email=email,
        password=password,
        avatar=img_binary,
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    return user


def create_friendship(
    db,
    user1,
    user2,
    status: str,
    last_sent=None,
):
    """Create a friendship between two users."""

    rel = models.Friend(
        user1_id=user1.id,
        user2_id=user2.id,
        status=status,
        last_sent=last_sent or datetime.now(),
    )
    db.add(rel)
    db.commit()
    return rel


def create_channel(db, user1, user2):
    """Create a channel between two users."""
    channel = models.Channel(
        channel_id=str(uuid4()),
        user1_id=user1.id,
        user2_id=user2.id,
    )
    db.add(channel)
    db.commit()
    return channel


def create_message(db, content: str, channel_id: str, user):
    """Create a message in a channel."""
    msg = models.Message(
        content=content,
        channel_id=channel_id,
        created_at=datetime.now(),
        user_id=user.id,
    )
    db.add(msg)
    db.commit()
    return msg


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


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    """Provide a fresh DB session to tests and ensure teardown/cleanup."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        clear_tables()

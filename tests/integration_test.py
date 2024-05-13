from base64 import b64encode
from datetime import datetime
from PIL import Image
from io import BytesIO
from conftest import client, test_db_session
from sqlalchemy.orm import Session
from model_test import User, TestingSessionLocal


def create_user(
    db: Session, name: str, surname: str, email: str, password: str, avatar_path: str
):
    """
    Create a new user and save to the database.

    Encodes the user avatar to base64.

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
    img_binary = BytesIO()
    img.save(img_binary, format="JPEG")
    img_binary = img_binary.getvalue()

    user = User(
        name=name,
        surname=surname,
        email=email,
        password=password,
        avatar=b64encode(img_binary),
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    return user


def test_register_user(test_db_session):
    """
    Test registering a new user.

    Creates a test user and asserts a successful
    registration response and user is saved.

    Args:
        test_db_session: The test database session

    """
    db = TestingSessionLocal()
    user = create_user(
        db,
        "XXXXXXXX",
        "XXXXXXXX",
        "XXXXXXXX@gmail.com",
        "XXXXXXXX",
        "project/static/img/default avatar.jpg",
    )

    response = client.post(
        "/sign_up",
        data={
            "name": user.name,
            "surname": user.surname,
            "email": user.email,
            "password": user.password,
            "confirm_password": user.password,
            "terms_conditions": True,
        },
    )

    assert response.status_code == 200
    assert db.query(User).filter(User.email == user.email).first() is not None


def test_login_user(test_db_session):
    """
    Test logging in a registered user.

    Logs in a test user and asserts a successful
    login response.

    Args:
        test_db_session: The test database session
    """
    db = TestingSessionLocal()
    user = create_user(
        db,
        "XXXXXXXX",
        "XXXXXXXX",
        "XXXXXXXX@gmail.com",
        "XXXXXXXX",
        "project/static/img/default avatar.jpg",
    )

    response = client.post(
        "/sign_up",
        data={
            "name": user.name,
            "surname": user.surname,
            "email": user.email,
            "password": user.password,
            "confirm_password": user.password,
            "terms_conditions": True,
        },
    )

    assert response.status_code == 200

    login_data = {
        "email": user.email,
        "password": user.password,
    }

    response = client.post("/login", data=login_data)
    assert response.status_code == 200
    assert db.query(User).filter(User.email == user.email).first() is not None

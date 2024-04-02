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
    """_summary_

    Args:
        db (Session): _description_
        name (str): _description_
        surname (str): _description_
        email (str): _description_
        password (str): _description_
        avatar_path (str): _description_

    Returns:
        _type_: _description_
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
    """_summary_

    Args:
        test_db_session (_type_): _description_
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
    """_summary_

    Args:
        test_db_session (_type_): _description_
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

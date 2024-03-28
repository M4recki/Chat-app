from base64 import b64encode
from datetime import datetime
from PIL import Image
from io import BytesIO
from conftest import client, test_db_session
from sqlalchemy.orm import Session
from model_test import User, TestingSessionLocal


def test_register_user(test_db_session):
    name = "XXXXXXXX"
    surname = "XXXXXXXX"
    email = "XXXXXXXX@gmail.com"
    password = "XXXXXXXX"
    avatar = "XXXXXXXX"
    created_at = datetime.now()

    img = Image.open("project/static/img/default avatar.jpg")
    img_binary = BytesIO()
    img.save(img_binary, format="JPEG")
    img_binary = img_binary.getvalue()

    user_data = {
        "name": name,
        "surname": surname,
        "email": email,
        "password": password,
        "confirm_password": password,
        "terms_conditions": True,
    }

    response = client.post("/sign_up", data=user_data)

    assert response.status_code == 200

    db = TestingSessionLocal()

    test_user = User(
        name=name,
        surname=surname,
        email=email,
        password=password,
        avatar=b64encode(img_binary),
        created_at=created_at,
    )
    db.add(test_user)
    db.commit()

    user = db.query(User).filter(User.email == email).first()

    assert user is not None
    assert user.name == user_data["name"]
    assert user.surname == user_data["surname"]
    assert user.email == user_data["email"]
    assert user.password == user_data["password"]
    assert user.avatar == b64encode(img_binary)

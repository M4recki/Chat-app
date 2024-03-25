from config import client, TestingSessionLocal
from base64 import b64encode, encode
from model_test import users_test


def test_register_user():
    user_data = {
        "name": "XXXXXXXX",
        "surname": "XXXXXXXX",
        "email": "XXXXXXXX@gmail.com",
        "password": "XXXXXXXX",
        "confirm_password": "XXXXXXXX",
        "terms_conditions": True,
        "avatar": b64encode(b"XXXXXXXX").decode("utf-8"),
        "created_at": "2024-03-21T00:00:00",
    }

    response = client.post("/sign_up", data=user_data)

    assert response.status_code == 200

    db = TestingSessionLocal()

    user = db.query(users_test).filter(users_test.email == user_data["email"]).first()

    assert user is not None
    assert user.name == user_data["name"]
    assert user.surname == user_data["surname"]
    assert user.email == user_data["email"]
    assert user.password == user_data["password"]
    assert user.avatar == user_data["avatar"]
    assert user.created_at == user_data["created_at"]

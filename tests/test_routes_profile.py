from conftest import (
    DEFAULT_AVATAR,
    TEST_PASSWORD,
    authed_client,
    create_user,
)

from project.python.routes.helpers import generate_csrf_token
from tests.model_test import TestingSessionLocal


def test_update_profile_page_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Update",
        "Profile",
        "update-profile@example.com",
    )

    local_client = authed_client(user)
    response = local_client.get("/update_profile")
    assert response.status_code == 200


def test_update_profile_data_password_mismatch():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "UP",
        "User",
        "up-user@example.com",
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        "/update_profile",
        data={
            "name": "Updated",
            "surname": "User",
            "email": "up-user@example.com",
            "password": "NewPass1",
            "confirm_password": "Different1",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200


def test_update_profile_data_non_alphanumeric_password():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "UP2",
        "User",
        "up2-user@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/update_profile",
        data={
            "name": "Updated",
            "surname": "User",
            "email": "up2-user@example.com",
            "password": TEST_PASSWORD,
            "confirm_password": TEST_PASSWORD,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200


def test_update_profile_data_success():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "UP3",
        "User",
        "up3-user@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/update_profile",
        data={
            "name": "Updated",
            "surname": "User",
            "email": "up3-user@example.com",
            "password": "NewPass1",
            "confirm_password": "NewPass1",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200


def test_update_profile_avatar_jpeg():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Avatar",
        "Test",
        "avatar-test@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    img_path = DEFAULT_AVATAR
    with open(img_path, "rb") as f:
        response = local_client.post(
            "/update_profile",
            data={
                "name": "Avatar",
                "surname": "Test",
                "email": "avatar-test@example.com",
                "password": "Password1",
                "confirm_password": "Password1",
                "csrf_token": csrf,
            },
            files={"avatar": ("avatar.jpg", f, "image/jpeg")},
        )

    assert response.status_code == 200


def test_update_profile_avatar_wrong_type():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Avatar2",
        "Test",
        "avatar-test2@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/update_profile",
        data={
            "name": "Avatar",
            "surname": "Test",
            "email": "avatar-test2@example.com",
            "password": "Password1",
            "confirm_password": "Password1",
            "csrf_token": csrf,
        },
        files={"avatar": ("avatar.gif", b"fake-gif-data", "image/gif")},
    )

    assert response.status_code == 200


def test_update_profile_invalid_email():
    db = TestingSessionLocal()
    user = create_user(db, "UP", "Email", "up-email@example.com")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        "/update_profile",
        data={
            "email": "not-an-email",
            "name": "UP",
            "surname": "Email",
            "password": "Password1",
            "confirm_password": "Password1",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    assert "Invalid email format" in response.text


def test_update_profile_short_password():
    db = TestingSessionLocal()
    user = create_user(db, "UP", "Pwd", "up-pwd@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        "/update_profile",
        data={
            "email": "up-pwd@example.com",
            "name": "UP",
            "surname": "Pwd",
            "password": "Short1",
            "confirm_password": "Short1",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    assert "Password must be at least 8 characters long" in response.text


def test_update_profile_large_avatar():
    db = TestingSessionLocal()
    user = create_user(db, "UP", "Avatar", "up-avatar-lg@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    large_data = b"\xff\xd8\xff\xe0" + b"\x00" * 5300000

    response = local_client.post(
        "/update_profile",
        data={
            "email": "up-avatar-lg@example.com",
            "name": "UP",
            "surname": "Avatar",
            "password": "Password1",
            "confirm_password": "Password1",
            "csrf_token": csrf,
        },
        files={"avatar": ("avatar.jpg", large_data, "image/jpeg")},
    )

    assert response.status_code == 200
    assert "Avatar must be smaller than 5 MB" in response.text

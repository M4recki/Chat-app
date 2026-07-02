from conftest import (
    client,
    create_user,
    DEFAULT_AVATAR,
    TEST_PASSWORD,
)
from project.python.main import app
from project.python.routes.helpers import generate_csrf_token
from project.python.routes.email import generate_password_reset_token
from project.python.rate_limit import clear_rate_limiter
from fastapi.testclient import TestClient
from tests.model_test import TestingSessionLocal


def test_logout_clears_cookie():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Logout",
        "Tester",
        "logout-tester@example.com",
    )

    from conftest import set_access_token as _sat

    _sat(user.id)
    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 303
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "expires=" in set_cookie_header.lower()


def test_logout_no_token():
    client.cookies.clear()
    response = client.get("/logout")
    assert response.status_code == 401


def test_login_wrong_password():
    db = TestingSessionLocal()
    _ = create_user(
        db,
        "Login",
        "Wrong",
        "login-wrong@example.com",
    )
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={
            "email": "login-wrong@example.com",
            "password": "wrong_pass",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_sign_up_duplicate_email():
    db = TestingSessionLocal()
    create_user(
        db,
        "Existing",
        "User",
        "existing@example.com",
    )
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "New",
            "surname": "User",
            "email": "existing@example.com",
            "password": "NewPass123",
            "confirm_password": "NewPass123",
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200


def test_sign_up_password_not_alphanumeric():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "Test",
            "surname": "User",
            "email": "alphanum@example.com",
            "password": TEST_PASSWORD,
            "confirm_password": TEST_PASSWORD,
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_sign_up_and_login():
    clear_rate_limiter()
    local_client = TestClient(
        app, raise_server_exceptions=False, follow_redirects=False
    )
    csrf_token = generate_csrf_token(0)
    response = local_client.post(
        "/sign_up",
        data={
            "name": "Full",
            "surname": "Cycle",
            "email": "full-cycle@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303
    csrf_token = generate_csrf_token(0)
    login_response = local_client.post(
        "/login",
        data={
            "email": "full-cycle@example.com",
            "password": "StrongPass1",
            "csrf_token": csrf_token,
        },
    )
    assert login_response.status_code == 303


def test_sign_up_password_mismatch():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "Test",
            "surname": "User",
            "email": "unique@example.com",
            "password": "Pass123",
            "confirm_password": "Different456",
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_sign_up_invalid_email():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "Bad",
            "surname": "Email",
            "email": "not-an-email",
            "password": TEST_PASSWORD,
            "confirm_password": TEST_PASSWORD,
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_forgot_password_page_returns_200():
    response = client.get("/forgot_password")
    assert response.status_code == 200


def test_forgot_password_invalid_email():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/forgot_password",
        data={"email": "not-an-email", "csrf_token": csrf_token},
    )
    assert response.status_code == 200


def test_forgot_password_valid_email():
    db = TestingSessionLocal()
    create_user(db, "Reset", "User", "reset-test@example.com")
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/forgot_password",
        data={"email": "reset-test@example.com", "csrf_token": csrf_token},
    )
    assert response.status_code == 200


def test_forgot_password_unregistered_email():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/forgot_password",
        data={"email": "nobody@example.com", "csrf_token": csrf_token},
    )
    assert response.status_code == 200


def test_reset_password_page_valid_token():
    token = generate_password_reset_token("valid@example.com")
    response = client.get(f"/reset_password/{token}")
    assert response.status_code == 200


def test_reset_password_page_invalid_token():
    response = client.get("/reset_password/invalid-token-here")
    assert response.status_code == 200


def test_reset_password_post_success():
    db = TestingSessionLocal()
    create_user(
        db, "Reset", "Post", "reset-post@example.com", "OldPass123", DEFAULT_AVATAR
    )
    token = generate_password_reset_token("reset-post@example.com")
    csrf_token = generate_csrf_token(0)

    response = client.post(
        f"/reset_password/{token}",
        data={
            "password": "NewSecurePass456",
            "confirm_password": "NewSecurePass456",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200


def test_reset_password_post_password_mismatch():
    token = generate_password_reset_token("mismatch@example.com")
    csrf_token = generate_csrf_token(0)
    response = client.post(
        f"/reset_password/{token}",
        data={
            "password": TEST_PASSWORD,
            "confirm_password": "Different456",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_reset_password_post_short_password():
    token = generate_password_reset_token("short@example.com")
    csrf_token = generate_csrf_token(0)
    response = client.post(
        f"/reset_password/{token}",
        data={
            "password": "Short1",
            "confirm_password": "Short1",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_reset_password_post_invalid_token():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/reset_password/bad-token-here",
        data={
            "password": TEST_PASSWORD,
            "confirm_password": TEST_PASSWORD,
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200

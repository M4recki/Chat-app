from itsdangerous import URLSafeTimedSerializer as Serializer
from conftest import client
from project.python.routes import generate_csrf_token
from project.python.settings import settings
from tests.integration_test import create_user
from tests.model_test import TestingSessionLocal


def _login_and_token():
    db = TestingSessionLocal()
    user = create_user(
        db, "Contract", "Test", "contract@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    client.cookies.set("access_token", token)
    return user


def test_index_response_shape():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_login_page_response_shape():
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_signup_page_response_shape():
    response = client.get("/sign_up")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_contact_page_response_shape():
    response = client.get("/contact")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_logout_response_shape():
    _login_and_token()
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert "set-cookie" in response.headers


def test_chatbot_json_response_shape():
    user = _login_and_token()
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    client.cookies.set("access_token", token)
    csrf = generate_csrf_token(user.id)

    response = client.post(
        "/chatbot",
        data={"message": "echo: hello", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")
    payload = response.json()
    assert "message" in payload
    assert "response" in payload
    assert "created_at" in payload
    assert isinstance(payload["message"], str)
    assert isinstance(payload["response"], str)
    assert isinstance(payload["created_at"], str)


def test_unauthenticated_returns_401():
    client.cookies.clear()
    response = client.get("/single_chat")
    assert response.status_code == 401


def test_404_returns_html():
    response = client.get("/nonexistent-route", headers={"Accept": "text/html"})
    assert response.status_code == 404


def test_login_wrong_password_content_type():
    db = TestingSessionLocal()
    create_user(
        db, "Login", "Wrong", "login-wrong-ct@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    response = client.post(
        "/login",
        data={"email": "login-wrong-ct@example.com", "password": "badpass"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

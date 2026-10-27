from conftest import (
    authed_client,
    client,
    create_user,
)
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer as Serializer

from project.python.chatbot_utils import ChatbotServiceError, chatbot_json_error
from project.python.main import app
from project.python.models import User
from project.python.routes.helpers import generate_csrf_token
from project.python.settings import settings
from tests.model_test import TestingSessionLocal


def test_chatbot_ajax_response():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "User",
        "chat-user@example.com",
    )

    from conftest import set_access_token as _sat

    _sat(user.id)
    csrf = generate_csrf_token(user.id)

    response = client.post(
        "/chatbot",
        data={"message": "echo: hello", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "echo: hello"
    assert payload["response"] == "hello"
    assert payload["created_at"]


def test_chatbot_requires_auth_returns_401_json():
    client.cookies.clear()

    response = client.post(
        "/chatbot",
        data={"message": "hi"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["status_code"] == 401
    assert payload["title"] == "Unauthorized"


def test_chatbot_expired_token_returns_401_json(monkeypatch):
    monkeypatch.setattr("project.python.settings.settings.token_max_age", 0)
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    local_client = TestClient(app, raise_server_exceptions=False)
    local_client.cookies.set("access_token", token)

    response = local_client.post(
        "/chatbot",
        data={"message": "hi"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["status_code"] == 401
    assert payload["title"] == "Unauthorized"


def test_chatbot_invalid_token_returns_401_json():
    local_client = TestClient(app, raise_server_exceptions=False)
    local_client.cookies.set("access_token", "forged-token")
    response = local_client.post(
        "/chatbot",
        data={"message": "hi"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["status_code"] == 401
    assert payload["title"] == "Unauthorized"


def test_chatbot_deleted_user_returns_401_json():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Delete",
        "Me",
        "deleted-user@example.com",
    )

    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    db.query(User).filter(User.id == user.id).delete()
    db.commit()

    local_client = TestClient(app, raise_server_exceptions=False)
    local_client.cookies.set("access_token", token)
    response = local_client.post(
        "/chatbot",
        data={"message": "hi"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["status_code"] == 401
    assert payload["title"] == "Unauthorized"


def test_chatbot_missing_message_validation():
    from project.python.rate_limit import clear_rate_limiter

    clear_rate_limiter()
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Missing",
        "chat-missing@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/chatbot",
        data={"csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 422


def test_chatbot_empty_message_returns_validation():
    result = chatbot_json_error(
        400,
        {
            "error": "validation",
            "details": {"message": "Message cannot be empty"},
        },
    )
    assert result.status_code == 400
    assert b"Message cannot be empty" in result.body


def test_chatbot_error_returns_502(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Err",
        "chat-err@example.com",
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    def mock_response():
        raise Exception("mock failure")

    monkeypatch.setattr(
        "project.python.routes.chatbot.chatbot_response",
        mock_response,
    )

    response = local_client.post(
        "/chatbot",
        data={"message": "hi", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 502


def test_chatbot_chatbot_service_error_html(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "ErrH",
        "chat-err-html@example.com",
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    def mock_response():
        raise Exception("mock failure")

    monkeypatch.setattr(
        "project.python.routes.chatbot.chatbot_response",
        mock_response,
    )

    response = local_client.post(
        "/chatbot",
        data={"message": "hi", "csrf_token": csrf},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_chatbot_page_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Page",
        "chat-page@example.com",
    )
    local_client = authed_client(user)
    response = local_client.get("/chatbot")
    assert response.status_code == 200


def test_chatbot_success_non_ajax():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "CS",
        "User",
        "cs-user@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/chatbot",
        data={"message": "echo: hello", "csrf_token": csrf},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_clear_chatbot_messages():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Clear",
        "Chat",
        "clear-chat@example.com",
    )

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post("/clear_chatbot_messages", data={"csrf_token": csrf})

    assert response.status_code == 200


def test_chatbot_service_error_non_ajax(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(db, "Chat", "SvcErr", "chat-svcerr@example.com")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    def mock_response(*_a, **_kw):
        raise ChatbotServiceError("service error")

    monkeypatch.setattr(
        "project.python.routes.chatbot.chatbot_response",
        mock_response,
    )

    response = local_client.post(
        "/chatbot",
        data={"message": "hi", "csrf_token": csrf},
    )

    assert response.status_code == 200
    assert "service error" in response.text


def test_chatbot_page_not_logged_in():
    response = client.get("/chatbot")
    assert response.status_code == 401


def test_clear_chatbot_messages_not_logged_in():
    response = client.post("/clear_chatbot_messages")
    assert response.status_code == 401

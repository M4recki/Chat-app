from conftest import (
    client,
    authed_client,
    create_user,
    create_friendship,
)
from project.python.models import FriendStatus
from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient
from project.python.main import app
from project.python.settings import settings
from tests.model_test import TestingSessionLocal


def test_login_page_returns_200():
    response = client.get("/login")
    assert response.status_code == 200


def test_sign_up_page_returns_200():
    response = client.get("/sign_up")
    assert response.status_code == 200


def test_authenticated_page_expired_token_returns_401(monkeypatch):
    monkeypatch.setattr("project.python.settings.settings.token_max_age", -1)
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    local_client = TestClient(app, raise_server_exceptions=False)
    local_client.cookies.set("access_token", token)
    response = local_client.get("/search_user")

    assert response.status_code == 401
    assert "text/html" in response.headers.get("content-type", "")


def test_authenticated_page_returns_401_html():
    client.cookies.clear()
    response = client.get("/search_user")
    assert response.status_code == 401
    assert "text/html" in response.headers.get("content-type", "")


def test_friend_requests_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Friend",
        "Req",
        "friend-req@example.com",
    )

    local_client = authed_client(user)
    response = local_client.get("/friend_requests")
    assert response.status_code == 200


def test_friend_requests_with_pending():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FR",
        "User",
        "fr-user@example.com",
    )
    requester = create_user(
        db,
        "FR",
        "Requester",
        "fr-requester@example.com",
    )

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.get("/friend_requests")

    assert response.status_code == 200

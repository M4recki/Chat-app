from starlette.requests import Request
from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient

from conftest import client, create_user
from project.python.main import app, get_rate_limit_identifier
from project.python.settings import settings
from project.python.routes.helpers import generate_csrf_token
from project.python.rate_limit import clear_rate_limiter
from tests.model_test import TestingSessionLocal


def test_login_rate_limit_headers_present():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={
            "email": "unknown@example.com",
            "password": "bad",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_search_user_rate_limit_429_headers():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Rate",
        "Limiter",
        "rate-limit@example.com",
    )

    from conftest import set_access_token as _sat

    _sat(user.id, target_client=local_client)

    limit = settings.rate_limit_search_max_requests
    for _ in range(limit):
        response = local_client.get("/search_user")
        assert response.status_code == 200

    response = local_client.get("/search_user")

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.headers.get("X-RateLimit-Remaining") == "0"


def test_chatbot_rate_limit_429_json():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Rater",
        "chat-rater@example.com",
    )

    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local_client.cookies.set("access_token", token)
    csrf = generate_csrf_token(user.id)
    limit = settings.rate_limit_chatbot_max_requests

    for _ in range(limit):
        response = local_client.post(
            "/chatbot",
            data={"message": "echo: test", "csrf_token": csrf},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
    response = local_client.post(
        "/chatbot",
        data={"message": "echo: test", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["status_code"] == 429
    assert payload["title"] == "Too many requests"


def test_login_rate_limit_429():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    csrf_token = generate_csrf_token(0)
    limit = settings.rate_limit_login_max_requests
    for _ in range(limit):
        response = local_client.post(
            "/login",
            data={
                "email": "spam@example.com",
                "password": "wrong",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200

    response = local_client.post(
        "/login",
        data={
            "email": "spam@example.com",
            "password": "wrong",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 429


def test_rate_limit_429_contains_all_headers():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    limit = settings.rate_limit_search_max_requests
    for _ in range(limit):
        local_client.get("/search_user")
    response = local_client.get("/search_user")

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def _make_request(cookies: dict | None = None):
    headers = []
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_str.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": ("127.0.0.1", 8000),
    }
    return Request(scope)


def test_get_rate_limit_identifier_no_token():
    request = _make_request()
    identifier = get_rate_limit_identifier(request)

    assert identifier is None


def test_get_rate_limit_identifier_valid_token():
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": 42})
    request = _make_request({"access_token": token})
    identifier = get_rate_limit_identifier(request)

    assert identifier == "user:42"


def test_get_rate_limit_identifier_no_user_id():
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"not_user_id": 99})
    request = _make_request({"access_token": token})
    identifier = get_rate_limit_identifier(request)
    assert identifier is None


def test_get_rate_limit_identifier_expired_token(monkeypatch):
    monkeypatch.setattr("project.python.settings.settings.token_max_age", -1)
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    request = _make_request({"access_token": token})
    identifier = get_rate_limit_identifier(request)

    assert identifier is None

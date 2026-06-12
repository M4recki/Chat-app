from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient
from conftest import client
from project.python.main import app
from project.python.settings import settings
from project.python.routes import generate_csrf_token
from project.python.rate_limit import clear_rate_limiter
from conftest import create_user
from tests.model_test import TestingSessionLocal
from project.python.models import Friend
from sqlalchemy import or_


def _auth_client():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Sec",
        "Test",
        "sec@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local = TestClient(app, raise_server_exceptions=False)
    local.cookies.set("access_token", token)
    return local, user


def _clear_rate_limiter():
    clear_rate_limiter()


#  SQL injection


def test_sql_injection_login_email():
    _clear_rate_limiter()
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={"email": "' OR 1=1 --", "password": "test", "csrf_token": csrf_token},
    )
    assert response.status_code == 200


def test_sql_injection_signup_name():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "'; DROP TABLE users; --",
            "surname": "Hacker",
            "email": "sql-inj@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code in (200, 303)


def test_sql_injection_search():
    _clear_rate_limiter()
    local, _ = _auth_client()
    response = local.get("/search_user?q=1' OR '1'='1")
    assert response.status_code == 200


#  XSS


def test_xss_in_message():
    _clear_rate_limiter()
    local, user = _auth_client()
    csrf = generate_csrf_token(user.id)
    response = local.post(
        "/chatbot",
        data={"message": "<script>alert('xss')</script>", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code in (200, 502)
    if response.status_code == 200:
        data = response.json()
        assert "<script>" not in data.get("response", "")


def test_xss_in_signup():
    _clear_rate_limiter()
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": "<script>alert(1)</script>",
            "surname": "<img src=x onerror=alert(1)>",
            "email": "xss-test@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code in (200, 303)


#  Token manipulation


def test_invalid_token_returns_401():
    local = TestClient(app, raise_server_exceptions=False)
    local.cookies.set("access_token", "forged-token")
    response = local.get("/single_chat")
    assert response.status_code == 401


def test_expired_token_returns_401(monkeypatch):
    monkeypatch.setattr("project.python.routes.settings.token_max_age", -1)
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Expired",
        "Token",
        "expired-token@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local = TestClient(app, raise_server_exceptions=False)
    local.cookies.set("access_token", token)
    response = local.get("/single_chat")
    assert response.status_code == 401


def test_token_for_other_user():
    db = TestingSessionLocal()
    user_a = create_user(
        db,
        "Token",
        "A",
        "token-a@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    user_b = create_user(
        db,
        "Token",
        "B",
        "token-b@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token_a = serializer.dumps({"user_id": user_a.id})
    local = TestClient(app, raise_server_exceptions=False)
    local.cookies.set("access_token", token_a)
    response = local.post(
        f"/add_friend/{user_b.id}",
        data={"csrf_token": generate_csrf_token(user_a.id)},
    )
    assert response.status_code == 200

    # Verify the friend request was created for
    # user_a → user_b, not the other way
    db_check = TestingSessionLocal()
    friendship = (
        db_check.query(Friend)
        .filter(
            or_(
                (Friend.user1_id == user_a.id) & (Friend.user2_id == user_b.id),
                (Friend.user1_id == user_b.id) & (Friend.user2_id == user_a.id),
            )
        )
        .first()
    )
    assert friendship is not None
    assert friendship.user1_id == user_a.id
    assert friendship.user2_id == user_b.id


#  Rate limit enforcement


def test_rate_limit_enforces_limit():
    with TestClient(app, raise_server_exceptions=False) as local:
        _clear_rate_limiter()
        responses = []
        for _ in range(50):
            resp = local.get("/search_user?q=test")
            responses.append(resp.status_code)

    limited = [r for r in responses if r == 429]
    assert len(limited) > 0, "Rate limiter did not block any requests"


#  Cookie flags


def test_logout_clears_cookie_with_flags():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Cookie",
        "Flags",
        "cookie-flags@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local = TestClient(
        app,
        raise_server_exceptions=False,
        follow_redirects=False,
    )
    local.cookies.set("access_token", token)
    response = local.get("/logout")
    assert response.status_code == 303
    cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in cookie
    assert "Max-Age=0" in cookie or "expires=" in cookie.lower()

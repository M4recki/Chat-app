from fastapi.testclient import TestClient
from conftest import client, create_user
from project.python.main import app
from project.python.models import User
from project.python.settings import settings
from project.python.rate_limit import clear_rate_limiter
from itsdangerous import URLSafeTimedSerializer as Serializer
from project.python.routes import generate_csrf_token
from tests.model_test import TestingSessionLocal


def test_register_user(test_db_session):
    """
    Test registering a new user.

    Creates a test user and asserts a successful
    registration response and user is saved.

    Args:
        test_db_session: The test database session

    """
    db = TestingSessionLocal()
    user = create_user(
        db,
        "XXXXXXXX",
        "XXXXXXXX",
        "XXXXXXXX@gmail.com",
        "XXXXXXXX",
        "project/static/img/default avatar.png",
    )

    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": user.name,
            "surname": user.surname,
            "email": user.email,
            "password": user.password,
            "confirm_password": user.password,
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert db.query(User).filter(User.email == user.email).first() is not None


def test_login_user(test_db_session):
    """
    Test logging in a registered user.

    Logs in a test user and asserts a successful
    login response.
    """
    db = TestingSessionLocal()
    user = create_user(
        db,
        "XXXXXXXX",
        "XXXXXXXX",
        "XXXXXXXX@gmail.com",
        "XXXXXXXX",
        "project/static/img/default avatar.png",
    )

    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/sign_up",
        data={
            "name": user.name,
            "surname": user.surname,
            "email": user.email,
            "password": user.password,
            "confirm_password": user.password,
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200

    csrf_token = generate_csrf_token(0)
    login_data = {
        "email": user.email,
        "password": user.password,
        "csrf_token": csrf_token,
    }

    response = client.post("/login", data=login_data)
    assert response.status_code == 200
    assert db.query(User).filter(User.email == user.email).first() is not None


#  Full flow: register -> login -> action -> logout


def test_full_flow_register_login_action_logout():
    clear_rate_limiter()
    local = TestClient(
        app,
        raise_server_exceptions=False,
        follow_redirects=False,
    )
    email = "full-flow@example.com"
    password = "StrongPass1"

    csrf_token = generate_csrf_token(0)
    resp = local.post(
        "/sign_up",
        data={
            "name": "Full",
            "surname": "Flow",
            "email": email,
            "password": password,
            "confirm_password": password,
            "terms_conditions": "on",
            "csrf_token": csrf_token,
        },
    )
    assert resp.status_code == 303

    csrf_token = generate_csrf_token(0)
    resp = local.post(
        "/login", data={"email": email, "password": password, "csrf_token": csrf_token}
    )
    assert resp.status_code == 303

    resp = local.get("/single_chat")
    assert resp.status_code == 200

    resp = local.get("/logout")
    assert resp.status_code == 303

    resp = local.get("/single_chat")
    assert resp.status_code == 401


#  Expired token mid-session


def test_expired_token_mid_session(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Mid",
        "Session",
        "mid-session@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local = TestClient(app, raise_server_exceptions=False)
    local.cookies.set("access_token", token)

    resp = local.get("/single_chat")
    assert resp.status_code == 200

    monkeypatch.setattr("project.python.routes.settings.token_max_age", -1)
    resp = local.get("/single_chat")
    assert resp.status_code == 401


#  Concurrent sessions for same user


def test_concurrent_sessions_same_user():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Concurrent",
        "User",
        "concurrent@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})

    sessions = []
    for _ in range(3):
        s = TestClient(app, raise_server_exceptions=False)
        s.cookies.set("access_token", token)
        sessions.append(s)

    for s in sessions:
        resp = s.get("/single_chat")
        assert resp.status_code == 200

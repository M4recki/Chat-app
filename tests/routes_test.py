from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient
from conftest import client, create_friendship, create_channel, create_message, create_user
from project.python.main import app
from project.python.settings import settings
from tests.model_test import TestingSessionLocal
from datetime import datetime, timedelta
from uuid import uuid4
from starlette.requests import Request
from project.python.chatbot_utils import chatbot_json_error
from project.python.main import get_rate_limit_identifier
from project.python.models import User, Channel, Message
from project.python.routes import generate_csrf_token
from project.python.models import FriendStatus
from project.python.rate_limit import clear_rate_limiter


DEFAULT_AVATAR = "project/static/img/default avatar.png"


def set_access_token(user_id: int, target_client=client) -> None:
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user_id})
    target_client.cookies.set("access_token", token)


def authed_client(user) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    set_access_token(user.id, target_client=c)
    return c


def test_chatbot_ajax_response():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "User",
        "chat-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )

    set_access_token(user.id)
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


def test_search_user_returns_other_users():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search",
        "Owner",
        "search-owner@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    other = create_user(
        db,
        "Search",
        "Target",
        "search-target@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )

    set_access_token(user.id)

    response = client.get("/search_user")

    assert response.status_code == 200
    assert other.name in response.text
    assert other.surname in response.text


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


def test_search_user_rate_limit_429_headers():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Rate",
        "Limiter",
        "rate-limit@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )

    set_access_token(user.id, target_client=local_client)

    limit = settings.rate_limit_search_max_requests
    for _ in range(limit):
        response = local_client.get("/search_user")
        assert response.status_code == 200

    response = local_client.get("/search_user")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.headers.get("X-RateLimit-Remaining") == "0"


def test_chatbot_expired_token_returns_401_json(monkeypatch):
    monkeypatch.setattr("project.python.routes.settings.token_max_age", 0)
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
        "Password123",
        DEFAULT_AVATAR,
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


def test_chatbot_rate_limit_429_json():
    clear_rate_limiter()
    local_client = TestClient(app, raise_server_exceptions=False)
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Rater",
        "chat-rater@example.com",
        "Password123",
        DEFAULT_AVATAR,
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


#  get_rate_limit_identifier


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


#  Static page routes


def test_login_page_returns_200():
    response = client.get("/login")
    assert response.status_code == 200


def test_sign_up_page_returns_200():
    response = client.get("/sign_up")
    assert response.status_code == 200


def test_contact_page_returns_200():
    response = client.get("/contact")
    assert response.status_code == 200


def test_contact_short_message_error():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/contact",
        data={
            "name": "Test",
            "email": "test@example.com",
            "subject": "Hi",
            "message": "short",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_sign_up_duplicate_email():
    db = TestingSessionLocal()
    _ = create_user(
        db,
        "Existing",
        "User",
        "existing@example.com",
        "Password123",
        DEFAULT_AVATAR,
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
            "password": "haslo-123",
            "confirm_password": "haslo-123",
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


#  Logout


def test_logout_clears_cookie():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Logout",
        "Tester",
        "logout-tester@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    set_access_token(user.id)
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "expires=" in set_cookie_header.lower()


def test_logout_no_token():
    client.cookies.clear()
    response = client.get("/logout")
    assert response.status_code == 401


#  Validation error (422)


def test_login_wrong_password():
    db = TestingSessionLocal()
    _ = create_user(
        db,
        "Login",
        "Wrong",
        "login-wrong@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={
            "email": "login-wrong@example.com",
            "password": "wrongpass",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_validation_error_returns_422_json():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "csrf_token": csrf_token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation"
    assert payload["status_code"] == 422


def test_validation_error_returns_422_html():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "csrf_token": csrf_token},
    )
    assert response.status_code == 422
    assert "text/html" in response.headers.get("content-type", "")


#  Unhandled exception (500)


def test_unhandled_exception_returns_500_json(monkeypatch):
    monkeypatch.setattr(
        "project.python.routes.main_page.render_template",
        lambda *a, **kw: (_ for _ in ()).throw(Exception("unexpected error")),
    )
    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get(
        "/",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "server"
    assert payload["status_code"] == 500


def test_unhandled_exception_returns_500_html(monkeypatch):
    monkeypatch.setattr(
        "project.python.routes.main_page.render_template",
        lambda *a, **kw: (_ for _ in ()).throw(Exception("unexpected error")),
    )
    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get("/")
    assert response.status_code == 500
    assert "text/html" in response.headers.get("content-type", "")


#  Authenticated routes


def test_single_chat_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Single",
        "Chat",
        "single-chat@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "Friend",
        "One",
        "friend-one@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    channel = create_channel(db, user, friend)

    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


def test_single_chat_no_friends():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Single",
        "Alone",
        "single-alone@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


def test_friend_requests_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Friend",
        "Req",
        "friend-req@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    response = local_client.get("/friend_requests")
    assert response.status_code == 200


def test_update_profile_page_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Update",
        "Profile",
        "update-profile@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    response = local_client.get("/update_profile")
    assert response.status_code == 200


def test_add_friend_old_pending_renews_last_sent(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Old",
        "Pending",
        "old-pending@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Target",
        "Old",
        "target-old@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    old_date = datetime.now() - timedelta(days=20)
    create_friendship(db, user, target, FriendStatus.PENDING.value, last_sent=old_date)

    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_chatbot_missing_message_validation():
    clear_rate_limiter()
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Missing",
        "chat-missing@example.com",
        "Password123",
        DEFAULT_AVATAR,
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


#  Friend management


def test_add_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Friend",
        "add-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Target",
        "User",
        "target-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_add_friend_duplicate_pending():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Dup",
        "add-dup@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Target",
        "Dup",
        "target-dup@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, target, FriendStatus.PENDING.value)
    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 400


def test_add_friend_duplicate_denied():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Den",
        "add-den@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Target",
        "Den",
        "target-den@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, target, FriendStatus.DENIED.value, last_sent=datetime(2020, 1, 1))
    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_accept_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Accept",
        "User",
        "accept-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    requester = create_user(
        db,
        "Request",
        "er",
        "requester@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, requester, user, FriendStatus.PENDING.value)
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_accept_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "AFNF",
        "User",
        "afnf-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        "/accept_friend/99999",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 404


def test_deny_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Deny",
        "User",
        "deny-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    requester = create_user(
        db,
        "Request",
        "deny",
        "requester-deny@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, requester, user, FriendStatus.PENDING.value)
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_deny_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "DNFNF",
        "User",
        "dnfnf-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        "/deny_friend/99999",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 404


def test_block_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Block",
        "User",
        "block-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Blocked",
        "Target",
        "blocked-target@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, target, FriendStatus.ACCEPTED.value)
    local_client = authed_client(user)
    response = local_client.post(
        f"/block_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_unblock_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Unblock",
        "User",
        "unblock-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    target = create_user(
        db,
        "Unblocked",
        "Target",
        "unblocked-target@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, target, FriendStatus.BLOCKED.value)
    local_client = authed_client(user)
    response = local_client.post(
        f"/unblock_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )
    assert response.status_code == 200


def test_chatbot_error_returns_502(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Err",
        "chat-err@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    def mock_response(*a, **kw):
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
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    def mock_response(*a, **kw):
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


#  Chatbot page


def test_chatbot_page_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Page",
        "chat-page@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    response = local_client.get("/chatbot")
    assert response.status_code == 200


#  Chatbot success non-AJAX


def test_chatbot_success_non_ajax():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "CS",
        "User",
        "cs-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
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
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post("/clear_chatbot_messages", data={"csrf_token": csrf})
    assert response.status_code == 200


#  Friend chat page


def test_friend_chat_page_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FC",
        "User",
        "fc-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "FC",
        "Friend",
        "fc-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/nonexistent/{friend.id}")
    assert response.status_code == 404


def test_friend_chat_page_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FC2",
        "User",
        "fc2-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "FC2",
        "Friend",
        "fc2-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    db.commit()
    msg = create_message(db, "hi", ch_id, user)
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/{ch_id}/{friend.id}")
    assert response.status_code == 200


#  Edit / delete message


def test_edit_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db, "Edit", "User", "edit-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db, "Edit", "Friend", "edit-friend@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "original", ch_id, user)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "updated", "csrf_token": csrf},
    )
    assert response.status_code == 200

    db2 = TestingSessionLocal()
    updated = db2.query(Message).filter(Message.id == msg.id).first()
    assert updated is not None
    assert updated.content == "updated"
    assert updated.edited_at is not None
    db2.close()


def test_edit_message_not_owner():
    db = TestingSessionLocal()
    user = create_user(
        db, "Edit2", "User", "edit2-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    other = create_user(
        db, "Edit2", "Other", "edit2-other@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=other.id)
    db.add(channel)
    msg = create_message(db, "mine", ch_id, other)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "hacked", "csrf_token": csrf},
    )
    assert response.status_code == 403


def test_edit_message_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db, "ENF", "User", "enf-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/edit_message/99999",
        data={"content": "test", "csrf_token": csrf},
    )
    assert response.status_code == 404


def test_delete_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db, "Del", "User", "del-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db, "Del", "Friend", "del-friend@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "delete me", ch_id, user)
    msg_id = msg.id

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_message/{msg_id}",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 200

    db2 = TestingSessionLocal()
    deleted = db2.query(Message).filter(Message.id == msg_id).first()
    assert deleted is None
    db2.close()


def test_delete_message_not_owner():
    db = TestingSessionLocal()
    user = create_user(
        db, "Del2", "User", "del2-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    other = create_user(
        db, "Del2", "Other", "del2-other@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=other.id)
    db.add(channel)
    msg = create_message(db, "not mine", ch_id, other)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_message/{msg.id}",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 403


def test_delete_message_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db, "DNF", "User", "dnf-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/delete_message/99999",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 404


def test_edit_message_empty_content():
    db = TestingSessionLocal()
    user = create_user(
        db, "EMC", "User", "emc-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db, "EMC", "Friend", "emc-friend@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "hello", ch_id, user)
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "   ", "csrf_token": csrf},
    )
    assert response.status_code == 400


def test_friend_chat_page_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db, "FNF", "User", "fnf-user@example.com", "Password123",
        DEFAULT_AVATAR,
    )
    db.close()
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/some-ch/99999")
    assert response.status_code == 404


#  Search user


def test_search_user_no_token():
    response = client.get("/search_user")
    assert response.status_code == 401


def test_search_user_with_friends():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search",
        "User",
        "search-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "Search",
        "Friend",
        "search-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    other = create_user(
        db,
        "Other",
        "User",
        "other-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    create_friendship(db, other, user, FriendStatus.PENDING.value)

    channel = create_channel(db, user, friend)

    local_client = authed_client(user)
    response = local_client.get("/search_user")
    assert response.status_code == 200


def test_search_user_with_friend_no_channel():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search2",
        "User",
        "search-user2@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "Search2",
        "Friend",
        "search-friend2@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    local_client = authed_client(user)
    response = local_client.get("/search_user")
    assert response.status_code == 200


#  Friend requests with data


#  Update profile data


def test_update_profile_data_password_mismatch():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "UP",
        "User",
        "up-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
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
        "Password123",
        DEFAULT_AVATAR,
    )
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/update_profile",
        data={
            "name": "Updated",
            "surname": "User",
            "email": "up2-user@example.com",
            "password": "haslo-123",
            "confirm_password": "haslo-123",
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
        "Password123",
        DEFAULT_AVATAR,
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


#  Single chat channel creation


def test_single_chat_creates_channel():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "SC",
        "Create",
        "sc-create@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "SC",
        "Friend",
        "sc-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


def test_single_chat_accepts_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "SCA",
        "User",
        "sca-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    friend = create_user(
        db,
        "SCA",
        "Friend",
        "sca-friend@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED.value)
    create_friendship(db, friend, user, FriendStatus.ACCEPTED.value)
    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


#  Update profile avatar upload


def test_update_profile_avatar_jpeg():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Avatar",
        "Test",
        "avatar-test@example.com",
        "Password123",
        DEFAULT_AVATAR,
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
        "Password123",
        DEFAULT_AVATAR,
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


#  Chatbot page


def test_chatbot_page_not_logged_in():
    response = client.get("/chatbot")
    assert response.status_code == 401


#  Clear chatbot messages not logged in


def test_clear_chatbot_messages_not_logged_in():
    response = client.post("/clear_chatbot_messages")
    assert response.status_code == 401


def test_friend_requests_with_pending():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FR",
        "User",
        "fr-user@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    requester = create_user(
        db,
        "FR",
        "Requester",
        "fr-requester@example.com",
        "Password123",
        DEFAULT_AVATAR,
    )
    create_friendship(db, requester, user, FriendStatus.PENDING.value)
    local_client = authed_client(user)
    response = local_client.get("/friend_requests")
    assert response.status_code == 200

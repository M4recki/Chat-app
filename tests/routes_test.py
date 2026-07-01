from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient
from conftest import (
    client,
    create_friendship,
    create_channel,
    create_message,
    create_user,
    create_group,
    create_group_member,
    create_group_message,
    DEFAULT_AVATAR,
    TEST_PASSWORD,
    NONEXISTENT_ID,
)
from project.python.main import app
from project.python.settings import settings
from tests.model_test import TestingSessionLocal
from datetime import datetime, timedelta
from uuid import uuid4
from starlette.requests import Request
from project.python.chatbot_utils import ChatbotServiceError, chatbot_json_error
from project.python.main import get_rate_limit_identifier
from project.python.models import (
    User,
    Channel,
    Message,
    GroupChat,
    GroupMember,
    GroupMessage,
)
from project.python.routes import generate_csrf_token
from project.python.models import FriendStatus
from project.python.rate_limit import clear_rate_limiter
from project.python.routes.email import generate_password_reset_token


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
    )
    other = create_user(
        db,
        "Search",
        "Target",
        "search-target@example.com",
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


def test_contact_invalid_email():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/contact",
        data={
            "name": "Test",
            "email": "not-an-email",
            "subject": "Hi",
            "message": "This is a long enough message",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200


def test_contact_email_send_failure(monkeypatch):
    monkeypatch.setattr(
        "project.python.routes.contact.send_email",
        lambda *_a, **_kw: "SMTP error occurred",
    )
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/contact",
        data={
            "name": "Test",
            "email": "test@example.com",
            "subject": "Hi",
            "message": "This is a long enough message",
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


#  Logout


def test_logout_clears_cookie():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Logout",
        "Tester",
        "logout-tester@example.com",
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
        lambda *_a, **_kw: (_ for _ in ()).throw(Exception("unexpected error")),
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
        lambda *_a, **_kw: (_ for _ in ()).throw(Exception("unexpected error")),
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
    )
    friend = create_user(
        db,
        "Friend",
        "One",
        "friend-one@example.com",
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_channel(db, user, friend)

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
    )
    target = create_user(
        db,
        "Target",
        "Old",
        "target-old@example.com",
    )
    old_date = datetime.now() - timedelta(days=20)
    create_friendship(db, user, target, FriendStatus.PENDING, last_sent=old_date)

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
    )
    target = create_user(
        db,
        "Target",
        "User",
        "target-user@example.com",
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
    )
    target = create_user(
        db,
        "Target",
        "Dup",
        "target-dup@example.com",
    )

    create_friendship(db, user, target, FriendStatus.PENDING)
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
    )
    target = create_user(
        db,
        "Target",
        "Den",
        "target-den@example.com",
    )
    create_friendship(
        db, user, target, FriendStatus.DENIED, last_sent=datetime(2020, 1, 1)
    )

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
    )
    requester = create_user(
        db,
        "Request",
        "er",
        "requester@example.com",
    )

    create_friendship(db, requester, user, FriendStatus.PENDING)
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
    )

    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{NONEXISTENT_ID}",
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
    )
    requester = create_user(
        db,
        "Request",
        "deny",
        "requester-deny@example.com",
    )

    create_friendship(db, requester, user, FriendStatus.PENDING)
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
    )

    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{NONEXISTENT_ID}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 404


def test_add_friend_redirects_to_search_user():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "User", "rf-user@example.com")
    target = create_user(db, "RF", "Target", "rf-target@example.com")

    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/search_user" in response.headers["location"]


def test_accept_friend_redirects_to_friend_requests():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "Accept", "rf-accept@example.com")
    requester = create_user(db, "RF", "Requester", "rf-requester@example.com")

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/friend_requests" in response.headers["location"]


def test_deny_friend_redirects_to_friend_requests():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "Deny", "rf-deny@example.com")
    requester = create_user(db, "RF", "DenyReq", "rf-denyreq@example.com")

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/friend_requests" in response.headers["location"]


def test_block_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Block",
        "User",
        "block-user@example.com",
    )
    target = create_user(
        db,
        "Blocked",
        "Target",
        "blocked-target@example.com",
    )

    create_friendship(db, user, target, FriendStatus.ACCEPTED)
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
    )
    target = create_user(
        db,
        "Unblocked",
        "Target",
        "unblocked-target@example.com",
    )

    create_friendship(db, user, target, FriendStatus.BLOCKED)
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


#  Chatbot page


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


#  Chatbot success non-AJAX


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


#  Friend chat page


def test_friend_chat_page_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FC",
        "User",
        "fc-user@example.com",
    )
    friend = create_user(
        db,
        "FC",
        "Friend",
        "fc-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
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
    )
    friend = create_user(
        db,
        "FC2",
        "Friend",
        "fc2-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    db.commit()
    create_message(db, "hi", ch_id, user)
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/{ch_id}/{friend.id}")

    assert response.status_code == 200


#  Edit / delete message


def test_edit_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Edit",
        "User",
        "edit-user@example.com",
    )
    friend = create_user(
        db,
        "Edit",
        "Friend",
        "edit-friend@example.com",
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
        db,
        "Edit2",
        "User",
        "edit2-user@example.com",
    )
    other = create_user(
        db,
        "Edit2",
        "Other",
        "edit2-other@example.com",
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
        db,
        "ENF",
        "User",
        "enf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{NONEXISTENT_ID}",
        data={"content": "test", "csrf_token": csrf},
    )

    assert response.status_code == 404


def test_delete_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Del",
        "User",
        "del-user@example.com",
    )
    friend = create_user(
        db,
        "Del",
        "Friend",
        "del-friend@example.com",
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
        db,
        "Del2",
        "User",
        "del2-user@example.com",
    )
    other = create_user(
        db,
        "Del2",
        "Other",
        "del2-other@example.com",
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
        db,
        "DNF",
        "User",
        "dnf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/delete_message/{NONEXISTENT_ID}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 404


def test_edit_message_empty_content():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "EMC",
        "User",
        "emc-user@example.com",
    )
    friend = create_user(
        db,
        "EMC",
        "Friend",
        "emc-friend@example.com",
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
        db,
        "FNF",
        "User",
        "fnf-user@example.com",
    )
    db.close()
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/some-ch/{NONEXISTENT_ID}")

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
    )
    friend = create_user(
        db,
        "Search",
        "Friend",
        "search-friend@example.com",
    )
    other = create_user(
        db,
        "Other",
        "User",
        "other-user@example.com",
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_friendship(db, other, user, FriendStatus.PENDING)

    create_channel(db, user, friend)

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
    )
    friend = create_user(
        db,
        "Search2",
        "Friend",
        "search-friend2@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.get("/search_user")

    assert response.status_code == 200


def test_search_user_with_query_filters_by_name():
    db = TestingSessionLocal()
    user = create_user(db, "SQ", "Owner", "sq-owner@example.com")
    jan = create_user(db, "Jan", "Kowalski", "sq-jan@example.com")
    create_user(db, "Piotr", "Nowak", "sq-piotr@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=Jan")

    assert response.status_code == 200
    assert jan.name in response.text
    assert jan.surname in response.text


def test_search_user_with_query_filters_by_email():
    db = TestingSessionLocal()
    user = create_user(db, "SQ2", "Owner", "sq2-owner@example.com")
    target = create_user(db, "Target", "Unique", "unique-email@example.com")
    create_user(db, "Other", "User", "other@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=unique-email")

    assert response.status_code == 200
    assert target.name in response.text
    assert target.surname in response.text


def test_search_user_with_query_no_results():
    db = TestingSessionLocal()
    user = create_user(db, "SQ3", "Owner", "sq3-owner@example.com")
    create_user(db, "Some", "User", "some@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=xyz123nonexistent")

    assert response.status_code == 200
    assert "Some" not in response.text


def test_search_user_with_empty_query_returns_all():
    db = TestingSessionLocal()
    user = create_user(db, "SQ4", "Owner", "sq4-owner@example.com")
    user1 = create_user(db, "Alpha", "User", "alpha@example.com")
    user2 = create_user(db, "Beta", "User", "beta@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=")

    assert response.status_code == 200
    assert user1.name in response.text
    assert user2.name in response.text


#  Update profile data


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


#  Single chat channel creation


def test_single_chat_creates_channel():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "SC",
        "Create",
        "sc-create@example.com",
    )
    friend = create_user(
        db,
        "SC",
        "Friend",
        "sc-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
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
    )
    friend = create_user(
        db,
        "SCA",
        "Friend",
        "sca-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_friendship(db, friend, user, FriendStatus.ACCEPTED)
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


#  Group chat


def test_group_chat_list_empty():
    db = TestingSessionLocal()
    user = create_user(db, "GL", "Empty", "gl-empty@example.com")
    local_client = authed_client(user)
    response = local_client.get("/group_chat_list")
    assert response.status_code == 200


def test_group_chat_list_with_groups():
    db = TestingSessionLocal()
    user = create_user(db, "GL", "With", "gl-with@example.com")
    group = create_group(db, "Test Group", user)
    create_group_member(db, group.id, user)
    local_client = authed_client(user)
    response = local_client.get("/group_chat_list")
    assert response.status_code == 200


def test_create_group_form():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Form", "cg-form@example.com")
    local_client = authed_client(user)
    response = local_client.get("/create_group")
    assert response.status_code == 200


def test_create_group_success():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Create", "cg-create@example.com")
    friend = create_user(db, "CG", "Friend", "cg-friend@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "New Group",
            "member_ids": str(friend.id),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/group_chat/" in response.headers["location"]
    db_check = TestingSessionLocal()
    groups = db_check.query(GroupChat).all()
    assert len(groups) == 1
    assert groups[0].name == "New Group"
    members = (
        db_check.query(GroupMember).filter(GroupMember.group_id == groups[0].id).all()
    )
    assert len(members) == 2


def test_create_group_empty_name():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Empty", "cg-empty@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "",
            "member_ids": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 422


def test_create_group_whitespace_name():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "WS", "cg-ws@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "   ",
            "member_ids": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_group_chat_page():
    db = TestingSessionLocal()
    user = create_user(db, "GP", "View", "gp-view@example.com")

    group = create_group(db, "View Group", user)
    create_group_member(db, group.id, user)
    local_client = authed_client(user)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 200


def test_group_chat_page_not_member():
    db = TestingSessionLocal()
    user = create_user(db, "GP", "NoMember", "gp-nomember@example.com")
    owner = create_user(db, "GP", "Owner", "gp-owner@example.com")

    group = create_group(db, "Private", owner)
    create_group_member(db, group.id, owner)
    local_client = authed_client(user)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 403


def test_group_chat_page_creator_with_friends():
    db = TestingSessionLocal()
    creator = create_user(db, "GP", "Creator", "gp-creator@example.com")
    friend = create_user(db, "GP", "Friend", "gp-friend@example.com")
    other = create_user(db, "GP", "Other", "gp-other@example.com")

    group = create_group(db, "With Friends", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    create_friendship(db, creator, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(creator)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 200
    assert friend.name in response.text


def test_add_group_member():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator", "ag-creator@example.com")
    friend = create_user(db, "AG", "Friend", "ag-friend@example.com")

    group = create_group(db, "Add Member", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": friend.id,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    db_check = TestingSessionLocal()
    member = (
        db_check.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == friend.id)
        .first()
    )
    assert member is not None


def test_add_group_member_not_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator2", "ag-creator2@example.com")
    other = create_user(db, "AG", "Other", "ag-other@example.com")
    friend = create_user(db, "AG", "Friend2", "ag-friend2@example.com")

    group = create_group(db, "Add Member 2", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": friend.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_add_group_member_already_member():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator3", "ag-creator3@example.com")
    member = create_user(db, "AG", "Member", "ag-member@example.com")

    group = create_group(db, "Add Member 3", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_add_group_member_nonexistent_user():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator4", "ag-creator4@example.com")

    group = create_group(db, "Bad Add", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": str(NONEXISTENT_ID),
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 404


def test_remove_group_member():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator", "rg-creator@example.com")
    member = create_user(db, "RG", "Member", "rg-member@example.com")

    group = create_group(db, "Remove Member", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_check = TestingSessionLocal()
    remaining = (
        db_check.query(GroupMember).filter(GroupMember.group_id == group.id).all()
    )
    assert len(remaining) == 1
    assert remaining[0].user_id == creator.id


def test_remove_group_member_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator2", "rg-creator2@example.com")

    group = create_group(db, "Remove Creator", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": creator.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_remove_group_member_not_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator3", "rg-creator3@example.com")
    other = create_user(db, "RG", "Other", "rg-other@example.com")
    member = create_user(db, "RG", "Member3", "rg-member3@example.com")

    group = create_group(db, "Remove Not Creator", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    create_group_member(db, group.id, member)
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_remove_group_member_nonexistent():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator4", "rg-creator4@example.com")

    group = create_group(db, "Remove Missing", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": str(NONEXISTENT_ID),
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 404


def test_edit_group_message():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "Edit", "eg-edit@example.com")

    group = create_group(db, "Edit Msg", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "original content")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "updated content",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    db_check = TestingSessionLocal()
    updated = db_check.query(GroupMessage).filter(GroupMessage.id == msg.id).first()
    assert updated is not None
    assert updated.content == "updated content"
    assert updated.edited_at is not None


def test_edit_group_message_not_owner():
    db = TestingSessionLocal()
    owner = create_user(db, "EG", "Owner", "eg-owner@example.com")
    other = create_user(db, "EG", "Other", "eg-other2@example.com")

    group = create_group(db, "Edit Other", owner)
    create_group_member(db, group.id, owner)
    create_group_member(db, group.id, other)
    msg = create_group_message(db, group.id, owner, "owner msg")
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "hacked",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_edit_group_message_empty_content():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "Empty", "eg-empty2@example.com")

    group = create_group(db, "Edit Empty", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "some content")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 422


def test_edit_group_message_whitespace_content():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "WS", "eg-ws@example.com")

    group = create_group(db, "Edit WS", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "original")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "   ",
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 400


def test_delete_group_message():
    db = TestingSessionLocal()
    user = create_user(db, "DG", "Delete", "dg-delete@example.com")

    group = create_group(db, "Delete Msg", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "to delete")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_group_message/{msg.id}",
        data={
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    db_check = TestingSessionLocal()
    deleted = db_check.query(GroupMessage).filter(GroupMessage.id == msg.id).first()
    assert deleted is None


def test_delete_group_message_not_owner():
    db = TestingSessionLocal()
    owner = create_user(db, "DG", "Owner", "dg-owner@example.com")
    other = create_user(db, "DG", "Other", "dg-other@example.com")

    group = create_group(db, "Delete Other", owner)
    create_group_member(db, group.id, owner)
    create_group_member(db, group.id, other)
    msg = create_group_message(db, group.id, owner, "owner msg")
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/delete_group_message/{msg.id}",
        data={
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_group_members_json():
    db = TestingSessionLocal()
    creator = create_user(db, "Alice", "Creator", "gm-creator@example.com")
    member = create_user(db, "Bob", "Member", "gm-member@example.com")

    group = create_group(db, "Members JSON", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    response = local_client.get(f"/group_members/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    names = {u["name"] for u in data}
    assert "Alice" in names
    assert "Bob" in names


def test_group_members_json_not_member():
    db = TestingSessionLocal()
    creator = create_user(db, "GM", "Creator2", "gm-creator2@example.com")
    outsider = create_user(db, "GM", "Outsider", "gm-outsider@example.com")

    group = create_group(db, "Members JSON 2", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(outsider)
    response = local_client.get(f"/group_members/{group.id}")

    assert response.status_code == 403


def test_leave_group_success():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator", "lg-creator@example.com")
    member = create_user(db, "LG", "Member", "lg-member@example.com")

    group = create_group(db, "Leave Group", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(member)
    csrf = generate_csrf_token(member.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/group_chat_list"

    db_check = TestingSessionLocal()
    remaining = (
        db_check.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == member.id)
        .first()
    )
    assert remaining is None
    db_check.close()


def test_leave_group_creator_forbidden():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator2", "lg-creator2@example.com")
    member = create_user(db, "LG", "Member2", "lg-member2@example.com")

    group = create_group(db, "Leave Group 2", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 400
    assert "Creator cannot leave" in response.text


def test_leave_group_not_member():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator3", "lg-creator3@example.com")
    outsider = create_user(db, "LG", "Outsider", "lg-outsider@example.com")

    group = create_group(db, "Leave Group 3", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(outsider)
    csrf = generate_csrf_token(outsider.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 404


def test_leave_group_no_auth():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator4", "lg-creator4@example.com")
    group = create_group(db, "Leave Group 4", creator)
    create_group_member(db, group.id, creator)

    response = client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": generate_csrf_token(0)},
    )

    assert response.status_code == 401


def test_api_chat_messages_basic():
    db = TestingSessionLocal()
    user = create_user(db, "API", "User", "api-user@example.com")
    friend = create_user(db, "API", "Friend", "api-friend@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    create_message(db, "hello", ch_id, user)
    create_message(db, "hi there", ch_id, friend)
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "has_more" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "hello"
    assert data["messages"][1]["content"] == "hi there"


def test_api_chat_messages_empty():
    db = TestingSessionLocal()
    user = create_user(db, "API", "Empty", "api-empty@example.com")
    friend = create_user(db, "API", "Friend2", "api-friend2@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_api_chat_messages_not_participant():
    db = TestingSessionLocal()
    user = create_user(db, "API", "NP", "api-np@example.com")
    friend = create_user(db, "API", "Friend3", "api-friend3@example.com")
    outsider = create_user(db, "API", "Outsider", "api-outsider@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    local_client = authed_client(outsider)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 403


def test_api_chat_messages_no_auth():
    db = TestingSessionLocal()
    user = create_user(db, "API", "NoAuth", "api-noauth@example.com")
    friend = create_user(db, "API", "Friend4", "api-friend4@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    response = client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 401


def test_api_group_messages_basic():
    db = TestingSessionLocal()
    user = create_user(db, "API", "Group", "api-group@example.com")
    member = create_user(db, "API", "GMember", "api-gmember@example.com")

    group = create_group(db, "API Group", user)
    create_group_member(db, group.id, user)
    create_group_member(db, group.id, member)
    create_group_message(db, group.id, user, "group msg 1")
    create_group_message(db, group.id, member, "group msg 2")
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "has_more" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "group msg 1"
    assert data["messages"][1]["content"] == "group msg 2"


def test_api_group_messages_empty():
    db = TestingSessionLocal()
    user = create_user(db, "API", "GEmpty", "api-gempty@example.com")

    group = create_group(db, "API Group Empty", user)
    create_group_member(db, group.id, user)
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_api_group_messages_not_member():
    db = TestingSessionLocal()
    user = create_user(db, "API", "GNM", "api-gnm@example.com")
    outsider = create_user(db, "API", "GOut", "api-gout@example.com")

    group = create_group(db, "API Group NM", user)
    create_group_member(db, group.id, user)
    db.close()

    local_client = authed_client(outsider)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 403


def test_api_group_messages_no_auth():
    db = TestingSessionLocal()
    user = create_user(db, "API", "GNoAuth", "api-gnoauth@example.com")

    group = create_group(db, "API Group NoAuth", user)
    create_group_member(db, group.id, user)
    db.close()

    response = client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 401


#  Password Reset


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

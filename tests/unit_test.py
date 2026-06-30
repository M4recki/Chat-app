import json
import smtplib
import time
from collections import deque
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from typing import cast
from unittest.mock import AsyncMock

import httpx
import openai as openai_mod
import pytest
from conftest import (
    async_session_scope,
    client,
    create_user,
    DEFAULT_AVATAR,
    NONEXISTENT_ID,
)
from fastapi import HTTPException, WebSocketDisconnect
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer as Serializer
from PIL import Image
from starlette.requests import Request
from starlette.testclient import TestClient as WSClient

from project.python.chatbot_utils import (
    ChatbotServiceError,
    build_chatbot_messages,
    chatbot_context,
    chatbot_json_error,
    chatbot_json_success,
    chatbot_response as chatbot_utils_response,
    normalize_chatbot_response,
)
from project.python.connection_manager import ConnectionManager
from project.python.database import async_url, get_db
from project.python.main import app
from project.python.main import app as ws_app
from project.python.models import (
    Channel,
    Friend as FriendModel,
    FriendStatus,
    GroupChat,
    GroupMember,
    GroupMessage,
    Message,
    User,
)
from project.python.rate_limit import MemoryBackend, RateLimiter, get_client_identifier
from project.python.routes import (
    authentication_in_header,
    chatbot_response,
    encode_avatar,
    generate_channel_id,
    get_user,
    get_user_from_request,
    is_authenticated,
    user_image,
    user_name,
)
from project.python.routes.email import (
    generate_password_reset_token,
    get_sender,
    send_email_raw,
    send_email,
    send_reset_email,
    verify_password_reset_token,
)
from project.python.routes.helpers import (
    get_channel_id_map,
    get_friend_status_map,
    get_message_or_404,
    get_user_by_id,
)
from project.python.settings import settings as app_settings
from tests.model_test import TestingSessionLocal


class FakeMessage:
    __slots__ = ("message", "response")

    def __init__(self, message, response):
        self.message = message
        self.response = response


def make_request(headers: list | None = None, host: str | None = "127.0.0.1"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": (host, 8000) if host else None,
    }
    return Request(scope)


def make_request_with_cookie(token: str) -> Request:
    return make_request([(b"cookie", f"access_token={token}".encode())])


def enable_openai(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    response = client.get("/invalid")
    assert response.status_code == 404


#  RateLimiter.get_client_identifier


def test_rate_limiter_get_client_identifier_x_forwarded_for():
    request = make_request([(b"x-forwarded-for", b"203.0.113.42, 10.0.0.1")])
    assert get_client_identifier(request) == "203.0.113.42"


def test_rate_limiter_get_client_identifier_fallback_host():
    request = make_request(host="10.0.0.55")
    assert get_client_identifier(request) == "10.0.0.55"


def test_rate_limiter_get_client_identifier_no_client():
    request = make_request(host=None)
    assert get_client_identifier(request) == "unknown"


#  RateLimiter.enforce edge cases


@pytest.mark.asyncio
async def test_rate_limiter_enforce_zero_max_requests():
    limiter = RateLimiter()
    request = make_request()
    result = await limiter.enforce(request, "test", 0, 60)

    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_negative_window():
    limiter = RateLimiter()
    request = make_request()
    result = await limiter.enforce(request, "test", 5, -1)

    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_bucket_cleanup():
    limiter = RateLimiter()
    backend = limiter.backend

    assert isinstance(backend, MemoryBackend)
    backend.buckets["cleanup:127.0.0.1"] = deque(
        [
            time.monotonic() - 120,
            time.monotonic() - 100,
        ]
    )
    request = make_request()
    result = await limiter.enforce(request, "cleanup", 5, 30)
    assert result is not None
    assert result["remaining"] >= 3


#  authentication_in_header


def test_authentication_in_header_valid():
    serializer = Serializer(app_settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    result = authentication_in_header(make_request_with_cookie(token))
    assert result == {"is_authenticated": True}


def test_authentication_in_header_no_token():
    result = authentication_in_header(make_request())
    assert result == {"is_authenticated": False}


def test_authentication_in_header_invalid_token():
    result = authentication_in_header(make_request_with_cookie("forged"))
    assert result == {"is_authenticated": False}


@pytest.mark.parametrize(
    "func,expected",
    [
        (authentication_in_header, {"is_authenticated": False}),
        (user_image, {"user_image": ""}),
        (user_name, {"user_name": None}),
    ],
)
def test_not_request(func, expected):
    assert func("not-a-request") == expected


#  get_user_from_request


@pytest.mark.asyncio
async def test_get_user_from_request_no_token():
    request = make_request()
    user, user_id = await get_user_from_request(request)
    assert user is None
    assert user_id is None


@pytest.mark.asyncio
async def test_get_user_from_request_invalid_token():
    user, user_id = await get_user_from_request(make_request_with_cookie("bad"))
    assert user is None
    assert user_id is None


#  get_user


def test_get_user_not_found():
    user = get_user(NONEXISTENT_ID)
    assert user is None


#  encode_avatar


def test_encode_avatar_empty():
    user = cast(User, type("FakeUser", (), {"avatar": None})())
    assert encode_avatar(user) == ""


def test_encode_avatar_with_avatar():
    user = cast(User, type("FakeUserWithAvatar", (), {"avatar": b"fake-binary-data"})())
    result = encode_avatar(user)
    assert isinstance(result, str)
    assert len(result) > 0


def test_encode_avatar_no_user():
    assert encode_avatar(None) == ""


#  user_image


def test_user_image_no_token():
    assert user_image(make_request()) == {"user_image": ""}


def test_user_image_invalid_token():
    assert user_image(make_request_with_cookie("bad")) == {"user_image": ""}


#  user_name


def test_user_name_no_token():
    assert user_name(make_request()) == {"user_name": None}


def test_user_name_invalid_token():
    assert user_name(make_request_with_cookie("bad")) == {"user_name": None}


#  settings properties


def test_settings_is_production():
    original = app_settings.environment
    app_settings.environment = "production"

    assert app_settings.is_production is True
    app_settings.environment = "development"
    assert app_settings.is_production is False
    app_settings.environment = original


def test_settings_is_testing():
    original = app_settings.environment
    app_settings.environment = "testing"

    assert app_settings.is_testing is True
    app_settings.testing = False
    app_settings.environment = "development"
    assert app_settings.is_testing is False
    app_settings.environment = original


#  chatbot_utils


def test_normalize_chatbot_response_empty():
    assert normalize_chatbot_response("") == ""
    assert normalize_chatbot_response(None) == ""


def test_normalize_chatbot_response_dedent():
    result = normalize_chatbot_response("  hello\n  world  ")
    assert result == "hello\nworld"


def test_build_chatbot_messages_no_history():
    messages = build_chatbot_messages("hello")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "hello"}


def test_build_chatbot_messages_with_history():
    history = [
        FakeMessage("hi", "hello back"),
        FakeMessage("how are you", "good"),
    ]
    messages = build_chatbot_messages("bye", history)

    assert len(messages) == 6
    assert messages[1] == {"role": "user", "content": "hi"}
    assert messages[2] == {"role": "assistant", "content": "hello back"}
    assert messages[5] == {"role": "user", "content": "bye"}


def test_build_chatbot_messages_with_empty_entries():
    history = [
        FakeMessage("", "response only"),
        FakeMessage("question", ""),
    ]
    messages = build_chatbot_messages("hi", history)
    assert len(messages) == 4


def test_chatbot_response_testing_mode_echo():
    result = chatbot_utils_response("echo: hello world")
    assert result == "hello world"


def test_chatbot_response_testing_mode_fallback():
    result = chatbot_utils_response("plain message")
    assert result == "test-response"


def test_chatbot_context_basic():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": None,
    }

    request = Request(scope)
    ctx = chatbot_context(
        cast(User, cast(object, "fake-user")),
        [],
        request=request,
        message="hi",
        response="hello",
    )

    assert ctx["user"] == "fake-user"
    assert ctx["message"] == "hi"
    assert ctx["response"] == "hello"
    assert ctx["chatbot_messages"] == []


def test_chatbot_json_error():
    resp = chatbot_json_error(502, {"error": "test"})
    assert resp.status_code == 502
    assert resp.body == b'{"error":"test"}'


def test_chatbot_json_success():
    resp = chatbot_json_success(
        "hi",
        "hello",
        datetime(2024, 1, 15, 10, 30, 0),
    )
    assert resp.status_code == 200

    body = json.loads(resp.body)
    assert body["message"] == "hi"
    assert body["response"] == "hello"
    assert "10:30" in body["created_at"]


def test_chatbot_service_error():
    err = ChatbotServiceError("boom")
    assert str(err) == "boom"
    assert err.details == {}
    err2 = ChatbotServiceError("boom", {"key": "val"})
    assert err2.details == {"key": "val"}


@pytest.mark.parametrize(
    "func,key,match",
    [
        (chatbot_utils_response, "changeme", "Chatbot service is not configured"),
        (
            chatbot_utils_response,
            "your-nvidia-api-key",
            "Chatbot service is not configured",
        ),
        (chatbot_utils_response, "   ", "Chatbot service is not configured"),
        (chatbot_utils_response, "bearer changeme", None),
        (chatbot_response, "changeme", "Chatbot service is not configured"),
        (chatbot_response, "your-nvidia-api-key", "Chatbot service is not configured"),
        (chatbot_response, "   ", "Chatbot service is not configured"),
        (chatbot_response, "bearer changeme", None),
    ],
)
def test_chatbot_api_key_validation(monkeypatch, func, key, match):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", key)
    if match:
        with pytest.raises(ChatbotServiceError, match=match):
            func("hello")
    else:
        with pytest.raises(ChatbotServiceError):
            func("hello")


def test_chatbot_context_with_extra():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": None,
    }
    request = Request(scope)
    ctx = chatbot_context(
        cast(User, cast(object, "user")),
        [],
        request=request,
        message="m",
        response="r",
        extra_field="x",
    )
    assert ctx["extra_field"] == "x"
    assert ctx["message"] == "m"


#  OpenAI mock helpers

MOCK_CONTENT = "Hello world"


class MockMsg:
    content = MOCK_CONTENT


class MockChoice:
    message = MockMsg()


class MockCompletion:
    choices = [MockChoice()]


class MockClient:
    class Chat:
        class Completions:
            @staticmethod
            def create(*_a, **_kw):
                return MockCompletion()

        completions = Completions()

    chat = Chat()


def mock_openai(monkeypatch, content=MOCK_CONTENT, create_fn=None):
    MockMsg.content = content

    if create_fn is not None:

        class CustomCompletions:
            @staticmethod
            def create(*_a, **_kw):
                return create_fn()

        class CustomChat:
            completions = CustomCompletions()

        class CustomClient:
            chat = CustomChat()

        monkeypatch.setattr(
            "project.python.chatbot_utils.OpenAI",
            lambda *_a, **_kw: CustomClient(),
        )
    else:
        monkeypatch.setattr(
            "project.python.chatbot_utils.OpenAI",
            lambda *_a, **_kw: MockClient(),
        )


def test_routes_chatbot_response_openai_success(monkeypatch):
    enable_openai(monkeypatch)
    mock_openai(monkeypatch, content="Hello world")
    result = chatbot_response("hello")
    assert result == "Hello world"


def test_routes_chatbot_response_retry_failure(monkeypatch):
    enable_openai(monkeypatch)

    def _raise():
        raise openai_mod.APITimeoutError(httpx.Request("GET", "http://test"))

    mock_openai(monkeypatch, create_fn=_raise)
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_retry_on_timeout(monkeypatch):
    enable_openai(monkeypatch)
    call_count = [0]

    def _create():
        call_count[0] += 1
        if call_count[0] == 1:
            raise openai_mod.APITimeoutError(httpx.Request("GET", "http://test"))
        MockMsg.content = "Retry succeeded"
        return MockCompletion()

    mock_openai(monkeypatch, create_fn=_create)
    result = chatbot_response("hello")
    assert result == "Retry succeeded"
    assert call_count[0] == 2


def test_routes_chatbot_response_api_error(monkeypatch):
    enable_openai(monkeypatch)
    monkeypatch.setattr("project.python.chatbot_utils.settings.debug", True)

    def _raise():
        raise Exception("API error")

    mock_openai(monkeypatch, create_fn=_raise)
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_openai_empty(monkeypatch):
    enable_openai(monkeypatch)
    mock_openai(monkeypatch, content=None)
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_chatbot_utils_debug_logging(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )
    monkeypatch.setattr("project.python.chatbot_utils.settings.debug", True)

    def _raise():
        raise Exception("API error")

    mock_openai(monkeypatch, create_fn=_raise)
    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


def test_chatbot_response_with_openai_mock(monkeypatch):
    enable_openai(monkeypatch)
    mock_openai(monkeypatch, content="Hello world")
    result = chatbot_utils_response("hello")
    assert result == "Hello world"


def test_chatbot_response_empty_openai_response(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )

    mock_openai(monkeypatch, content=None)
    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


#  routes helpers


def test_generate_channel_id():
    result = generate_channel_id(1, 2)
    expected = sha256(b"12").hexdigest()
    assert result == expected
    assert result != generate_channel_id(2, 1)


#  connection_manager


@pytest.fixture
def mgr():
    return ConnectionManager()


@pytest.fixture
def mock_ws():
    return AsyncMock()


@pytest.mark.asyncio
async def test_connection_manager_connect(mgr, mock_ws):
    await mgr.connect(mock_ws, "channel-1", 42)
    assert "channel-1" in mgr.active_connections
    assert mock_ws in mgr.active_connections["channel-1"]
    assert 42 in mgr.user_connections
    assert mock_ws in mgr.user_connections[42]
    assert 42 in mgr.online_users
    mock_ws.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_manager_disconnect(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr.user_connections[1] = [mock_ws]
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert mock_ws not in mgr.active_connections["ch"]
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_connection_manager_broadcast(mgr):
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]

    await mgr.broadcast("hello", "ch")
    mock_a.send_text.assert_awaited_once_with("hello")
    mock_b.send_text.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_connection_manager_broadcast_no_channel(mgr):
    await mgr.broadcast("hello", "nonexistent")
    assert True


@pytest.mark.asyncio
async def test_connection_manager_broadcast_except(mgr):
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]
    await mgr.broadcast_to_channel_except("hello", "ch", mock_a)
    mock_a.send_text.assert_not_awaited()
    mock_b.send_text.assert_awaited_once_with("hello")


def test_connection_manager_is_online(mgr):
    assert not mgr.is_online(1)
    mgr.online_users.add(1)
    assert mgr.is_online(1)


def test_get_other_user_ids_in_channel():
    mgr = ConnectionManager()
    ws_a = AsyncMock()
    ws_b = AsyncMock()

    mgr.active_connections["ch"] = [ws_a, ws_b]
    mgr._ws_to_user[id(ws_a)] = 1
    mgr._ws_to_user[id(ws_b)] = 2

    other_a = mgr.get_other_user_ids_in_channel("ch", ws_a)
    assert 2 in other_a
    assert 1 not in other_a

    other_b = mgr.get_other_user_ids_in_channel("ch", ws_b)
    assert 1 in other_b
    assert 2 not in other_b


def test_get_other_user_ids_in_channel_empty(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr._ws_to_user[id(mock_ws)] = 1
    assert mgr.get_other_user_ids_in_channel("ch", mock_ws) == []


def test_connection_manager_get_online_users(mgr):
    mgr.online_users.update({1, 2, 3})
    result = mgr.get_online_users()
    assert result == {1, 2, 3}
    assert result is not mgr.online_users


@pytest.mark.asyncio
async def test_disconnect_value_error_ws_not_in_channel(mgr, mock_ws):
    mgr.active_connections["ch"] = []
    mgr.user_connections[1] = [mock_ws]
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert "ch" in mgr.active_connections
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_disconnect_value_error_ws_not_in_user_connections(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr.user_connections[1] = []
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert mock_ws not in mgr.active_connections["ch"]
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_broadcast_websocket_disconnect(mgr):
    mock_ok = AsyncMock()
    mock_fail = AsyncMock()
    mock_fail.send_text.side_effect = WebSocketDisconnect()
    mgr.active_connections["ch"] = [mock_ok, mock_fail]

    await mgr.broadcast("hello", "ch")
    mock_ok.send_text.assert_awaited_once_with("hello")
    mock_fail.send_text.assert_awaited_once_with("hello")
    assert mock_fail not in mgr.active_connections["ch"]
    assert mock_ok in mgr.active_connections["ch"]


@pytest.mark.asyncio
async def test_broadcast_except_websocket_disconnect(mgr):
    mock_exclude = AsyncMock()
    mock_fail = AsyncMock()
    mock_fail.send_text.side_effect = WebSocketDisconnect()
    mgr.active_connections["ch"] = [mock_exclude, mock_fail]

    await mgr.broadcast_to_channel_except("hello", "ch", mock_exclude)
    mock_exclude.send_text.assert_not_awaited()
    mock_fail.send_text.assert_awaited_once_with("hello")
    assert mock_fail not in mgr.active_connections["ch"]


#  WebSocket


def create_test_user(db, name="TestUser", email_suffix=""):
    user = User(
        name=name,
        surname="User",
        email=f"ws-test{email_suffix}@example.com",
        password="hash",
        avatar=b"fake",
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    return user


def test_websocket_send_and_receive():
    db = TestingSessionLocal()
    user = create_test_user(db)
    friend = create_test_user(db, name="Friend", email_suffix="-friend")
    ch = Channel(channel_id="test-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/test-ch") as ws:
        ws.send_json(
            {
                "type": "message",
                "message": "Hello!",
            }
        )
        data = ws.receive_text()

        assert '"Hello!"' in data
        assert '"TestUser"' in data


def test_websocket_message_has_type_field():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-2")
    friend = create_test_user(db, name="Friend", email_suffix="-friend2")
    ch = Channel(channel_id="type-ch", user1_id=user.id, user2_id=friend.id)

    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/type-ch") as ws:
        ws.send_json(
            {
                "type": "message",
                "message": "Hi",
            }
        )

        data = json.loads(ws.receive_text())
        assert data["type"] == "message"
        assert data["content"] == "Hi"
        assert data["senderName"] == "TestUser"


def test_online_users_endpoint():
    TestClient(app)
    db = TestingSessionLocal()
    img_binary = BytesIO()

    with Image.open(DEFAULT_AVATAR) as img:
        img.save(img_binary, format="PNG")

    user = User(
        name="Online",
        surname="Test",
        email="online-test@example.com",
        password="hash",
        avatar=img_binary.getvalue(),
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    client.cookies.set("access_token", token)

    response = client.get("/online-users")
    data = response.json()

    assert response.status_code == 200
    assert "online_user_ids" in data
    assert isinstance(data["online_user_ids"], list)
    db.close()


#  database


def test_async_url_postgres():
    result = async_url("postgresql://user:pass@localhost/db")
    assert result == "postgresql+asyncpg://user:pass@localhost/db"


def test_async_url_sqlite():
    result = async_url("sqlite:///./test.db")
    assert result == "sqlite+aiosqlite:///./test.db"


def test_async_url_unknown():
    result = async_url("mysql://user:pass@localhost/db")
    assert result == "mysql://user:pass@localhost/db"


def test_get_db():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass


#  helpers


@pytest.mark.asyncio
async def test_get_user_by_id_found():
    db_sync = TestingSessionLocal()
    user = create_user(
        db_sync,
        "Helper",
        "One",
        "helper1@example.com",
    )
    db_sync.close()

    async with async_session_scope() as db:
        result = await get_user_by_id(db, user.id)
    assert result is not None
    assert result.id == user.id
    assert result.name == "Helper"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found():

    async with async_session_scope() as db:
        result = await get_user_by_id(db, NONEXISTENT_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_message_or_404_found():
    db_sync = TestingSessionLocal()
    user = create_user(
        db_sync,
        "Msg",
        "User",
        "msg-user@example.com",
    )
    msg = Message(
        content="test", channel_id="ch", created_at=datetime.now(), user_id=user.id
    )
    db_sync.add(msg)
    db_sync.commit()
    msg_id = msg.id
    db_sync.close()

    async with async_session_scope() as db:
        result = await get_message_or_404(db, msg_id)
    assert result.id == msg_id


@pytest.mark.asyncio
async def test_get_message_or_404_not_found():
    async with async_session_scope() as db:
        with pytest.raises(HTTPException) as exc:
            await get_message_or_404(db, NONEXISTENT_ID)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_friend_status_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync,
        "FSM",
        "One",
        "fsm1@example.com",
    )
    u2 = create_user(
        db_sync,
        "FSM",
        "Two",
        "fsm2@example.com",
    )
    rel = FriendModel(
        user1_id=u1.id,
        user2_id=u2.id,
        status=FriendStatus.ACCEPTED,
        last_sent=datetime.now(),
    )
    db_sync.add(rel)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        smap = await get_friend_status_map(db, u1.id, [cast(int, u2.id)])
    assert smap[cast(int, u2.id)] == FriendStatus.ACCEPTED


@pytest.mark.asyncio
async def test_get_channel_id_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync,
        "CIM",
        "One",
        "cim1@example.com",
    )
    u2 = create_user(
        db_sync,
        "CIM",
        "Two",
        "cim2@example.com",
    )

    ch = Channel(channel_id="test-ch", user1_id=u1.id, user2_id=u2.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        cmap = await get_channel_id_map(db, u1.id, [cast(int, u2.id)])
    assert cmap[cast(int, u2.id)] == "test-ch"


def test_send_email_config_incomplete(monkeypatch):
    monkeypatch.setattr(app_settings, "testing", False)
    monkeypatch.setattr(app_settings, "email_receiver", "")
    monkeypatch.setattr(app_settings, "email_password", "")
    result = send_email("test@example.com", "Subject", "Body")

    assert result == "Email configuration is incomplete"


@pytest.mark.asyncio
async def test_is_authenticated_expired_token(monkeypatch):
    s = Serializer(app_settings.chat_secret_key)
    token = s.dumps({"user_id": NONEXISTENT_ID})
    monkeypatch.setattr(app_settings, "token_max_age", -1)
    request = make_request_with_cookie(token)

    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_is_authenticated_bad_signature():
    request = make_request_with_cookie("not-a-valid-token")
    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_is_authenticated_user_not_found():
    s = Serializer(app_settings.chat_secret_key)
    token = s.dumps({"user_id": NONEXISTENT_ID})
    request = make_request_with_cookie(token)
    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User not found"


#  email helpers


def test_get_sender_uses_email_sender():
    original = app_settings.email_sender
    app_settings.email_sender = "sender@example.com"
    app_settings.email_receiver = "receiver@example.com"

    try:
        assert get_sender() == "sender@example.com"
    finally:
        app_settings.email_sender = original


def test_get_sender_falls_back_to_receiver():
    original_sender = app_settings.email_sender
    original_receiver = app_settings.email_receiver
    app_settings.email_sender = ""
    app_settings.email_receiver = "fallback@example.com"

    try:
        assert get_sender() == "fallback@example.com"
    finally:
        app_settings.email_sender = original_sender
        app_settings.email_receiver = original_receiver


def test_send_testing_mode_returns_none():
    original = app_settings.testing
    app_settings.testing = True

    try:
        result = send_email_raw("test@example.com", "Subject", "Body")
        assert result is None
    finally:
        app_settings.testing = original


def test_send_config_incomplete_returns_error():
    original_testing = app_settings.testing
    original_sender = app_settings.email_sender
    original_password = app_settings.email_password
    app_settings.testing = False
    app_settings.email_sender = ""
    app_settings.email_password = ""
    app_settings.email_receiver = ""

    try:
        result = send_email_raw("test@example.com", "Subject", "Body")
        assert result == "Email configuration is incomplete"
    finally:
        app_settings.testing = original_testing
        app_settings.email_sender = original_sender
        app_settings.email_password = original_password


def test_send_smtp_failure_returns_error(monkeypatch):
    def fake_smtp():
        raise smtplib.SMTPException("Connection refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", fake_smtp)

    original_testing = app_settings.testing
    original_sender = app_settings.email_sender
    original_password = app_settings.email_password
    app_settings.testing = False
    app_settings.email_sender = "sender@example.com"
    app_settings.email_password = "secret"
    app_settings.email_receiver = "receiver@example.com"

    try:
        result = send_email_raw("test@example.com", "Subject", "Body")
        assert result == "Failed to send email. Please try again later."
    finally:
        app_settings.testing = original_testing
        app_settings.email_sender = original_sender
        app_settings.email_password = original_password


def test_send_smtp_success_returns_none(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def login(self, sender, password):
            pass

        def sendmail(self, sender, to_email, msg):
            pass

    monkeypatch.setattr(
        "project.python.routes.email.SMTP_SSL", lambda *a, **kw: FakeSMTP()
    )

    original_testing = app_settings.testing
    original_sender = app_settings.email_sender
    original_password = app_settings.email_password
    app_settings.testing = False
    app_settings.email_sender = "sender@example.com"
    app_settings.email_password = "secret"
    app_settings.email_receiver = "receiver@example.com"

    try:
        result = send_email_raw("test@example.com", "Subject", "Body")
        assert result is None
    finally:
        app_settings.testing = original_testing
        app_settings.email_sender = original_sender
        app_settings.email_password = original_password


def test_generate_and_verify_password_reset_token():
    token = generate_password_reset_token("user@example.com")
    assert isinstance(token, str)
    assert len(token) > 10

    email = verify_password_reset_token(token)
    assert email == "user@example.com"


def test_verify_password_reset_token_invalid():
    result = verify_password_reset_token("not-a-real-token")
    assert result is None


def test_verify_password_reset_token_expired(monkeypatch):
    original = app_settings.password_reset_token_max_age
    app_settings.password_reset_token_max_age = -1
    try:
        token = generate_password_reset_token("user@example.com")
        result = verify_password_reset_token(token)
        assert result is None
    finally:
        app_settings.password_reset_token_max_age = original


def test_send_reset_email_calls_send(monkeypatch):
    sent_args: tuple[str, str, str] | None = None

    def fake_send(to_email: str, subject: str, body: str) -> None:
        nonlocal sent_args
        sent_args = (to_email, subject, body)

    monkeypatch.setattr("project.python.routes.email.send_email_raw", fake_send)

    result = send_reset_email("user@example.com", "https://example.com/reset/token123")
    assert result is None
    assert sent_args is not None
    assert sent_args[0] == "user@example.com"
    assert sent_args[1] == "Password Reset Request"
    assert "https://example.com/reset/token123" in sent_args[2]


def test_send_email_contact_form_calls_send(monkeypatch):
    sent_args: tuple[str, str, str] | None = None

    def fake_send(to_email: str, subject: str, body: str) -> None:
        nonlocal sent_args
        sent_args = (to_email, subject, body)

    monkeypatch.setattr("project.python.routes.email.send_email_raw", fake_send)

    result = send_email("sender@example.com", "Contact", "Hello there")
    assert result is None
    assert sent_args is not None
    assert sent_args[0] == app_settings.email_receiver
    assert "From: sender@example.com" in sent_args[2]


def test_websocket_auth_failure_no_token():
    ws_client = WSClient(ws_app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/ws/no-token-ch") as ws:
            pass
    assert exc_info.value.code == 4008


def test_websocket_user_not_found():
    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": NONEXISTENT_ID})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/ws/no-user-ch") as ws:
            pass
    assert exc_info.value.code == 4008


def test_websocket_typing():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-typing")
    friend = create_test_user(db, name="Friend", email_suffix="-typing-friend")
    ch = Channel(channel_id="typing-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    ws_client2 = WSClient(ws_app)
    ws_client2.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/typing-ch") as ws1:
        with ws_client2.websocket_connect("/ws/typing-ch") as ws2:
            # Consume the initial user_online sent to ws2 about ws1
            data = ws2.receive_text()
            parsed = json.loads(data)
            assert parsed["type"] == "user_online"

            ws1.send_json({"type": "typing", "typing": True})
            data = ws2.receive_text()
            parsed = json.loads(data)
            assert parsed["type"] == "typing"
            assert parsed["user_name"] == "TestUser"
            assert parsed["typing"] is True


def test_websocket_group_chat():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-group")
    friend = create_test_user(db, name="GFriend", email_suffix="-group-friend")
    group = GroupChat(name="Test Group", created_at=datetime.now(), created_by=user.id)
    db.add(group)
    db.commit()
    gm = GroupMember(group_id=group.id, user_id=user.id, joined_at=datetime.now())
    gm2 = GroupMember(group_id=group.id, user_id=friend.id, joined_at=datetime.now())
    db.add(gm)
    db.add(gm2)
    group_id = group.id
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect(f"/ws/group/{group_id}") as ws:
        ws.send_json({"type": "message", "message": "Hello group!"})
        data = ws.receive_text()
        parsed = json.loads(data)
        assert parsed["type"] == "message"
        assert parsed["content"] == "Hello group!"
        assert parsed["senderName"] == "TestUser"


def test_websocket_group_non_member():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-gnm")
    other = create_test_user(db, name="Other", email_suffix="-gnm-other")
    group = GroupChat(
        name="Private Group", created_at=datetime.now(), created_by=other.id
    )
    db.add(group)
    db.commit()
    gm = GroupMember(group_id=group.id, user_id=other.id, joined_at=datetime.now())
    db.add(gm)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/ws/group/{group.id}") as ws:
            pass
    assert exc_info.value.code == 4003


def test_websocket_invalid_channel():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-badch")
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/nonexistent-channel") as ws:
        ws.send_json({"type": "message", "message": "Hello?"})
        ws.send_json({"type": "typing", "typing": False})
        ws.close()


def test_websocket_reconnect_cancels_pending_leave():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-recon")
    friend = create_test_user(db, name="FriendR", email_suffix="-recon-f")
    ch = Channel(channel_id="recon-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/recon-ch") as ws:
        ws.send_json({"type": "message", "message": "first"})
        data = ws.receive_text()
        assert "first" in data

    with ws_client.websocket_connect("/ws/recon-ch") as ws:
        ws.send_json({"type": "message", "message": "reconnect"})
        data = ws.receive_text()
        assert "reconnect" in data

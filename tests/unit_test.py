import json
import time
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from typing import cast
from unittest.mock import AsyncMock

import httpx
import openai as openai_mod
import pytest
from conftest import async_session_scope, client, create_user
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
from project.python.database import get_db
from project.python.main import app
from project.python.main import app as ws_app
from project.python.models import Message, User
from project.python.rate_limit import MemoryBackend, RateLimiter, get_client_identifier
from project.python.routes import (
    authentication_in_header,
    chatbot_response,
    encode_avatar,
    generate_channel_id,
    get_user,
    get_user_from_request,
    user_image,
    user_name,
)
from project.python.settings import settings as app_settings
from tests.model_test import TestingSessionLocal


class FakeMessage:
    def __init__(self, message, response):
        self.message = message
        self.response = response


def _make_request(headers: list | None = None, host: str | None = "127.0.0.1"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": (host, 8000) if host else None,
    }
    return Request(scope)


def _make_request_with_cookie(token: str) -> Request:
    return _make_request([(b"cookie", f"access_token={token}".encode())])


def _enable_openai(monkeypatch):
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
    request = _make_request([(b"x-forwarded-for", b"203.0.113.42, 10.0.0.1")])
    assert get_client_identifier(request) == "203.0.113.42"


def test_rate_limiter_get_client_identifier_fallback_host():
    request = _make_request(host="10.0.0.55")
    assert get_client_identifier(request) == "10.0.0.55"


def test_rate_limiter_get_client_identifier_no_client():
    request = _make_request(host=None)
    assert get_client_identifier(request) == "unknown"


#  RateLimiter.enforce edge cases


@pytest.mark.asyncio
async def test_rate_limiter_enforce_zero_max_requests():
    limiter = RateLimiter()
    request = _make_request()
    result = await limiter.enforce(request, "test", 0, 60)
    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_negative_window():
    limiter = RateLimiter()
    request = _make_request()
    result = await limiter.enforce(request, "test", 5, -1)
    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_bucket_cleanup():
    from collections import deque as _deque

    limiter = RateLimiter()
    backend = limiter.backend
    assert isinstance(backend, MemoryBackend)
    backend.buckets["cleanup:127.0.0.1"] = _deque(
        [
            time.monotonic() - 120,
            time.monotonic() - 100,
        ]
    )
    request = _make_request()
    result = await limiter.enforce(request, "cleanup", 5, 30)
    assert result is not None
    assert result["remaining"] >= 4


#  authentication_in_header


def test_authentication_in_header_valid():
    serializer = Serializer(app_settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    result = authentication_in_header(_make_request_with_cookie(token))
    assert result == {"is_authenticated": True}


def test_authentication_in_header_no_token():
    result = authentication_in_header(_make_request())
    assert result == {"is_authenticated": False}


def test_authentication_in_header_invalid_token():
    result = authentication_in_header(_make_request_with_cookie("forged"))
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
    request = _make_request()
    user, user_id = await get_user_from_request(request)
    assert user is None
    assert user_id is None


@pytest.mark.asyncio
async def test_get_user_from_request_invalid_token():
    user, user_id = await get_user_from_request(_make_request_with_cookie("bad"))
    assert user is None
    assert user_id is None


#  get_user


def test_get_user_not_found():
    user = get_user(99999)
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
    assert user_image(_make_request()) == {"user_image": ""}


def test_user_image_invalid_token():
    assert user_image(_make_request_with_cookie("bad")) == {"user_image": ""}


#  user_name


def test_user_name_no_token():
    assert user_name(_make_request()) == {"user_name": None}


def test_user_name_invalid_token():
    assert user_name(_make_request_with_cookie("bad")) == {"user_name": None}


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

_MOCK_CONTENT = "Hello world"


class _MockMsg:
    content = _MOCK_CONTENT


class _MockChoice:
    message = _MockMsg()


class _MockCompletion:
    choices = [_MockChoice()]


class _MockClient:
    class Chat:
        class Completions:
            @staticmethod
            def create(*a, **kw):
                return _MockCompletion()

        completions = Completions()

    chat = Chat()


def _mock_openai(monkeypatch, content=None, create_fn=None):
    if content is not None:
        _MockMsg.content = content
    _MockMsg.content = content if content is not None else _MOCK_CONTENT

    if create_fn is not None:

        class CustomCompletions:
            @staticmethod
            def create(*a, **kw):
                return create_fn()

        client = _MockClient()
        client.Chat.Completions = CustomCompletions()
        client.Chat.completions = CustomCompletions()
        monkeypatch.setattr(
            "project.python.chatbot_utils.OpenAI",
            lambda *a, **kw: client,
        )
    else:
        monkeypatch.setattr(
            "project.python.chatbot_utils.OpenAI",
            lambda *a, **kw: _MockClient(),
        )


def test_routes_chatbot_response_openai_success(monkeypatch):
    _enable_openai(monkeypatch)
    _mock_openai(monkeypatch, content="Hello world")
    result = chatbot_response("hello")
    assert result == "Hello world"


def test_routes_chatbot_response_retry_failure(monkeypatch):
    _enable_openai(monkeypatch)

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise openai_mod.APITimeoutError(
                        httpx.Request("GET", "http://test"),
                    )

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_retry_on_timeout(monkeypatch):
    _enable_openai(monkeypatch)
    call_count = [0]

    class MockMsg:
        content = "Retry succeeded"

    class MockChoice:
        message = MockMsg()

    class MockCompletion:
        choices = [MockChoice()]

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise openai_mod.APITimeoutError(
                            httpx.Request("GET", "http://test"),
                        )
                    return MockCompletion()

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    result = chatbot_response("hello")
    assert result == "Retry succeeded"
    assert call_count[0] == 2


def test_routes_chatbot_response_api_error(monkeypatch):
    _enable_openai(monkeypatch)
    monkeypatch.setattr("project.python.chatbot_utils.settings.debug", True)

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise Exception("API error")

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_openai_empty(monkeypatch):
    _enable_openai(monkeypatch)

    class MockMsg:
        content = None

    class MockChoice:
        message = MockMsg()

    class MockCompletion:
        choices = [MockChoice()]

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    return MockCompletion()

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_chatbot_utils_debug_logging(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )
    monkeypatch.setattr("project.python.chatbot_utils.settings.debug", True)

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise Exception("API error")

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


def test_chatbot_response_with_openai_mock(monkeypatch):
    _enable_openai(monkeypatch)

    class MockMsg:
        content = "Hello world"

    class MockChoice:
        message = MockMsg()

    class MockCompletion:
        choices = [MockChoice()]

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    return MockCompletion()

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
    result = chatbot_utils_response("hello")
    assert result == "Hello world"


def test_chatbot_response_empty_openai_response(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )

    class MockMsg:
        content = None

    class MockChoice:
        message = MockMsg()

    class MockCompletion:
        choices = [MockChoice()]

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    return MockCompletion()

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(
        "project.python.chatbot_utils.OpenAI",
        lambda *a, **kw: MockClient(),
    )
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


#  WebSocket


def _create_test_user(db, name="TestUser", email_suffix=""):
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
    user = _create_test_user(db)
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
                "channel_id": "test-ch",
                "message": "Hello!",
            }
        )
        data = ws.receive_text()
        assert '"Hello!"' in data
        assert '"TestUser"' in data


def test_websocket_message_has_type_field():
    db = TestingSessionLocal()
    user = _create_test_user(db, email_suffix="-2")
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
                "channel_id": "type-ch",
                "message": "Hi",
            }
        )
        data = json.loads(ws.receive_text())
        assert data["type"] == "message"
        assert data["content"] == "Hi"
        assert data["senderName"] == "TestUser"


def test_online_users_endpoint():
    client = TestClient(app)
    db = TestingSessionLocal()
    img_binary = BytesIO()

    with Image.open("project/static/img/default avatar.png") as img:
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
        db_sync, "Helper", "One", "helper1@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    db_sync.close()
    from project.python.routes.helpers import get_user_by_id

    async with async_session_scope() as db:
        result = await get_user_by_id(db, user.id)
    assert result is not None
    assert result.id == user.id
    assert result.name == "Helper"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found():
    from project.python.routes.helpers import get_user_by_id

    async with async_session_scope() as db:
        result = await get_user_by_id(db, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_get_message_or_404_found():
    db_sync = TestingSessionLocal()
    user = create_user(
        db_sync, "Msg", "User", "msg-user@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    msg = Message(content="test", channel_id="ch", created_at=datetime.now(), user_id=user.id)
    db_sync.add(msg)
    db_sync.commit()
    msg_id = msg.id
    db_sync.close()
    from project.python.routes.helpers import get_message_or_404

    async with async_session_scope() as db:
        result = await get_message_or_404(db, msg_id)
    assert result.id == msg_id


@pytest.mark.asyncio
async def test_get_message_or_404_not_found():
    from project.python.routes.helpers import get_message_or_404
    from fastapi import HTTPException

    async with async_session_scope() as db:
        with pytest.raises(HTTPException) as exc:
            await get_message_or_404(db, 99999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_friend_status_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync, "FSM", "One", "fsm1@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    u2 = create_user(
        db_sync, "FSM", "Two", "fsm2@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    from project.python.models import Friend as FriendModel, FriendStatus

    rel = FriendModel(
        user1_id=u1.id, user2_id=u2.id, status=FriendStatus.ACCEPTED.value, last_sent=datetime.now(),
    )
    db_sync.add(rel)
    db_sync.commit()
    db_sync.close()
    from project.python.routes.helpers import get_friend_status_map

    async with async_session_scope() as db:
        smap = await get_friend_status_map(db, u1.id, [u2.id])
    assert smap[u2.id] == FriendStatus.ACCEPTED.value


@pytest.mark.asyncio
async def test_get_channel_id_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync, "CIM", "One", "cim1@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    u2 = create_user(
        db_sync, "CIM", "Two", "cim2@example.com", "Password123",
        "project/static/img/default avatar.png",
    )
    from project.python.models import Channel

    ch = Channel(channel_id="test-ch", user1_id=u1.id, user2_id=u2.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()
    from project.python.routes.helpers import get_channel_id_map

    async with async_session_scope() as db:
        cmap = await get_channel_id_map(db, u1.id, [u2.id])
    assert cmap[u2.id] == "test-ch"

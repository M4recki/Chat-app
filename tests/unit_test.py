import httpx
import pytest
from conftest import client
from itsdangerous import URLSafeTimedSerializer as Serializer
from starlette.requests import Request
from project.python.settings import settings
from project.python.rate_limit import RateLimiter
from project.python.routes import (
    authentication_in_header,
    get_user_from_request,
    get_user,
    encode_avatar,
    user_image,
    user_name,
)

import json
import time
from datetime import datetime
from hashlib import sha256
from unittest.mock import AsyncMock

import openai as openai_mod
from fastapi.testclient import TestClient
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
from project.python.rate_limit import get_client_identifier
from project.python.routes import chatbot_response
from project.python.routes import generate_channel_id

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    response = client.get("/invalid")
    assert response.status_code == 404


#  RateLimiter.get_client_identifier


def _make_request(headers: list | None = None, host: str | None = "127.0.0.1"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": (host, 8000) if host else None,
    }
    return Request(scope)


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


def test_rate_limiter_enforce_zero_max_requests():
    limiter = RateLimiter()
    request = _make_request()
    result = limiter.enforce(request, "test", 0, 60)
    assert result is None


def test_rate_limiter_enforce_negative_window():
    limiter = RateLimiter()
    request = _make_request()
    result = limiter.enforce(request, "test", 5, -1)
    assert result is None


def test_rate_limiter_enforce_bucket_cleanup():
    limiter = RateLimiter()
    request = _make_request()

    limiter._buckets["cleanup:127.0.0.1"] = __import__("collections").deque(
        [
            time.monotonic() - 120,
            time.monotonic() - 100,
        ]
    )
    result = limiter.enforce(request, "cleanup", 5, 30)
    assert result is not None
    assert result["remaining"] >= 4


#  authentication_in_header


def test_authentication_in_header_valid():
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", f"access_token={token}".encode())],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)
    result = authentication_in_header(request)
    assert result == {"is_authenticated": True}


def test_authentication_in_header_no_token():
    request = _make_request()
    result = authentication_in_header(request)
    assert result == {"is_authenticated": False}


def test_authentication_in_header_invalid_token():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=forged")],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)
    result = authentication_in_header(request)
    assert result == {"is_authenticated": False}


def test_authentication_in_header_not_request():
    result = authentication_in_header("not-a-request")
    assert result == {"is_authenticated": False}


#  get_user_from_request


def test_get_user_from_request_no_token():
    request = _make_request()
    user, user_id = get_user_from_request(request)
    assert user is None
    assert user_id is None


def test_get_user_from_request_invalid_token():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=bad")],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)
    user, user_id = get_user_from_request(request)
    assert user is None
    assert user_id is None


#  get_user


def test_get_user_not_found():
    user = get_user(99999)
    assert user is None


def test_encode_avatar_empty():
    class FakeUser:
        avatar = None

    assert encode_avatar(FakeUser()) == ""


def test_encode_avatar_with_avatar():
    class FakeUserWithAvatar:
        avatar = b"fake-binary-data"

    result = encode_avatar(FakeUserWithAvatar())
    assert isinstance(result, str)
    assert len(result) > 0


def test_encode_avatar_no_user():
    assert encode_avatar(None) == ""


#  user_image


def test_user_image_not_request():
    assert user_image("not-a-request") == {"user_image": ""}


def test_user_image_no_token():
    request = _make_request()
    assert user_image(request) == {"user_image": ""}


def test_user_image_invalid_token():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=bad")],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)
    assert user_image(request) == {"user_image": ""}


#  user_name


def test_user_name_not_request():
    assert user_name("not-a-request") == {"user_name": None}


def test_user_name_no_token():
    request = _make_request()
    assert user_name(request) == {"user_name": None}


def test_user_name_invalid_token():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=bad")],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)
    assert user_name(request) == {"user_name": None}


#  settings properties


def test_settings_is_production():

    original = settings.environment
    settings.environment = "production"
    assert settings.is_production is True
    settings.environment = "development"
    assert settings.is_production is False
    settings.environment = original


def test_settings_is_testing():

    original = settings.environment
    settings.environment = "testing"
    assert settings.is_testing is True
    settings.testing = False
    settings.environment = "development"
    assert settings.is_testing is False
    settings.environment = original


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

    class FakeMessage:
        def __init__(self, message, response):
            self.message = message
            self.response = response

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

    class FakeMessage:
        def __init__(self, message, response):
            self.message = message
            self.response = response

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
        "fake-user", [], request=request, message="hi", response="hello"
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

    resp = chatbot_json_success("hi", "hello", datetime(2024, 1, 15, 10, 30, 0))
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


def test_chatbot_response_non_testing_missing_api_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "changeme")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_utils_response("hello")


def test_chatbot_response_non_testing_placeholder_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "your-nvidia-api-key")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_utils_response("hello")


def test_chatbot_response_non_testing_empty_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "   ")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_utils_response("hello")


def test_chatbot_context_with_extra():

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "client": None}
    request = Request(scope)
    ctx = chatbot_context(
        "user", [], request=request, message="m", response="r", extra_field="x"
    )
    assert ctx["extra_field"] == "x"
    assert ctx["message"] == "m"


def test_chatbot_response_bearer_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "bearer changeme")
    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


def test_routes_build_chatbot_messages():

    messages = build_chatbot_messages("hello")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "hello"}


def test_routes_build_chatbot_messages_with_history():

    class FakeMsg:
        def __init__(self, message, response):
            self.message = message
            self.response = response
    history = [FakeMsg("hi", "hello back")]
    messages = build_chatbot_messages("bye", history)
    assert len(messages) == 4


def test_routes_chatbot_response_missing_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "changeme")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_response("hello")


def test_routes_chatbot_response_placeholder_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "your-nvidia-api-key")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_response("hello")


def test_routes_chatbot_response_empty_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "   ")
    with pytest.raises(ChatbotServiceError, match="Chatbot service is not configured"):
        chatbot_response("hello")


def test_routes_chatbot_response_bearer_key(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "bearer changeme")
    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_testing_path(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    assert chatbot_response("echo: hi") == "hi"
    assert chatbot_response("plain") == "test-response"


def test_routes_chatbot_response_openai_success(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "sk-real-key")

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

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    result = chatbot_response("hello")
    assert result == "Hello world"


def test_routes_chatbot_response_retry_failure(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "sk-real-key")

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise openai_mod.APITimeoutError(httpx.Request("GET", "http://test"))
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_retry_on_timeout(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "sk-real-key")
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
                        raise openai_mod.APITimeoutError(httpx.Request("GET", "http://test"))
                    return MockCompletion()
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    result = chatbot_response("hello")
    assert result == "Retry succeeded"
    assert call_count[0] == 2


def test_routes_chatbot_response_api_error(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "sk-real-key")
    monkeypatch.setattr("project.python.routes.settings.debug", True)

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise Exception("API error")
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_routes_chatbot_response_openai_empty(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.routes.settings.ai_key", "sk-real-key")

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

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    with pytest.raises(ChatbotServiceError):
        chatbot_response("hello")


def test_chatbot_utils_debug_logging(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "sk-real-key")
    monkeypatch.setattr("project.python.chatbot_utils.settings.debug", True)

    class MockClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(*a, **kw):
                    raise Exception("API error")
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


def test_chatbot_response_with_openai_mock(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "sk-real-key")

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

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    result = chatbot_utils_response("hello")
    assert result == "Hello world"


def test_chatbot_response_empty_openai_response(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr("project.python.chatbot_utils.settings.ai_key", "sk-real-key")

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

    monkeypatch.setattr("project.python.chatbot_utils.OpenAI", lambda *a, **kw: MockClient())

    with pytest.raises(ChatbotServiceError):
        chatbot_utils_response("hello")


#  routes helpers


def test_generate_channel_id():

    result = generate_channel_id(1, 2)
    expected = sha256(b"12").hexdigest()
    assert result == expected
    assert result != generate_channel_id(2, 1)


#  connection_manager


@pytest.mark.asyncio
async def test_connection_manager_connect():

    mgr = ConnectionManager()
    mock_ws = AsyncMock()
    await mgr.connect(mock_ws, "channel-1", 42)
    assert "channel-1" in mgr.active_connections
    assert mock_ws in mgr.active_connections["channel-1"]
    assert 42 in mgr.user_connections
    assert mock_ws in mgr.user_connections[42]
    assert 42 in mgr.online_users
    mock_ws.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_manager_disconnect():

    mgr = ConnectionManager()
    mock_ws = AsyncMock()
    mgr.active_connections["ch"] = [mock_ws]
    mgr.user_connections[1] = [mock_ws]
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)
    assert mock_ws not in mgr.active_connections["ch"]
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_connection_manager_broadcast():

    mgr = ConnectionManager()
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]
    await mgr.broadcast("hello", "ch")
    mock_a.send_text.assert_awaited_once_with("hello")
    mock_b.send_text.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_connection_manager_broadcast_no_channel():

    mgr = ConnectionManager()
    await mgr.broadcast("hello", "nonexistent")
    assert True


@pytest.mark.asyncio
async def test_connection_manager_broadcast_except():

    mgr = ConnectionManager()
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]
    await mgr.broadcast_to_channel_except("hello", "ch", mock_a)
    mock_a.send_text.assert_not_awaited()
    mock_b.send_text.assert_awaited_once_with("hello")


def test_connection_manager_is_online():

    mgr = ConnectionManager()
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


def test_get_other_user_ids_in_channel_empty():

    mgr = ConnectionManager()
    ws = AsyncMock()
    mgr.active_connections["ch"] = [ws]
    mgr._ws_to_user[id(ws)] = 1

    assert mgr.get_other_user_ids_in_channel("ch", ws) == []


def test_connection_manager_get_online_users():

    mgr = ConnectionManager()
    mgr.online_users.update({1, 2, 3})
    result = mgr.get_online_users()
    assert result == {1, 2, 3}
    assert result is not mgr.online_users


#  WebSocket


def test_websocket_send_and_receive():

    ws_client = WSClient(ws_app)
    with ws_client.websocket_connect("/ws/test-ch/TestUser/1") as ws:
        ws.send_json({
            "type": "message",
            "channel_id": "test-ch",
            "message": "Hello!",
        })
        data = ws.receive_text()
        assert '"Hello!"' in data
        assert '"TestUser"' in data


def test_websocket_message_has_type_field():

    ws_client = WSClient(ws_app)
    with ws_client.websocket_connect("/ws/type-ch/TestUser/1") as ws:
        ws.send_json({
            "type": "message",
            "channel_id": "type-ch",
            "message": "Hi",
        })
        data = json.loads(ws.receive_text())
        assert data["type"] == "message"
        assert data["content"] == "Hi"
        assert data["senderName"] == "TestUser"


def test_online_users_endpoint():

    client = TestClient(app)
    response = client.get("/online-users")
    assert response.status_code == 200
    data = response.json()
    assert "online_user_ids" in data
    assert isinstance(data["online_user_ids"], list)


#  database


def test_get_db():

    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass

import json
from datetime import datetime
from typing import cast
from unittest.mock import MagicMock

import httpx
import openai as openai_mod
import pytest
from starlette.requests import Request

from project.python.chatbot_utils import (
    ChatbotServiceError,
    build_chatbot_messages,
    call_model,
    chatbot_context,
    chatbot_json_error,
    chatbot_json_success,
    chatbot_response,
    chatbot_response as chatbot_utils_response,
    normalize_chatbot_response,
)
from project.python.models import User
from project.python.routes.helpers import generate_channel_id


class FakeMessage:
    __slots__ = ("message", "response")

    def __init__(self, message, response):
        self.message = message
        self.response = response


def enable_openai(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(
        "project.python.chatbot_utils.settings.ai_key",
        "sk-real-key",
    )


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


def mock_openai(monkeypatch, content: str | None = MOCK_CONTENT, create_fn=None):
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
    from hashlib import sha256

    result = generate_channel_id(1, 2)
    expected = sha256(b"12").hexdigest()
    assert result == expected
    assert result != generate_channel_id(2, 1)


def test_call_model_success():
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "hello world"
    mock_client.chat.completions.create.return_value = mock_completion

    result = call_model(mock_client, "test-model", [{"role": "user", "content": "hi"}])
    assert result == "hello world"


def test_call_model_empty_content():
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = None
    mock_client.chat.completions.create.return_value = mock_completion

    result = call_model(mock_client, "test-model", [{"role": "user", "content": "hi"}])
    assert result == ""

from itsdangerous import URLSafeTimedSerializer as Serializer
from fastapi.testclient import TestClient
from project.python.models import ChatbotMessage
from project.python.chatbot_utils import ChatbotServiceError
from project.python.routes import send_email, chatbot_response, generate_csrf_token
from project.python.settings import settings
from project.python.main import app
from project.python.rate_limit import rate_limiter
from tests.integration_test import create_user
from tests.model_test import TestingSessionLocal
from conftest import client


def test_send_email():
    """
    Test sending an email.

    Sends a test email and asserts the POST
    response status code is 200.
    """
    name = "John Doe"
    email = "john@example.com"
    subject = "Test Subject"
    message = "Test Message"

    response = client.post(
        "/contact",
        data={"name": name, "email": email, "subject": subject, "message": message},
    )

    send_email(email, subject, message)

    assert response.status_code == 200


def test_chatbot_response():
    """
    Test the chatbot response.

    Sends a test input and asserts the response
    is a string that matches the input.
    """
    user_input = "Say exactly these sentence without any additions: I am chatbot"

    response = chatbot_response(user_input)

    assert response is not None
    assert isinstance(response, str)
    assert response == "I am chatbot"


def test_chatbot_api_failure_returns_structured_error(monkeypatch):
    """
    Test chatbot route error handling.

    Forces the chatbot service to fail and asserts that the API returns
    a structured error response without inserting a fake chatbot message.
    """
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Chat",
        "Tester",
        "chat-tester@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )

    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    client.cookies.set("access_token", token)

    def raise_chatbot_error(message, previous_messages=None):
        raise ChatbotServiceError(
            "Chatbot service is temporarily unavailable",
            {"models": ["test-model"], "attempts": ["forced failure"]},
        )

    monkeypatch.setattr("project.python.routes.chatbot.chatbot_response", raise_chatbot_error)

    csrf = generate_csrf_token(user.id)
    response = client.post(
        "/chatbot",
        data={"message": "please tell me a random fact", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 502

    payload = response.json()
    assert payload["error"] == "chatbot"
    assert payload["message"] == "Chatbot service is temporarily unavailable"
    assert payload["error_type"] == "ChatbotServiceError"
    assert payload["details"]["models"] == ["test-model"]
    assert payload["details"]["attempts"] == ["forced failure"]

    assert (
        db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).count() == 0
    )


#  Pydantic edge cases


def test_very_long_strings_in_signup():
    rate_limiter._buckets.clear()
    long_name = "A" * 500
    response = client.post(
        "/sign_up",
        data={
            "name": long_name,
            "surname": "Test",
            "email": "long-string@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
        },
    )
    assert response.status_code in (200, 303, 422)


def test_unicode_in_signup():
    rate_limiter._buckets.clear()
    response = client.post(
        "/sign_up",
        data={
            "name": "Zoë ユーザー",
            "surname": "Müller测试",
            "email": "unicode-test@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
        },
    )
    assert response.status_code in (200, 303, 422)


def test_special_characters_in_name():
    rate_limiter._buckets.clear()
    response = client.post(
        "/sign_up",
        data={
            "name": "!@#$%^&*()_+",
            "surname": "{}[]|\\:;\"'<>,.?/~",
            "email": "special-chars@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
        },
    )
    assert response.status_code in (200, 303, 422)


def test_very_long_email():
    rate_limiter._buckets.clear()
    local_part = "a" * 200
    response = client.post(
        "/sign_up",
        data={
            "name": "Long",
            "surname": "Email",
            "email": f"{local_part}@example.com",
            "password": "Pass123",
            "confirm_password": "Pass123",
            "terms_conditions": "on",
        },
    )
    assert response.status_code in (200, 303, 422)


def test_unicode_in_chatbot():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Unicode",
        "Chat",
        "unicode-chat@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    local = TestClient(app, raise_server_exceptions=False)
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local.cookies.set("access_token", token)
    csrf = generate_csrf_token(user.id)
    response = local.post(
        "/chatbot",
        data={"message": "echo: hi", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code in (200, 502)


def test_html_injection_in_chatbot():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "HTML",
        "Inj",
        "html-inj@example.com",
        "Password123",
        "project/static/img/default avatar.png",
    )
    local = TestClient(app, raise_server_exceptions=False)
    serializer = Serializer(settings.chat_secret_key)
    token = serializer.dumps({"user_id": user.id})
    local.cookies.set("access_token", token)
    csrf = generate_csrf_token(user.id)
    response = local.post(
        "/chatbot",
        data={"message": "<b>bold</b><script>alert(1)</script>", "csrf_token": csrf},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code in (200, 502)


def test_contact_with_long_message():
    rate_limiter._buckets.clear()
    response = client.post(
        "/contact",
        data={
            "name": "Test",
            "email": "long-msg@example.com",
            "subject": "Test",
            "message": "A" * 10000,
        },
    )
    assert response.status_code == 200

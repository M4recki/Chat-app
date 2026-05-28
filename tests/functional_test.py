from itsdangerous import URLSafeTimedSerializer as Serializer

from project.python.models import ChatbotMessage
from project.python.chatbot_utils import ChatbotServiceError
from project.python.routes import send_email, chatbot_response
from project.python.settings import settings
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

    monkeypatch.setattr("project.python.routes.chatbot_response", raise_chatbot_error)

    response = client.post(
        "/chatbot",
        data={"message": "please tell me a random fact"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 502

    payload = response.json()
    assert payload["error"] == "chatbot"
    assert payload["message"] == "Chatbot service is temporarily unavailable"
    assert payload["error_type"] == "ChatbotServiceError"
    assert payload["details"]["models"] == ["test-model"]
    assert payload["details"]["attempts"] == ["forced failure"]

    assert db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).count() == 0

from project.python.routes import send_email, chatbot_response
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

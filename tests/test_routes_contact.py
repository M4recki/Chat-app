from conftest import client
from project.python.routes.helpers import generate_csrf_token


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

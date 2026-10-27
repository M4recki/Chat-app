import smtplib

from project.python.routes.email import (
    generate_password_reset_token,
    get_sender,
    send_email,
    send_email_raw,
    send_reset_email,
    verify_password_reset_token,
)
from project.python.settings import settings as app_settings


def test_send_email_config_incomplete(monkeypatch):
    monkeypatch.setattr(app_settings, "testing", False)
    monkeypatch.setattr(app_settings, "email_receiver", "")
    monkeypatch.setattr(app_settings, "email_password", "")
    result = send_email("test@example.com", "Subject", "Body")

    assert result == "Email configuration is incomplete"


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

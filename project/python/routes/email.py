import logging

from email.message import EmailMessage
from smtplib import SMTPException, SMTP_SSL
from ssl import create_default_context

from itsdangerous import URLSafeTimedSerializer as Serializer

from ..settings import settings

logger = logging.getLogger(__name__)


def get_sender() -> str:
    """Return the SMTP sender/login address, falling back to email_receiver."""
    return settings.email_sender or settings.email_receiver


def send_email_raw(to_email: str, subject: str, body: str) -> str | None:
    """Send an email via SMTP to the given recipient."""
    if settings.testing:
        logger.info("TESTING mode: skipping email to %s", to_email)
        return None

    sender = get_sender()
    if not sender or not settings.email_password:
        logger.warning(
            "Email config incomplete: sender=%s, has_password=%s",
            bool(sender),
            bool(settings.email_password),
        )
        return "Email configuration is incomplete"

    email = EmailMessage()
    email["From"] = sender
    email["To"] = to_email
    email["Subject"] = subject
    email.set_content(body)

    context = create_default_context()

    try:
        with SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(sender, settings.email_password)
            smtp.sendmail(
                sender,
                to_email,
                email.as_string(),
            )
    except (SMTPException, OSError) as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return "Failed to send email. Please try again later."

    return None


def send_email(email_address: str, subject: str, message: str) -> str | None:
    """Send an email from the contact form to the admin.

    Args:
        email_address: The sender's email address (included in body)
        subject: The email subject
        message: The email body

    Returns:
        str or None: Error message if sending failed, None on success
    """
    body = f"From: {email_address}\n\n{message}"
    return send_email_raw(settings.email_receiver, subject, body)


def generate_password_reset_token(email: str) -> str:
    """Generate a time-limited signed token for password reset.

    Args:
        email: The user's email address

    Returns:
        str: Signed token valid for password_reset_token_max_age seconds
    """
    s = Serializer(settings.chat_secret_key + "_password_reset")
    return s.dumps({"email": email})


def verify_password_reset_token(token: str) -> str | None:
    """Verify a password reset token and return the email.

    Args:
        token: The signed token

    Returns:
        str or None: The email if valid, None otherwise
    """
    s = Serializer(settings.chat_secret_key + "_password_reset")
    try:
        data = s.loads(token, max_age=settings.password_reset_token_max_age)
        return data["email"]
    except Exception:
        return None


def send_reset_email(to_email: str, reset_link: str) -> str | None:
    """Send a password reset email to the user.

    Args:
        to_email: The user's email address
        reset_link: The full reset URL

    Returns:
        str or None: Error message if sending failed, None on success
    """
    subject = "Password Reset Request"
    body = (
        f"You have requested a password reset.\n\n"
        f"Click the link below to reset your password. "
        f"This link expires in 30 minutes.\n\n"
        f"{reset_link}\n\n"
        f"If you did not request this, please ignore this email."
    )
    return send_email_raw(to_email, subject, body)

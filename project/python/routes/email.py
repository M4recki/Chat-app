from email.message import EmailMessage
from smtplib import SMTPException, SMTP_SSL
from ssl import create_default_context

from ..settings import settings


def send_email(email_address, subject, message):
    """Send an email using SMTP.

    Args:
        email_address: The sender's email address (included in body)
        subject: The email subject
        message: The email body

    Returns:
        str or None: Error message if sending failed, None on success
    """
    if settings.testing:
        return None

    if not settings.email_receiver or not settings.email_password:
        return "Email configuration is incomplete"

    body = f"From: {email_address}\n\n{message}"

    email = EmailMessage()
    email["From"] = settings.email_sender
    email["To"] = settings.email_receiver
    email["Subject"] = subject
    email.set_content(body)

    context = create_default_context()

    try:
        with SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(settings.email_sender, settings.email_password)
            smtp.sendmail(
                settings.email_sender,
                settings.email_receiver,
                email.as_string(),
            )
    except (SMTPException, OSError):
        return "Failed to send email. Please try again later."

    return None

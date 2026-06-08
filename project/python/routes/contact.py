from fastapi import APIRouter, Depends, Form, Request

from .email import send_email
from .helpers import validate_csrf_optional
from .template import render_template

router = APIRouter()


@router.get("/contact", name="contact")
def contact_page(request: Request):
    """Render the contact page.

    Args:
        request: The request object

    Returns:
        Response: Contact page template response
    """
    return render_template("contact.html", request)


@router.post("/contact", dependencies=[Depends(validate_csrf_optional)])
async def contact_data(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    """Handle contact form submission.

    Args:
        request: The request object
        name: The name form field
        email: The email form field
        subject: The subject form field
        message: The message form field

    Returns:
        Response: Redirect to home page on success
    """
    errors = {}

    if len(message) < 10:
        errors["message"] = "Message must contain at least 10 characters"

    error = send_email(email, subject, message)
    if error:
        errors["email"] = error

    if errors:
        return render_template("contact.html", request, errors=errors)

    flash_messages = ["Your message has been sent"]

    return render_template("main_page.html", request, flash_messages=flash_messages)

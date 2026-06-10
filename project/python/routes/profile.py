from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from ..database import async_session_scope
from ..models import User
from .helpers import get_current_user, validate_csrf, validate_email
from .template import templates

router = APIRouter()


@router.get("/update_profile")
async def update_profile_page(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Render the update profile page.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: Update profile page template
    """
    return templates.TemplateResponse(
        request,
        "update_profile.html",
        {"request": request, "user": user, "errors": {}},
    )


@router.post("/update_profile", dependencies=[Depends(validate_csrf)])
async def update_profile_data(
    request: Request,
    avatar: UploadFile = File(None),
    name: str = Form(None),
    surname: str = Form(None),
    email: str = Form(None),
    password: str = Form(None),
    confirm_password: str = Form(None),
    user: User = Depends(get_current_user),
) -> Response:
    """Handle update profile form submission.

    Args:
        request: The request object
        avatar: The avatar upload field
        name: The name form field
        surname: The surname form field
        email: The email form field
        password: The password form field
        confirm_password: The confirm password form field
        user: The authenticated user

    Returns:
        Response: Redirect or update profile template
    """

    errors = {}

    if email is not None and not validate_email(email):
        errors["email"] = "Invalid email format"

    if password is not None and len(password) < 8:
        errors["password"] = "Password must be at least 8 characters long"

    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match"

    if errors:
        return templates.TemplateResponse(
            request,
            "update_profile.html",
            {"request": request, "user": user, "errors": errors},
        )

    if avatar and avatar.content_type:
        if avatar.content_type not in ["image/jpeg", "image/png"]:
            errors["avatar"] = "Avatar must be a JPEG or PNG file"
        else:
            avatar_data = await avatar.read()
            if len(avatar_data) > 5 * 1024 * 1024:
                errors["avatar"] = "Avatar must be smaller than 5 MB"
            else:
                user.avatar = avatar_data

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user.id))
        updated_user = result.scalar()
        if name is not None:
            updated_user.name = name
        if surname is not None:
            updated_user.surname = surname
        if email is not None:
            updated_user.email = email
        if password is not None:
            updated_user.password = generate_password_hash(password)
        if avatar and avatar.content_type:
            updated_user.avatar = user.avatar

    return RedirectResponse(request.url_for("single_chat"), status_code=303)

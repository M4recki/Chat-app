from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from ..database import async_session_scope
from ..models import User
from ..settings import settings
from .forms import ProfileUpdateForm, profile_update_form
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
    form: ProfileUpdateForm = Depends(profile_update_form),
    user: User = Depends(get_current_user),
) -> Response:
    errors = {}

    if form.email is not None and not validate_email(form.email):
        errors["email"] = "Invalid email format"

    if form.password is not None and len(form.password) < settings.password_min_length:
        errors["password"] = (
            f"Password must be at least {settings.password_min_length} characters long"
        )

    if form.password != form.confirm_password:
        errors["confirm_password"] = "Passwords do not match"

    if form.avatar and form.avatar.content_type:
        if form.avatar.content_type not in ["image/jpeg", "image/png"]:
            errors["avatar"] = "Avatar must be a JPEG or PNG file"
        else:
            avatar_data = await form.avatar.read()
            if len(avatar_data) > settings.max_avatar_size:
                errors["avatar"] = (
                    "Avatar must be smaller than "
                    f"{settings.max_avatar_size // (1024 * 1024)} MB"
                )
            else:
                user.avatar = avatar_data

    if errors:
        return templates.TemplateResponse(
            request,
            "update_profile.html",
            {"request": request, "user": user, "errors": errors},
        )

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user.id))
        updated_user = result.scalar()
        if form.name is not None:
            updated_user.name = form.name
        if form.surname is not None:
            updated_user.surname = form.surname
        if form.email is not None:
            updated_user.email = form.email
        if form.password is not None:
            updated_user.password = generate_password_hash(form.password)
        if form.avatar and form.avatar.content_type:
            updated_user.avatar = user.avatar

    return RedirectResponse(request.url_for("single_chat"), status_code=303)

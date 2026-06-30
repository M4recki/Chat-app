from base64 import b64encode
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..database import session_scope
from ..models import User
from .helpers import authentication_in_header, csrf_context, decode_access_token

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_AVATAR_PATH = PROJECT_DIR / "static" / "img" / "default avatar.png"


def encode_avatar(user: User | None) -> str:
    """Encode user avatar to base64 string for display in templates.

    Args:
        user: The user object containing the avatar binary data

    Returns:
        str: The base64-encoded avatar string, or an empty string
            if no avatar is found
    """
    if user and user.avatar:
        return b64encode(user.avatar).decode()
    return ""


# User image


def user_image(request: Request) -> dict[str, str]:
    """Get user image from database.

    Args:
        request: The request object

    Returns:
        dict: A dict with 'user_image' key containing base64-encoded
            avatar, or empty string if not found
    """
    if not isinstance(request, Request):
        return {"user_image": ""}

    user_id = decode_access_token(request.cookies)
    if not user_id:
        return {"user_image": ""}

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if user and user.avatar:
        return {"user_image": b64encode(user.avatar).decode()}
    return {"user_image": ""}


# Username


def user_name(request: Request) -> dict[str, str | None]:
    """Get username from database.

    Args:
        request: The request object

    Returns:
        dict: A dict with 'user_name' key containing the user's name,
            or None if not found
    """
    if not isinstance(request, Request):
        return {"user_name": None}

    user_id = decode_access_token(request.cookies)
    if not user_id:
        return {"user_name": None}

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if user:
        return {"user_name": user.name}
    return {"user_name": None}


# Current year in footer


def current_year(request: Request):
    """Get the current year.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the current year
    """
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent.parent / "templates",
    context_processors=[
        authentication_in_header,
        user_image,
        user_name,
        current_year,
        csrf_context,
    ],
)


def render_template(name: str, request: Request, **kwargs: object) -> HTMLResponse:
    """Render template with auto-injected context data.

    Args:
        name: Template filename
        request: Request object
        **kwargs: Additional context variables

    Returns:
        HTMLResponse with rendered template
    """
    return templates.TemplateResponse(request, name, kwargs)

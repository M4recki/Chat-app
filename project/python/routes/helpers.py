import re
from hashlib import sha256

from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadSignature, SignatureExpired

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select

from ..database import async_session_scope, session_scope
from ..models import Channel, Friend, User
from ..settings import settings


def authentication_in_header(request: object) -> dict:
    """Check if user is authenticated based on access token in header.

    Args:
        request (Request): The incoming request object.

    Returns:
        dict: A dictionary with a boolean indicating if the user
            is authenticated
    """
    if not isinstance(request, Request):
        return {"is_authenticated": False}
    token = request.cookies.get("access_token")
    if not token:
        return {"is_authenticated": False}

    s = Serializer(settings.chat_secret_key)
    try:
        s.loads(token, max_age=settings.token_max_age)
        return {"is_authenticated": True}
    except (SignatureExpired, BadSignature):
        return {"is_authenticated": False}


async def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated based on access token.

    Args:
        request (Request): The request object

    Raises:
        HTTPException: Error description

    Returns:
        bool: True if user is authenticated, False otherwise
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session token")

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return True


async def get_user_from_request(
    request: Request,
    max_age: int = settings.token_max_age,
):
    """Get user object and ID from request based on access token.

    Args:
        request (Request): The request object
        max_age (int): The maximum age of the token in seconds

    Returns:
        tuple: A tuple containing the user object and user ID, or
            (None, None) if not found
    """
    token = request.cookies.get("access_token")
    if not token:
        return None, None

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=max_age).get("user_id")
    except (SignatureExpired, BadSignature):
        return None, None

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()

    return user, user_id


def get_user(user_id: int) -> User | None:
    """Get user object from database by user ID.

    Args:
        user_id: The ID of the user to retrieve

    Returns:
        User: The user object if found, None otherwise
    """
    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()
    return user


async def get_current_user(request: Request) -> User:
    """FastAPI dependency: extract authenticated user from access token cookie.

    Args:
        request: The incoming request

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException 401: If token is missing, invalid, or user not found
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session token")

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_user_id(request: Request) -> int | None:
    """Extract user ID from the access token cookie.

    Args:
        request: The incoming request

    Returns:
        int or None: The user ID if authenticated, None otherwise
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    s = Serializer(settings.chat_secret_key)
    try:
        return s.loads(token, max_age=settings.token_max_age).get("user_id")
    except (SignatureExpired, BadSignature):
        return None


def csrf_context(request: Request) -> dict:
    """Template context processor providing a CSRF token
    for all users (authenticated and anonymous).

    Args:
        request: The incoming request

    Returns:
        dict: A dict with a 'csrf_token' key
    """
    user_id = get_current_user_id(request) or 0
    return {"csrf_token": generate_csrf_token(user_id)}


async def validate_csrf_optional(request: Request):
    """Validate CSRF token for endpoints accessible
    without authentication (login, sign_up, contact).

    Checks signature validity and expiry only —
    does not require the user to be logged in.

    Args:
        request: The incoming request

    Raises:
        HTTPException 403: If CSRF token is missing or invalid
    """
    token: str = request.headers.get("X-CSRF-Token", "")
    if not token:
        form = await request.form()
        raw = form.get("csrf_token", "")
        token = raw if isinstance(raw, str) else ""
    if not token or not is_csrf_token_valid(token, 0):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def validate_csrf(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Validate CSRF token from X-CSRF-Token header or form field.

    Args:
        request: The incoming request
        user: The authenticated user (from dependency chain)

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 403: If CSRF token is missing or invalid
    """
    token: str = request.headers.get("X-CSRF-Token", "")
    if not token:
        form = await request.form()
        raw = form.get("csrf_token", "")
        token = raw if isinstance(raw, str) else ""
    if not token or not is_csrf_token_valid(token, user.id):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def generate_csrf_token(user_id: int) -> str:
    """Generate a signed CSRF token for the given user.

    Args:
        user_id: The user ID to encode in the token

    Returns:
        str: A signed CSRF token string
    """
    s = Serializer(settings.chat_secret_key + "_csrf")
    return s.dumps({"user_id": user_id})

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> bool:
    """Check if the given string is a valid email address.

    Args:
        email: The email string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return bool(_EMAIL_PATTERN.match(email))


async def get_friendship(db, user_id: int, other_id: int):
    """Find a friendship between two users (either direction)."""
    result = await db.execute(
        select(Friend).filter(
            or_(
                (Friend.user1_id == user_id) & (Friend.user2_id == other_id),
                (Friend.user1_id == other_id) & (Friend.user2_id == user_id),
            )
        )
    )
    return result.scalar()


async def get_channel(db, user_id: int, other_id: int):
    """Find a channel between two users (either direction)."""
    result = await db.execute(
        select(Channel).filter(
            or_(
                (Channel.user1_id == user_id) & (Channel.user2_id == other_id),
                (Channel.user1_id == other_id) & (Channel.user2_id == user_id),
            )
        )
    )
    return result.scalar()


def generate_channel_id(user1_id: int, user2_id: int) -> str:
    """Generate a unique channel ID."""
    unique_string = f"{user1_id}{user2_id}"
    return sha256(unique_string.encode()).hexdigest()


async def create_channel(db, user_id: int, other_id: int) -> Channel:
    """Create a new channel between two users."""
    channel_id = generate_channel_id(user_id, other_id)
    channel = Channel(
        channel_id=channel_id,
        user1_id=user_id,
        user2_id=other_id,
    )
    db.add(channel)
    return channel


async def get_or_create_channel(db, user_id: int, other_id: int) -> Channel:
    """Find an existing channel between two users or create a new one."""
    existing = await get_channel(db, user_id, other_id)
    if existing:
        return existing
    return await create_channel(db, user_id, other_id)


async def get_friendship_by_direction(db, user1_id: int, user2_id: int):
    """Find a friendship where user1_id sent a request to user2_id."""
    result = await db.execute(
        select(Friend).filter(
            Friend.user1_id == user1_id, Friend.user2_id == user2_id
        )
    )
    return result.scalar()


def is_csrf_token_valid(token: str, user_id: int) -> bool:
    """Verify a CSRF token matches the given user.

    Args:
        token: The CSRF token to validate
        user_id: The expected user ID

    Returns:
        bool: True if the token is valid and matches the user
    """
    s = Serializer(settings.chat_secret_key + "_csrf")
    try:
        data = s.loads(token, max_age=settings.token_max_age)
        return data.get("user_id") == user_id
    except (BadSignature, SignatureExpired):
        return False

from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadSignature, SignatureExpired

from fastapi import Depends, HTTPException, Request

from ..database import session_scope
from ..models import User
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


def is_authenticated(request: Request):
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return True


def get_user_from_request(request: Request, max_age: int = settings.token_max_age):
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    return user, user_id


def get_user(user_id):
    """Get user object from database by user ID.

    Args:
        user_id: The ID of the user to retrieve

    Returns:
        User: The user object if found, None otherwise
    """
    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()
    return user


def get_current_user(request: Request) -> User:
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

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
    """Template context processor providing a CSRF token for authenticated users.

    Args:
        request: The incoming request

    Returns:
        dict: A dict with a 'csrf_token' key, empty string if unauthenticated
    """
    user_id = get_current_user_id(request)
    if user_id is None:
        return {"csrf_token": ""}
    return {"csrf_token": generate_csrf_token(user_id)}


async def validate_csrf(request: Request, user: User = Depends(get_current_user)):
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

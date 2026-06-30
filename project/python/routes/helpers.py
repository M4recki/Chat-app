import re
from datetime import datetime
from hashlib import sha256
from json import dumps
from typing import cast

from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadSignature, SignatureExpired

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select

from ..connection_manager import manager
from ..database import async_session_scope, session_scope
from ..models import (
    Channel,
    Friend,
    FriendStatus,
    GroupChat,
    GroupMember,
    GroupMessage,
    Message,
    User,
)
from ..settings import settings


def decode_access_token(cookies: dict) -> int | None:
    """Extract user ID from access token cookie.

    Args:
        cookies: A dict-like object with cookie values

    Returns:
        int or None: The user ID if token is valid, None otherwise
    """
    raw = cookies.get(settings.access_token_cookie)
    if not isinstance(raw, str):
        return None
    token: str = raw
    s = Serializer(settings.chat_secret_key)
    try:
        return cast(
            int | None, s.loads(token, max_age=settings.token_max_age).get("user_id")
        )
    except (BadSignature, SignatureExpired):
        return None


def authentication_in_header(request: object) -> dict:
    """Check if user is authenticated based on access token in cookie.

    Args:
        request: The incoming request object

    Returns:
        dict: A dictionary with a boolean indicating if the user
            is authenticated
    """
    if not isinstance(request, Request):
        return {"is_authenticated": False}
    user_id = decode_access_token(request.cookies)
    return {"is_authenticated": user_id is not None}


async def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated based on access token.

    Args:
        request: The request object

    Raises:
        HTTPException 401: If not authenticated or user not found

    Returns:
        bool: True if user is authenticated
    """
    user_id = decode_access_token(request.cookies)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    async with async_session_scope() as db:
        user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return True


async def get_user_from_request(request: Request) -> tuple[User | None, int | None]:
    """Get user object and ID from request based on access token.

    Args:
        request: The request object

    Returns:
        tuple: A tuple containing the user object and user ID, or
            (None, None) if not found
    """
    user_id = decode_access_token(request.cookies)
    if not user_id:
        return None, None

    async with async_session_scope() as db:
        user = await get_user_by_id(db, user_id)

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
    user_id = decode_access_token(request.cookies)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    async with async_session_scope() as db:
        user = await get_user_by_id(db, user_id)

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
    return decode_access_token(request.cookies)


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


async def get_friend_status_map(
    db, user_id: int, friend_ids: list[int]
) -> dict[int, str]:
    """Get a map of friend_id -> status for a list of friend IDs."""
    result = await db.execute(
        select(Friend).filter(
            or_(
                (Friend.user1_id == user_id) & (Friend.user2_id.in_(friend_ids)),
                (Friend.user2_id == user_id) & (Friend.user1_id.in_(friend_ids)),
            )
        )
    )
    status_map = {}
    for fs in result.scalars().all():
        other_id = fs.user2_id if fs.user1_id == user_id else fs.user1_id
        status_map[other_id] = fs.status
    return status_map


async def get_channel_id_map(db, user_id: int, friend_ids: list[int]) -> dict[int, str]:
    """Get a map of friend_id -> channel_id for a list of friend IDs."""
    result = await db.execute(
        select(Channel).filter(
            or_(
                (Channel.user1_id == user_id) & (Channel.user2_id.in_(friend_ids)),
                (Channel.user2_id == user_id) & (Channel.user1_id.in_(friend_ids)),
            )
        )
    )
    channel_map = {}
    for ch in result.scalars().all():
        other_id = ch.user2_id if ch.user1_id == user_id else ch.user1_id
        channel_map[other_id] = ch.channel_id
    return channel_map


async def get_user_by_id(db, user_id: int) -> User | None:
    """Get a user by ID."""
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalar()


async def get_message_or_404(db, message_id: int) -> Message:
    """Get a message by ID or raise 404."""
    result = await db.execute(select(Message).filter(Message.id == message_id))
    message = result.scalar()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


async def get_group_message_or_404(db, message_id: int) -> GroupMessage:
    """Get a group message by ID or raise 404."""
    result = await db.execute(
        select(GroupMessage).filter(GroupMessage.id == message_id)
    )
    message = result.scalar()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


async def get_group_or_404(db, group_id: int) -> GroupChat:
    result = await db.execute(select(GroupChat).filter(GroupChat.id == group_id))
    group = result.scalar()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


async def require_group_member(db, group_id: int, user_id: int):
    result = await db.execute(
        select(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    if not result.scalar():
        raise HTTPException(status_code=403, detail="Not a member of this group")


async def get_group_member(db, group_id: int, user_id: int) -> GroupMember | None:
    result = await db.execute(
        select(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    return result.scalar()


async def get_group_members(db, group_id: int) -> list[GroupMember]:
    result = await db.execute(
        select(GroupMember).filter(GroupMember.group_id == group_id)
    )
    return result.scalars().all()


async def get_users_by_ids(db, user_ids: list[int]) -> list[User]:
    if not user_ids:
        return []
    result = await db.execute(select(User).filter(User.id.in_(user_ids)))
    return result.scalars().all()


async def load_user_groups(db, user_id: int) -> tuple[list[GroupChat], dict[int, int]]:
    result = await db.execute(
        select(GroupMember).filter(GroupMember.user_id == user_id)
    )
    memberships = result.scalars().all()
    group_ids = [m.group_id for m in memberships]
    groups = []
    group_member_counts: dict[int, int] = {}
    if group_ids:
        result_groups = await db.execute(
            select(GroupChat).filter(GroupChat.id.in_(group_ids))
        )
        groups = result_groups.scalars().all()
        for g in groups:
            member_count = len(
                (
                    await db.execute(
                        select(GroupMember).filter(GroupMember.group_id == g.id)
                    )
                )
                .scalars()
                .all()
            )
            group_member_counts[g.id] = member_count
    return groups, group_member_counts


async def get_accepted_friends(db, user_id: int) -> list[User]:
    result = await db.execute(
        select(User)
        .distinct()
        .join(Friend, or_(Friend.user1_id == User.id, Friend.user2_id == User.id))
        .filter(
            Friend.status == FriendStatus.ACCEPTED,
            or_(
                (Friend.user1_id == user_id) & (User.id == Friend.user2_id),
                (Friend.user2_id == user_id) & (User.id == Friend.user1_id),
            ),
        )
    )
    return result.scalars().all()


async def get_friendship_by_direction(db, user1_id: int, user2_id: int):
    """Find a friendship where user1_id sent a request to user2_id."""
    result = await db.execute(
        select(Friend).filter(Friend.user1_id == user1_id, Friend.user2_id == user2_id)
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


async def edit_message_broadcast(message, user_id: int, content: str, channel_id: str):
    """Edit a message and broadcast the update via WebSocket.

    Args:
        message: The message object to edit
        user_id: The ID of the user requesting the edit
        content: The new message content
        channel_id: The channel to broadcast to

    Raises:
        HTTPException 403: If the user is not the message author
        HTTPException 400: If content is empty
    """
    if message.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your message")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    now = datetime.now()
    message.content = content
    message.edited_at = now

    await manager.broadcast(
        dumps(
            {
                "type": "edit_message",
                "message_id": message.id,
                "content": content,
                "edited_at": now.isoformat(),
            }
        ),
        channel_id,
    )


async def delete_message_broadcast(message, user_id: int, channel_id: str):
    """Delete a message and broadcast the deletion via WebSocket.

    Args:
        message: The message object to delete
        user_id: The ID of the user requesting deletion
        channel_id: The channel to broadcast to

    Raises:
        HTTPException 403: If the user is not the message author
    """
    if message.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your message")

    await manager.broadcast(
        dumps(
            {
                "type": "delete_message",
                "message_id": message.id,
            }
        ),
        channel_id,
    )

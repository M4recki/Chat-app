from base64 import b64encode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import or_, select

from ..database import async_session_scope
from ..models import Channel, Friend, FriendStatus, Message, User
from .helpers import (
    create_channel,
    get_current_user,
    get_friendship,
)
from .template import encode_avatar, templates

router = APIRouter()


@router.get("/single_chat")
async def single_chat(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Display the user's chat channels.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: Single chat template
    """
    async with async_session_scope() as db:
        result = await db.execute(
            select(User)
            .distinct()
            .join(
                Friend,
                or_(Friend.user1_id == User.id, Friend.user2_id == User.id),
            )
            .filter(
                Friend.status.in_(
                    [FriendStatus.ACCEPTED.value, FriendStatus.BLOCKED.value]
                ),
                or_(
                    (Friend.user1_id == user.id) & (User.id == Friend.user2_id),
                    (Friend.user2_id == user.id) & (User.id == Friend.user1_id),
                ),
            )
        )
        friends = result.scalars().all()

        friend_avatars = {}
        friend_status_map = {}
        channel_ids = {}

        if friends:
            friend_ids = [f.id for f in friends]
            friend_avatars = {f.id: b64encode(f.avatar).decode() for f in friends}

            result_friendships = await db.execute(
                select(Friend).filter(
                    or_(
                        (Friend.user1_id == user.id)
                        & (Friend.user2_id.in_(friend_ids)),
                        (Friend.user2_id == user.id)
                        & (Friend.user1_id.in_(friend_ids)),
                    )
                )
            )
            for fs in result_friendships.scalars().all():
                other_id = fs.user2_id if fs.user1_id == user.id else fs.user1_id
                friend_status_map[other_id] = fs.status

            result_channels = await db.execute(
                select(Channel).filter(
                    or_(
                        (Channel.user1_id == user.id)
                        & (Channel.user2_id.in_(friend_ids)),
                        (Channel.user2_id == user.id)
                        & (Channel.user1_id.in_(friend_ids)),
                    )
                )
            )
            for ch in result_channels.scalars().all():
                other_id = ch.user2_id if ch.user1_id == user.id else ch.user1_id
                channel_ids[other_id] = ch.channel_id

            for fid in friend_ids:
                if fid not in channel_ids:
                    ch = await create_channel(db, user.id, fid)
                    channel_ids[fid] = ch.channel_id

    return templates.TemplateResponse(
        request,
        "single_chat.html",
        {
            "request": request,
            "friends": friends,
            "user": user,
            "friend_avatars": friend_avatars,
            "friend_status_map": friend_status_map,
            "channel_ids": channel_ids,
        },
    )


@router.get("/friend_chat/{channel_id}/{friend_id}")
async def friend_chat_page(
    request: Request,
    channel_id: str,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Retrieve chat messages for a friend chat channel.

    Args:
        request (Request): The HTTP request object
        channel_id (str): The ID of the chat channel
        friend_id (int): The ID of the friend
        user: The authenticated user

    Raises:
        HTTPException: If the channel is not found

    Returns:
        TemplateResponse: Rendered template with chat context
    """
    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == friend_id))
        friend = result.scalar()
        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        result_messages = await db.execute(
            select(Message)
            .filter(Message.channel_id == channel_id)
            .order_by(Message.created_at.asc())
        )
        messages = result_messages.scalars().all()

        # Bulk-load all message authors to avoid N+1 queries
        author_ids = {m.user_id for m in messages}
        if author_ids:
            result_authors = await db.execute(
                select(User).filter(User.id.in_(author_ids))
            )
            users_map = {u.id: u for u in result_authors.scalars().all()}
        else:
            users_map = {}

        result_channel = await db.execute(
            select(Channel).filter(Channel.channel_id == channel_id)
        )
        channel = result_channel.scalar()

        friend_status = await get_friendship(db, user.id, friend_id)
        friend_status_value = friend_status.status if friend_status else None

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

    avatar_b64 = encode_avatar(user)
    friend_avatar_b64 = encode_avatar(friend)

    return templates.TemplateResponse(
        request,
        "friend_chat.html",
        {
            "request": request,
            "user": user,
            "avatar_b64": avatar_b64,
            "friend": friend,
            "friend_avatar_b64": friend_avatar_b64,
            "friend_status": friend_status_value,
            "messages": messages,
            "channel_id": channel_id,
            "users": users_map,
        },
    )

from base64 import b64encode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import or_, select

from ..database import async_session_scope
from ..models import Channel, Friend, FriendStatus, User
from .helpers import create_channel, get_current_user
from .template import templates

router = APIRouter()


@router.get("/search_user")
async def search_user(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Search for and return other users.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: User search template
    """
    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id != user.id))
        users = result.scalars().all()

        result_friends = await db.execute(
            select(Friend).filter(
                or_(Friend.user1_id == user.id, Friend.user2_id == user.id)
            )
        )
        friend_statuses = result_friends.scalars().all()

        friend_status_map = {}
        channel_ids = {}
        for friend in friend_statuses:
            if friend.user1_id == user.id:
                friend_id = friend.user2_id
            else:
                friend_id = friend.user1_id
            friend_status_map[friend_id] = friend.status

        accepted_ids = [
            fid
            for fid, st in friend_status_map.items()
            if st == FriendStatus.ACCEPTED.value
        ]

        if accepted_ids:
            result_channels = await db.execute(
                select(Channel).filter(
                    or_(
                        (Channel.user1_id == user.id)
                        & (Channel.user2_id.in_(accepted_ids)),
                        (Channel.user2_id == user.id)
                        & (Channel.user1_id.in_(accepted_ids)),
                    )
                )
            )
            for ch in result_channels.scalars().all():
                other_id = ch.user2_id if ch.user1_id == user.id else ch.user1_id
                channel_ids[other_id] = ch.channel_id

            for fid in accepted_ids:
                if fid not in channel_ids:
                    ch = await create_channel(db, user.id, fid)
                    channel_ids[fid] = ch.channel_id

        avatar_map = {u.id: b64encode(u.avatar).decode() for u in users if u.avatar}

    return templates.TemplateResponse(
        request,
        "search_user.html",
        {
            "request": request,
            "users": users,
            "avatar_map": avatar_map,
            "friend_status_map": friend_status_map,
            "channel_ids": channel_ids,
        },
    )

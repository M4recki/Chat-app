from base64 import b64encode

from fastapi import APIRouter, Depends, Request

from ..database import session_scope
from ..models import Channel, Friend, User
from .chat import generate_channel_id
from .helpers import get_current_user
from .template import templates

router = APIRouter()


@router.get("/search_user")
async def search_user(request: Request, user: User = Depends(get_current_user)):
    """Search for and return other users.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: User search template
    """
    with session_scope() as db:
        users = db.query(User).filter(User.id != user.id).all()

        friend_statuses = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user.id)
                | (Friend.user2_id == user.id)
            )
            .all()
        )

        friend_status_map = {}
        channel_ids = {}
        for friend in friend_statuses:
            if friend.user1_id == user.id:
                friend_id = friend.user2_id
            else:
                friend_id = friend.user1_id

            friend_status_map[friend_id] = friend.status

            if friend.status == "accepted":
                existing_channel = (
                    db.query(Channel)
                    .filter(
                        (
                            (Channel.user1_id == user.id)
                            & (Channel.user2_id == friend_id)
                        )
                        | (
                            (Channel.user1_id == friend_id)
                            & (Channel.user2_id == user.id)
                        )
                    )
                    .first()
                )

                if existing_channel:
                    channel_ids[friend_id] = existing_channel.channel_id
                else:
                    channel_id = generate_channel_id(user.id, friend_id)
                    new_channel = Channel(
                        channel_id=channel_id,
                        user1_id=user.id,
                        user2_id=friend_id,
                    )
                    db.add(new_channel)
                    db.commit()
                    channel_ids[friend_id] = channel_id

        avatar_map = {
            u.id: b64encode(u.avatar).decode()
            for u in users if u.avatar
        }

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

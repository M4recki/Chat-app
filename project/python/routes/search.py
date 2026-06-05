from base64 import b64encode
from hashlib import sha256

from fastapi import APIRouter, Depends, Request
from itsdangerous import URLSafeTimedSerializer as Serializer

from ..database import session_scope
from ..models import Channel, Friend, User
from ..settings import settings
from .chat import generate_channel_id
from .helpers import is_authenticated
from .template import render_template, templates

router = APIRouter()


@router.get("/search_user", dependencies=[Depends(is_authenticated)])
async def search_user(request: Request):
    """Search for and return other users.

    Args:
        request: The request object

    Returns:
        Response: User search template
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            users = db.query(User).filter(User.id != user_id).all()

            friend_statuses = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    | (Friend.user2_id == user_id)
                )
                .all()
            )

            friend_status_map = {}
            channel_ids = {}
            for friend in friend_statuses:
                if friend.user1_id == user_id:
                    friend_id = friend.user2_id
                else:
                    friend_id = friend.user1_id

                friend_status_map[friend_id] = friend.status

                if friend.status == "accepted":
                    existing_channel = (
                        db.query(Channel)
                        .filter(
                            (
                                (Channel.user1_id == user_id)
                                & (Channel.user2_id == friend_id)
                            )
                            | (
                                (Channel.user1_id == friend_id)
                                & (Channel.user2_id == user_id)
                            )
                        )
                        .first()
                    )

                    if existing_channel:
                        channel_ids[friend_id] = existing_channel.channel_id
                    else:
                        channel_id = generate_channel_id(user_id, friend_id)
                        new_channel = Channel(
                            channel_id=channel_id,
                            user1_id=user_id,
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
    else:
        return render_template("login.html", request)

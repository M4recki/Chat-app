from base64 import b64encode
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request

from ..database import session_scope
from ..models import Channel, Friend, Message, User
from .helpers import get_current_user, get_user
from .template import encode_avatar, templates

router = APIRouter()


def generate_channel_id(user1_id, user2_id):
    """Generate a unique channel ID.

    Args:
        user1_id: ID of first user
        user2_id: ID of second user

    Returns:
        str: The generated channel ID
    """
    unique_string = f"{user1_id}{user2_id}"
    return sha256(unique_string.encode()).hexdigest()


@router.get("/single_chat")
async def single_chat(request: Request, user: User = Depends(get_current_user)):
    """Display the user's chat channels.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: Single chat template
    """
    with session_scope() as db:
        friends = (
            db.query(User)
            .join(
                Friend,
                (Friend.user1_id == User.id) | (Friend.user2_id == User.id),
            )
            .filter(
                Friend.status == "accepted",
                ((Friend.user1_id == user.id) & (User.id == Friend.user2_id))
                | (
                    (Friend.user2_id == user.id)
                    & (User.id == Friend.user1_id)
                ),
            )
            .all()
        )

        friend_status_value = None
        friend_avatars = {}
        channel_ids = {}

        if friends:
            for friend in friends:
                friend_id = friend.id
                friend_avatars[friend_id] = b64encode(friend.avatar).decode()

                existing_channel = (
                    db.query(Channel)
                    .filter(
                        (Channel.user1_id == user.id)
                        & (Channel.user2_id == friend_id)
                        | (Channel.user1_id == friend_id)
                        & (Channel.user2_id == user.id)
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

                friend_status = (
                    db.query(Friend)
                    .filter(
                        (Friend.user1_id == user.id)
                        & (Friend.user2_id == friend_id)
                        | (
                            (Friend.user1_id == friend_id)
                            & (Friend.user2_id == user.id)
                        )
                    )
                    .first()
                )

                friend_status_value = (
                    friend_status.status if friend_status else None
                )

    return templates.TemplateResponse(
        request,
        "single_chat.html",
        {
            "request": request,
            "friends": friends,
            "user": user,
            "friend_avatars": friend_avatars,
            "friend_status": friend_status_value,
            "channel_ids": channel_ids,
        },
    )


@router.get("/friend_chat/{channel_id}/{friend_id}")
async def friend_chat_page(
    request: Request,
    channel_id: str,
    friend_id: int,
    user: User = Depends(get_current_user),
):
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
    with session_scope() as db:
        friend = db.query(User).filter(User.id == friend_id).first()
        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        messages = (
            db.query(Message)
            .filter(Message.channel_id == channel_id)
            .all()
        )

        channel = (
            db.query(Channel)
            .filter(Channel.channel_id == channel_id)
            .first()
        )

        friend_status = (
            db.query(Friend)
            .filter(
                    (Friend.user1_id == user.id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user.id)
            )
            .first()
        )

        friend_status_value = (
            friend_status.status if friend_status else None
        )

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
            "get_user": get_user,
        },
    )

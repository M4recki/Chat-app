from base64 import b64encode
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from itsdangerous import URLSafeTimedSerializer as Serializer
from sqlalchemy.orm.exc import NoResultFound

from ..database import session_scope
from ..models import Friend, User
from ..settings import settings
from .helpers import is_authenticated
from .template import render_template, templates

router = APIRouter()


@router.get("/friend_requests", dependencies=[Depends(is_authenticated)])
async def friend_requests(request: Request):
    """Get pending friend requests for logged-in user.

    Args:
        request: The request object

    Returns:
        Response: Friend requests template
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")
        with session_scope() as db:
            friend_requests = (
                db.query(Friend)
                .filter(Friend.user2_id == user_id, Friend.status == "pending")
                .all()
            )
            friend_request_avatars = {
                fr.id: b64encode(fr.user1.avatar).decode()
                for fr in friend_requests
                if fr.user1.avatar
            }

        return templates.TemplateResponse(
            request,
            "friend_requests.html",
            {
                "request": request,
                "friend_requests": friend_requests,
                "friend_request_avatars": friend_request_avatars,
            },
        )
    else:
        return render_template("login.html", request)


@router.get(
    "/block_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
async def block_friend(request: Request, friend_id: int):
    """
    Block a friend from the user's friend list.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to block

    Returns:
        TemplateResponse: Rendered template on success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            existing_friendship = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user_id)
                )
                .first()
            )

            if existing_friendship:
                existing_friendship.status = "blocked"
                existing_friendship.last_sent = datetime.now()
                db.commit()
            else:
                new_friendship = Friend(
                    user1_id=user_id,
                    user2_id=friend_id,
                    status="blocked",
                    last_sent=datetime.now(),
                )
                db.add(new_friendship)
                db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


@router.get(
    "/unblock_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
async def unblock_friend(request: Request, friend_id: int):
    """
    Unblock a previously blocked friend.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to unblock

    Returns:
        TemplateResponse: Rendered template on success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            existing_friendship = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user_id)
                )
                .first()
            )

            if existing_friendship:
                existing_friendship.status = "accepted"
                existing_friendship.blocked_by_user = None
                existing_friendship.last_sent = datetime.now()
                db.commit()
            else:
                new_friendship = Friend(
                    user1_id=user_id,
                    user2_id=friend_id,
                    status="accepted",
                    last_sent=datetime.now(),
                )
                db.add(new_friendship)
                db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


@router.get(
    "/add_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
async def add_friend(request: Request, friend_id: int):
    """
    Add a friend request.

    Checks if a pending or denied request already exists,
    updates it if needed or creates a new one.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Raises:
        HTTPException: If request already sent recently

    Returns:
        TemplateResponse: On success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            try:
                existing_request = (
                    db.query(Friend)
                    .filter(
                        (Friend.user1_id == user_id)
                        & (Friend.user2_id == friend_id)
                    )
                    .one()
                )

                if existing_request.status == "pending":
                    if (
                        datetime.now() - existing_request.last_sent
                        > timedelta(days=14)
                    ):
                        existing_request.last_sent = datetime.now()
                        db.commit()
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Friend request already sent recently",
                        )
                elif existing_request.status == "denied":
                    existing_request.status = "pending"
                    existing_request.last_sent = datetime.now()
                    db.commit()

            except NoResultFound:
                new_friendship = Friend(
                    user1_id=user_id,
                    user2_id=friend_id,
                    status="pending",
                    last_sent=datetime.now(),
                )
                db.add(new_friendship)
                db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


@router.get(
    "/accept_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
async def accept_friend(request: Request, friend_id: int):
    """
    Accept a pending friend request.

    Updates the friend request status to accepted.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Returns:
        TemplateResponse: On success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            friend = (
                db.query(Friend)
                .filter(Friend.user1_id == friend_id,
                        Friend.user2_id == user_id)
                .first()
            )
            friend.status = "accepted"

            db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


@router.get(
    "/deny_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
async def deny_friend(request: Request, friend_id: int):
    """
    Deny a pending friend request.

    Updates the friend request status to denied.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Returns:
        TemplateResponse: On success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")

        with session_scope() as db:
            friend = (
                db.query(Friend)
                .filter(Friend.user1_id == friend_id,
                        Friend.user2_id == user_id)
                .first()
            )
            friend.status = "denied"

            db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)

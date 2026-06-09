from base64 import b64encode
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import async_session_scope
from ..models import Friend, FriendStatus, User
from .helpers import (
    get_current_user,
    get_friendship,
    get_friendship_by_direction,
    validate_csrf,
)
from .template import templates

router = APIRouter()


@router.get("/friend_requests")
async def friend_requests(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Get pending friend requests for logged-in user.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: Friend requests template
    """
    async with async_session_scope() as db:
        result = await db.execute(
            select(Friend)
            .options(selectinload(Friend.user1))
            .filter(
                Friend.user2_id == user.id, Friend.status == FriendStatus.PENDING.value
            )
        )
        friend_requests = result.scalars().all()
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


@router.post("/block_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def block_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Block a friend from the user's friend list.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to block
        user: The authenticated user

    Returns:
        TemplateResponse: Rendered template on success
    """
    async with async_session_scope() as db:
        existing_friendship = await get_friendship(db, user.id, friend_id)

        if existing_friendship:
            existing_friendship.status = FriendStatus.BLOCKED.value
            existing_friendship.blocked_by_user = user.id
            existing_friendship.last_sent = datetime.now()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.BLOCKED.value,
                blocked_by_user=user.id,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.post("/unblock_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def unblock_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Unblock a previously blocked friend.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to unblock
        user: The authenticated user

    Returns:
        TemplateResponse: Rendered template on success
    """
    async with async_session_scope() as db:
        existing_friendship = await get_friendship(db, user.id, friend_id)

        if existing_friendship:
            existing_friendship.status = FriendStatus.ACCEPTED.value
            existing_friendship.blocked_by_user = None
            existing_friendship.last_sent = datetime.now()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.ACCEPTED.value,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.post("/add_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def add_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Add a friend request.

    Checks if a pending or denied request already exists,
    updates it if needed or creates a new one.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend
        user: The authenticated user

    Raises:
        HTTPException: If request already sent recently

    Returns:
        TemplateResponse: On success
    """
    async with async_session_scope() as db:
        existing_request = await get_friendship_by_direction(
            db, user.id, friend_id
        )

        if existing_request:
            if existing_request.status == FriendStatus.PENDING.value:
                if datetime.now() - existing_request.last_sent > timedelta(days=14):
                    existing_request.last_sent = datetime.now()
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Friend request already sent recently",
                    )
            elif existing_request.status in (
                FriendStatus.DENIED.value,
                FriendStatus.BLOCKED.value,
            ):
                existing_request.status = FriendStatus.PENDING.value
                existing_request.last_sent = datetime.now()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.PENDING.value,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.post("/accept_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def accept_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Accept a pending friend request.

    Updates the friend request status to accepted.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend
        user: The authenticated user

    Returns:
        TemplateResponse: On success
    """
    async with async_session_scope() as db:
        friend = await get_friendship_by_direction(db, friend_id, user.id)
        friend.status = FriendStatus.ACCEPTED.value

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.post("/deny_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def deny_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Deny a pending friend request.

    Updates the friend request status to deny.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend
        user: The authenticated user

    Returns:
        TemplateResponse: On success
    """
    async with async_session_scope() as db:
        friend = await get_friendship_by_direction(db, friend_id, user.id)
        friend.status = FriendStatus.DENIED.value

    return RedirectResponse(request.url_for("single_chat"), status_code=303)

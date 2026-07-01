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


async def respond_to_friend_request(friend_id: int, user_id: int, status: str) -> None:
    """Respond to a pending friend request.

    Args:
        friend_id: The ID of the user who sent the request
        user_id: The ID of the current user responding
        status: The new status (accepted or denied)

    Raises:
        HTTPException 404: If no pending request is found
    """
    async with async_session_scope() as db:
        friend = await get_friendship_by_direction(db, friend_id, user_id)
        if friend is None:
            raise HTTPException(status_code=404, detail="Friend request not found")
        friend.status = status


async def set_friend_status(
    user_id: int,
    friend_id: int,
    status: str,
    blocked_by_user: int | None = None,
) -> None:
    """Set the friendship status between two users.

    Creates a new friendship record if one does not exist,
    otherwise updates the existing one.

    Args:
        user_id: The ID of the current user
        friend_id: The ID of the other user
        status: The friendship status to set
        blocked_by_user: The user ID who initiated the block (for block status)
    """
    async with async_session_scope() as db:
        existing = await get_friendship(db, user_id, friend_id)
        if existing:
            existing.status = status
            existing.last_sent = datetime.now()
            if blocked_by_user is not None:
                existing.blocked_by_user = blocked_by_user
            else:
                existing.blocked_by_user = None
        else:
            kwargs: dict = {
                "user1_id": user_id,
                "user2_id": friend_id,
                "status": status,
                "last_sent": datetime.now(),
            }
            if blocked_by_user is not None:
                kwargs["blocked_by_user"] = blocked_by_user
            db.add(Friend(**kwargs))


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
            .filter(Friend.user2_id == user.id, Friend.status == FriendStatus.PENDING)
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
    """Block a friend from the user's friend list.

    Args:
        request: The request object
        friend_id: The ID of the friend to block
        user: The authenticated user

    Returns:
        Response: Redirect to the single chat page
    """
    await set_friend_status(
        user.id, friend_id, FriendStatus.BLOCKED, blocked_by_user=user.id
    )
    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.post("/unblock_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def unblock_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Unblock a previously blocked friend.

    Args:
        request: The request object
        friend_id: The ID of the friend to unblock
        user: The authenticated user

    Returns:
        Response: Redirect to the single chat page
    """
    await set_friend_status(user.id, friend_id, FriendStatus.ACCEPTED)
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
        existing_request = await get_friendship_by_direction(db, user.id, friend_id)

        if existing_request:
            if existing_request.status == FriendStatus.PENDING:
                if datetime.now() - existing_request.last_sent > timedelta(days=14):
                    existing_request.last_sent = datetime.now()
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Friend request already sent recently",
                    )
            elif existing_request.status in (
                FriendStatus.DENIED,
                FriendStatus.BLOCKED,
            ):
                existing_request.status = FriendStatus.PENDING
                existing_request.last_sent = datetime.now()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.PENDING,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)

    return RedirectResponse(request.url_for("search_user"), status_code=303)


@router.post("/accept_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def accept_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Accept a pending friend request.

    Args:
        request: The request object
        friend_id: The ID of the user who sent the request
        user: The authenticated user

    Returns:
        Response: Redirect to the single chat page
    """
    await respond_to_friend_request(friend_id, user.id, FriendStatus.ACCEPTED)
    return RedirectResponse(request.url_for("friend_requests"), status_code=303)


@router.post("/deny_friend/{friend_id}", dependencies=[Depends(validate_csrf)])
async def deny_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Deny a pending friend request.

    Args:
        request: The request object
        friend_id: The ID of the user who sent the request
        user: The authenticated user

    Returns:
        Response: Redirect to the single chat page
    """
    await respond_to_friend_request(friend_id, user.id, FriendStatus.DENIED)
    return RedirectResponse(request.url_for("friend_requests"), status_code=303)

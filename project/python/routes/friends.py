from base64 import b64encode
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm.exc import NoResultFound

from ..database import session_scope
from ..models import Friend, FriendStatus, User
from .helpers import get_current_user
from .template import templates

router = APIRouter()


@router.get("/friend_requests")
async def friend_requests(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get pending friend requests for logged-in user.

    Args:
        request: The request object
        user: The authenticated user

    Returns:
        Response: Friend requests template
    """
    with session_scope() as db:
        friend_requests = (
            db.query(Friend)
            .filter(
                Friend.user2_id == user.id, Friend.status == FriendStatus.PENDING.value
            )
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


@router.get("/block_friend/{friend_id}")
async def block_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
):
    """
    Block a friend from the user's friend list.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to block
        user: The authenticated user

    Returns:
        TemplateResponse: Rendered template on success
    """
    with session_scope() as db:
        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user.id) & (Friend.user2_id == friend_id)
                | (Friend.user1_id == friend_id) & (Friend.user2_id == user.id)
            )
            .first()
        )

        if existing_friendship:
            existing_friendship.status = FriendStatus.BLOCKED.value
            existing_friendship.last_sent = datetime.now()
            db.commit()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.BLOCKED.value,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)
            db.commit()

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.get("/unblock_friend/{friend_id}")
async def unblock_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
):
    """
    Unblock a previously blocked friend.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to unblock
        user: The authenticated user

    Returns:
        TemplateResponse: Rendered template on success
    """
    with session_scope() as db:
        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user.id) & (Friend.user2_id == friend_id)
                | (Friend.user1_id == friend_id) & (Friend.user2_id == user.id)
            )
            .first()
        )

        if existing_friendship:
            existing_friendship.status = FriendStatus.ACCEPTED.value
            existing_friendship.blocked_by_user = None
            existing_friendship.last_sent = datetime.now()
            db.commit()
        else:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.ACCEPTED.value,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)
            db.commit()

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.get("/add_friend/{friend_id}")
async def add_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
):
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
    with session_scope() as db:
        try:
            existing_request = (
                db.query(Friend)
                .filter((Friend.user1_id == user.id) & (Friend.user2_id == friend_id))
                .one()
            )

            if existing_request.status == FriendStatus.PENDING.value:
                if datetime.now() - existing_request.last_sent > timedelta(days=14):
                    existing_request.last_sent = datetime.now()
                    db.commit()
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Friend request already sent recently",
                    )
            elif existing_request.status == FriendStatus.DENIED.value:
                existing_request.status = FriendStatus.PENDING.value
                existing_request.last_sent = datetime.now()
                db.commit()

        except NoResultFound:
            new_friendship = Friend(
                user1_id=user.id,
                user2_id=friend_id,
                status=FriendStatus.PENDING.value,
                last_sent=datetime.now(),
            )
            db.add(new_friendship)
            db.commit()

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.get("/accept_friend/{friend_id}")
async def accept_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
):
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
    with session_scope() as db:
        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user.id)
            .first()
        )
        friend.status = FriendStatus.ACCEPTED.value

        db.commit()

    return RedirectResponse(request.url_for("single_chat"), status_code=303)


@router.get("/deny_friend/{friend_id}")
async def deny_friend(
    request: Request,
    friend_id: int,
    user: User = Depends(get_current_user),
):
    """
    Deny a pending friend request.

    Updates the friend request status to denied.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend
        user: The authenticated user

    Returns:
        TemplateResponse: On success
    """
    with session_scope() as db:
        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user.id)
            .first()
        )
        friend.status = FriendStatus.DENIED.value

        db.commit()

    return RedirectResponse(request.url_for("single_chat"), status_code=303)

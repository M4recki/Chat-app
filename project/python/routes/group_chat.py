from base64 import b64encode
from datetime import datetime
from json import dumps

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select

from ..models import GroupChat, GroupMember, GroupMessage, User

from ..database import async_session_scope
from .helpers import (
    PAGE_SIZE,
    compute_group_unread_counts,
    delete_message_broadcast,
    edit_message_broadcast,
    get_accepted_friends,
    get_current_user,
    get_group_member,
    get_group_members,
    get_group_message_or_404,
    get_group_or_404,
    get_paginated_messages,
    get_user_by_id,
    get_users_by_ids,
    load_user_groups,
    mark_group_read,
    message_to_json,
    require_group_member,
    validate_csrf,
)
from .template import encode_avatar, templates

router = APIRouter()


@router.get("/group_chat_list")
async def group_chat_list(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Display the user's group chats.

    Args:
        request: The incoming HTTP request
        user: The authenticated user

    Returns:
        Response: Rendered group chat list page
    """
    async with async_session_scope() as db:
        groups, group_member_counts = await load_user_groups(db, user.id)

        unread_counts = await compute_group_unread_counts(
            db, user.id, [g.id for g in groups] if groups else []
        )

    return templates.TemplateResponse(
        request,
        "group_chat_list.html",
        {
            "request": request,
            "user": user,
            "groups": groups,
            "group_member_counts": group_member_counts,
            "unread_counts": unread_counts,
        },
    )


@router.get("/group_chat/{group_id}")
async def group_chat_page(
    request: Request,
    group_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """View a group chat page.

    Args:
        request: The incoming HTTP request
        group_id: The ID of the group to view
        user: The authenticated user

    Returns:
        Response: Rendered group chat page with messages and members

    Raises:
        HTTPException 404: If the group does not exist
        HTTPException 403: If the user is not a group member
    """
    async with async_session_scope() as db:
        group = await get_group_or_404(db, group_id)
        await require_group_member(db, group_id, user.id)

        total_messages, messages, users_map = await get_paginated_messages(
            db, GroupMessage, GroupMessage.group_id, group_id
        )

        members = await get_group_members(db, group_id)
        member_ids = [m.user_id for m in members]
        member_users_list = await get_users_by_ids(db, member_ids)
        member_users_map = {u.id: u for u in member_users_list}

        friend_candidates = []
        friend_candidate_avatars = {}
        if group.created_by == user.id:
            all_friends = await get_accepted_friends(db, user.id)
            friend_candidates = [f for f in all_friends if f.id not in member_ids]
            friend_candidate_avatars = {
                f.id: b64encode(f.avatar).decode() for f in friend_candidates
            }

        await mark_group_read(db, user.id, group_id)

    avatar_b64 = encode_avatar(user)
    has_more = total_messages > PAGE_SIZE

    return templates.TemplateResponse(
        request,
        "group_chat.html",
        {
            "request": request,
            "user": user,
            "avatar_b64": avatar_b64,
            "group": group,
            "messages": messages,
            "users": users_map,
            "members": members,
            "member_users": member_users_map,
            "friend_candidates": friend_candidates,
            "friend_candidate_avatars": friend_candidate_avatars,
            "has_more": has_more,
        },
    )


@router.get("/create_group")
async def create_group_form(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Show create group form.

    Args:
        request: The incoming HTTP request
        user: The authenticated user

    Returns:
        Response: Rendered create group form page with friend list
    """
    async with async_session_scope() as db:
        friends = await get_accepted_friends(db, user.id)

    return templates.TemplateResponse(
        request,
        "create_group.html",
        {
            "request": request,
            "user": user,
            "friends": friends,
        },
    )


@router.post("/create_group", dependencies=[Depends(validate_csrf)])
async def create_group(
    name: str = Form(...),
    member_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
) -> Response:
    """Create a new group chat.

    Args:
        name: The group name
        member_ids: Comma-separated list of user IDs to invite
        user: The authenticated user

    Returns:
        RedirectResponse: Redirects to the new group chat page

    Raises:
        HTTPException 400: If the group name is empty
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="Group name cannot be empty")

    async with async_session_scope() as db:
        group = GroupChat(
            name=name.strip(),
            created_at=datetime.now(),
            created_by=user.id,
        )
        db.add(group)
        await db.flush()

        db.add(
            GroupMember(
                group_id=group.id,
                user_id=user.id,
                joined_at=datetime.now(),
            )
        )

        invited_ids = [
            int(mid) for mid in member_ids.split(",") if mid.strip().isdigit()
        ]
        for uid in invited_ids:
            if not await get_user_by_id(db, uid):
                continue
            if await get_group_member(db, group.id, uid):
                continue
            db.add(
                GroupMember(
                    group_id=group.id,
                    user_id=uid,
                    joined_at=datetime.now(),
                )
            )

        await db.commit()
        group_id = group.id

    return RedirectResponse(
        url=f"/group_chat/{group_id}",
        status_code=303,
    )


@router.post("/add_group_member/{group_id}", dependencies=[Depends(validate_csrf)])
async def add_group_member(
    group_id: int,
    user_id: int = Form(...),
    user: User = Depends(get_current_user),
) -> Response:
    """Add a member to a group (creator only).

    Args:
        group_id: The ID of the group
        user_id: The ID of the user to add
        user: The authenticated user

    Returns:
        RedirectResponse: Redirects to the group chat page

    Raises:
        HTTPException 403: If the current user is not the group creator
        HTTPException 404: If the user to add does not exist
        HTTPException 400: If the user is already a member
    """
    async with async_session_scope() as db:
        group = await get_group_or_404(db, group_id)
        if group.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="Only the creator can add members"
            )

        if not await get_user_by_id(db, user_id):
            raise HTTPException(status_code=404, detail="User not found")

        if await get_group_member(db, group_id, user_id):
            raise HTTPException(status_code=400, detail="User is already a member")

        member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            joined_at=datetime.now(),
        )
        db.add(member)
        await db.commit()

    return RedirectResponse(
        url=f"/group_chat/{group_id}",
        status_code=303,
    )


@router.post("/remove_group_member/{group_id}", dependencies=[Depends(validate_csrf)])
async def remove_group_member(
    group_id: int,
    user_id: int = Form(...),
    user: User = Depends(get_current_user),
) -> Response:
    """Remove a member from a group (creator only).

    Args:
        group_id: The ID of the group
        user_id: The ID of the user to remove
        user: The authenticated user

    Returns:
        RedirectResponse: Redirects to the group chat page

    Raises:
        HTTPException 403: If the current user is not the group creator
        HTTPException 400: If attempting to remove the creator
        HTTPException 404: If the member is not found
    """
    async with async_session_scope() as db:
        group = await get_group_or_404(db, group_id)
        if group.created_by != user.id:
            raise HTTPException(
                status_code=403, detail="Only the creator can remove members"
            )

        if user_id == group.created_by:
            raise HTTPException(status_code=400, detail="Cannot remove the creator")

        member = await get_group_member(db, group_id, user_id)
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        await db.delete(member)
        await db.commit()

    return RedirectResponse(
        url=f"/group_chat/{group_id}",
        status_code=303,
    )


@router.post("/edit_group_message/{message_id}", dependencies=[Depends(validate_csrf)])
async def edit_group_message(
    message_id: int,
    content: str = Form(...),
    user: User = Depends(get_current_user),
) -> Response:
    """Edit a group message.

    Args:
        message_id: The ID of the message to edit
        content: The new message content
        user: The authenticated user

    Returns:
        Response: 200 OK

    Raises:
        HTTPException 403: If the user is not the message author
        HTTPException 404: If the message is not found
    """
    async with async_session_scope() as db:
        message = await get_group_message_or_404(db, message_id)
        await edit_message_broadcast(
            message, user.id, content, f"group_{message.group_id}"
        )
        await db.commit()

    return Response(status_code=200)


@router.post(
    "/delete_group_message/{message_id}", dependencies=[Depends(validate_csrf)]
)
async def delete_group_message(
    message_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a group message.

    Args:
        message_id: The ID of the message to delete
        user: The authenticated user

    Returns:
        Response: 200 OK

    Raises:
        HTTPException 403: If the user is not the message author
        HTTPException 404: If the message is not found
    """
    async with async_session_scope() as db:
        message = await get_group_message_or_404(db, message_id)
        channel_id = f"group_{message.group_id}"
        await delete_message_broadcast(message, user.id, channel_id)
        await db.delete(message)
        await db.commit()

    return Response(status_code=200)


@router.post("/leave_group/{group_id}", dependencies=[Depends(validate_csrf)])
async def leave_group(
    group_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Leave a group chat (creator cannot leave).

    Args:
        group_id: The ID of the group to leave
        user: The authenticated user

    Returns:
        RedirectResponse: Redirects to the group chat list

    Raises:
        HTTPException 400: If the user is the group creator
        HTTPException 404: If the user is not a member
    """
    async with async_session_scope() as db:
        group = await get_group_or_404(db, group_id)
        if group.created_by == user.id:
            raise HTTPException(
                status_code=400,
                detail="Creator cannot leave the group. Transfer ownership or delete the group.",
            )

        member = await get_group_member(db, group_id, user.id)
        if not member:
            raise HTTPException(status_code=404, detail="Not a member of this group")

        await db.delete(member)

    return RedirectResponse(
        url=f"/group_chat_list",
        status_code=303,
    )


@router.get("/api/group_messages/{group_id}")
async def api_group_messages(
    group_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Fetch paginated group messages as JSON.

    Args:
        group_id: The group ID
        offset: Number of messages to skip (from newest)
        limit: Maximum number of messages to return
        user: The authenticated user

    Returns:
        JSONResponse: JSON with messages list and has_more flag
    """
    async with async_session_scope() as db:
        await require_group_member(db, group_id, user.id)

        count_result = await db.execute(
            select(func.count())
            .select_from(GroupMessage)
            .filter(GroupMessage.group_id == group_id)
        )
        total = count_result.scalar()

        # Get messages ordered by created_at DESC (newest first), then reverse
        result_messages = await db.execute(
            select(GroupMessage)
            .filter(GroupMessage.group_id == group_id)
            .order_by(GroupMessage.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        msgs = list(reversed(result_messages.scalars().all()))

        author_ids = {m.user_id for m in msgs}
        users_map = {}
        if author_ids:
            users = await get_users_by_ids(db, list(author_ids))
            users_map = {u.id: {"name": u.name, "surname": u.surname} for u in users}

        messages_json = []
        for m in msgs:
            sender = users_map.get(m.user_id, {})
            messages_json.append(
                message_to_json(
                    m, f"{sender.get('name', '')} {sender.get('surname', '')}".strip()
                )
            )

        return JSONResponse(
            {
                "messages": messages_json,
                "has_more": (offset + limit) < total,
                "total": total,
            }
        )


@router.get("/group_members/{group_id}")
async def group_members(
    group_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """JSON endpoint listing group members.

    Args:
        group_id: The ID of the group
        user: The authenticated user

    Returns:
        Response: JSON array of members with id, name, surname

    Raises:
        HTTPException 403: If the user is not a group member
    """
    async with async_session_scope() as db:
        await require_group_member(db, group_id, user.id)

        members = await get_group_members(db, group_id)
        member_ids = [m.user_id for m in members]
        users = await get_users_by_ids(db, member_ids)

        member_list = [
            {
                "id": u.id,
                "name": u.name,
                "surname": u.surname,
            }
            for u in users
        ]

    return Response(
        content=dumps(member_list),
        media_type="application/json",
    )

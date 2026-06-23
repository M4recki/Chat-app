import asyncio
from datetime import datetime
from html import escape
from json import dumps, loads

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadSignature, SignatureExpired
from sqlalchemy import select

from .connection_manager import manager
from .database import async_session_scope
from .models import Channel, GroupMember, GroupMessage, Message, User
from .settings import settings

ws_router = APIRouter()

# Track pending "user left" broadcasts so reconnect can cancel them
_pending_leave: dict[tuple[str, int], asyncio.Task] = {}


async def _authenticate_ws_user(websocket: WebSocket) -> tuple[int, str] | None:
    """Authenticate websocket user via access_token cookie.

    Returns:
        tuple of (user_id, user_name) if authenticated, None otherwise
    """
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4008)
        return None
    s = Serializer(settings.chat_secret_key)
    try:
        token_data = s.loads(token, max_age=settings.token_max_age)
        user_id = token_data.get("user_id")
    except (BadSignature, SignatureExpired):
        await websocket.close(code=4008)
        return None

    if user_id is None:
        await websocket.close(code=4008)
        return None

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()
        if user is None:
            await websocket.close(code=4008)
            return None
        user_name = user.name

    return user_id, user_name


async def _broadcast_user_online(
    channel_id: str, user_id: int, user_name: str, websocket: WebSocket
):
    """Broadcast user_online event to channel except the sender."""
    await manager.broadcast_to_channel_except(
        dumps(
            {
                "type": "user_online",
                "user_id": user_id,
                "user_name": escape(user_name),
            }
        ),
        channel_id,
        websocket,
    )


async def _send_existing_users(channel_id: str, websocket: WebSocket):
    """Send list of existing online users to newly connected websocket."""
    for other_uid in manager.get_other_user_ids_in_channel(channel_id, websocket):
        await websocket.send_text(
            dumps(
                {
                    "type": "user_online",
                    "user_id": other_uid,
                    "user_name": "",
                }
            )
        )


async def _handle_typing(
    channel_id: str, user_id: int, user_name: str, is_typing: bool, websocket: WebSocket
):
    """Broadcast typing indicator to channel except the sender."""
    await manager.broadcast_to_channel_except(
        dumps(
            {
                "type": "typing",
                "user_id": user_id,
                "user_name": escape(user_name),
                "typing": is_typing,
            }
        ),
        channel_id,
        websocket,
    )


async def _delayed_leave_broadcast(
    channel_id: str, user_id: int, user_name: str, leave_key: tuple[str, int]
):
    """Broadcast leave messages after delay if user didn't reconnect."""
    await asyncio.sleep(5)
    if leave_key in _pending_leave:
        _pending_leave.pop(leave_key, None)
        await manager.broadcast(
            dumps(
                {
                    "type": "system",
                    "content": f"{escape(user_name)} left the chat",
                    "user_id": user_id,
                    "user_name": escape(user_name),
                }
            ),
            channel_id,
        )
        await manager.broadcast(
            dumps(
                {
                    "type": "user_offline",
                    "user_id": user_id,
                    "user_name": escape(user_name),
                }
            ),
            channel_id,
        )


@ws_router.websocket("/ws/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    """
    Handle incoming websocket connections.

    Accepts the websocket connection and broadcasts received messages
    to other clients in the channel. Saves messages to the database.
    Supports typing indicators and presence events.

    Args:
        websocket (WebSocket): The websocket connection
        channel_id (str): The ID of the chat channel

    Raises:
        WebSocketDisconnect: If the connection is closed
    """
    # Verify authentication via access_token cookie
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4008)
        return
    s = Serializer(settings.chat_secret_key)
    try:
        token_data = s.loads(token, max_age=settings.token_max_age)
        user_id = token_data.get("user_id")
    except (BadSignature, SignatureExpired):
        await websocket.close(code=4008)
        return

    if user_id is None:
        await websocket.close(code=4008)
        return

    # Look up username from database
    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()
        if user is None:
            await websocket.close(code=4008)
            return
        user_name = user.name

    # Cancel any pending "left the chat" broadcast from a previous disconnect
    leave_key = (channel_id, user_id)
    old_task = _pending_leave.pop(leave_key, None)
    if old_task:
        old_task.cancel()

    await manager.connect(websocket, channel_id, user_id)

    await manager.broadcast_to_channel_except(
        dumps(
            {
                "type": "user_online",
                "user_id": user_id,
                "user_name": escape(user_name),
            }
        ),
        channel_id,
        websocket,
    )

    # Send the new user info about all others already online in this channel
    for other_uid in manager.get_other_user_ids_in_channel(channel_id, websocket):
        await websocket.send_text(
            dumps(
                {
                    "type": "user_online",
                    "user_id": other_uid,
                    "user_name": "",
                }
            )
        )

    try:
        while True:
            data = await websocket.receive_text()
            message_data = loads(data)
            msg_type = message_data.get("type", "message")

            if msg_type == "typing":
                await manager.broadcast_to_channel_except(
                    dumps(
                        {
                            "type": "typing",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                            "typing": message_data.get("typing", False),
                        }
                    ),
                    channel_id,
                    websocket,
                )

            elif msg_type == "message":
                message = message_data["message"]

                async with async_session_scope() as db:
                    result_channel = await db.execute(
                        select(Channel).filter(Channel.channel_id == channel_id)
                    )
                    channel = result_channel.scalar()
                    if not channel or user_id not in (
                        channel.user1_id,
                        channel.user2_id,
                    ):
                        continue

                    new_message = Message(
                        content=message,
                        channel_id=channel_id,
                        created_at=datetime.now(),
                        user_id=user_id,
                    )
                    db.add(new_message)
                    await db.flush()

                    message_object = {
                        "type": "message",
                        "message_id": new_message.id,
                        "userId": user_id,
                        "senderName": escape(user_name),
                        "content": escape(message),
                    }

                await manager.broadcast(dumps(message_object), channel_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id, user_id)

        async def delayed_leave():
            """Wait then broadcast leave only if user didn't reconnect."""
            await asyncio.sleep(5)
            if leave_key in _pending_leave:
                _pending_leave.pop(leave_key, None)
                await manager.broadcast(
                    dumps(
                        {
                            "type": "system",
                            "content": f"{escape(user_name)} left the chat",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                        }
                    ),
                    channel_id,
                )
                await manager.broadcast(
                    dumps(
                        {
                            "type": "user_offline",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                        }
                    ),
                    channel_id,
                )

        task = asyncio.create_task(delayed_leave())
        _pending_leave[leave_key] = task


@ws_router.websocket("/ws/group/{group_id}")
async def websocket_group_endpoint(websocket: WebSocket, group_id: int):
    """
    Handle incoming websocket connections for group chat.

    Accepts the websocket connection and broadcasts received messages
    to other clients in the group. Saves messages to the database.
    Supports typing indicators and presence events.

    Args:
        websocket (WebSocket): The websocket connection
        group_id (int): The ID of the group chat

    Raises:
        WebSocketDisconnect: If the connection is closed
    """
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4008)
        return
    s = Serializer(settings.chat_secret_key)
    try:
        token_data = s.loads(token, max_age=settings.token_max_age)
        user_id = token_data.get("user_id")
    except (BadSignature, SignatureExpired):
        await websocket.close(code=4008)
        return

    if user_id is None:
        await websocket.close(code=4008)
        return

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()
        if user is None:
            await websocket.close(code=4008)
            return
        user_name = user.name

        # Check group membership
        result_member = await db.execute(
            select(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        if not result_member.scalar():
            await websocket.close(code=4003)
            return

    channel_id = f"group_{group_id}"

    leave_key = (channel_id, user_id)
    old_task = _pending_leave.pop(leave_key, None)
    if old_task:
        old_task.cancel()

    await manager.connect(websocket, channel_id, user_id)

    await manager.broadcast_to_channel_except(
        dumps(
            {
                "type": "user_online",
                "user_id": user_id,
                "user_name": escape(user_name),
            }
        ),
        channel_id,
        websocket,
    )

    for other_uid in manager.get_other_user_ids_in_channel(channel_id, websocket):
        await websocket.send_text(
            dumps(
                {
                    "type": "user_online",
                    "user_id": other_uid,
                    "user_name": "",
                }
            )
        )

    try:
        while True:
            data = await websocket.receive_text()
            message_data = loads(data)
            msg_type = message_data.get("type", "message")

            if msg_type == "typing":
                await manager.broadcast_to_channel_except(
                    dumps(
                        {
                            "type": "typing",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                            "typing": message_data.get("typing", False),
                        }
                    ),
                    channel_id,
                    websocket,
                )

            elif msg_type == "message":
                message = message_data["message"]

                async with async_session_scope() as db:
                    new_message = GroupMessage(
                        content=message,
                        group_id=group_id,
                        created_at=datetime.now(),
                        user_id=user_id,
                    )
                    db.add(new_message)
                    await db.flush()

                    message_object = {
                        "type": "message",
                        "message_id": new_message.id,
                        "userId": user_id,
                        "senderName": escape(user_name),
                        "content": escape(message),
                    }

                await manager.broadcast(dumps(message_object), channel_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id, user_id)

        async def delayed_leave():
            await asyncio.sleep(5)
            if leave_key in _pending_leave:
                _pending_leave.pop(leave_key, None)
                await manager.broadcast(
                    dumps(
                        {
                            "type": "system",
                            "content": f"{escape(user_name)} left the chat",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                        }
                    ),
                    channel_id,
                )
                await manager.broadcast(
                    dumps(
                        {
                            "type": "user_offline",
                            "user_id": user_id,
                            "user_name": escape(user_name),
                        }
                    ),
                    channel_id,
                )

        task = asyncio.create_task(delayed_leave())
        _pending_leave[leave_key] = task

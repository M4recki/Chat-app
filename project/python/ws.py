import asyncio
from datetime import datetime
from html import escape
from json import dumps, loads

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from .connection_manager import manager
from .database import async_session_scope
from .models import Channel, GroupMember, GroupMessage, Message, User
from .routes.helpers import decode_access_token

ws_router = APIRouter()

_pending_leave: dict[tuple[str, int], asyncio.Task] = {}


async def handle_ws_connection(
    websocket: WebSocket,
    channel_id: str,
    is_group: bool = False,
    group_id: int | None = None,
):
    """Handle a WebSocket connection for chat.

    Authenticates the user, manages online presence, and processes
    incoming messages (typing indicators and chat messages).

    Args:
        websocket: The WebSocket connection
        channel_id: The channel identifier
        is_group: Whether this is a group chat
        group_id: The group ID (for group chats)
    """
    raw_user_id = decode_access_token(websocket.cookies)
    if raw_user_id is None:
        await websocket.close(code=4008)
        return
    user_id: int = raw_user_id

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar()
        if user is None:
            await websocket.close(code=4008)
            return
        user_name = user.name

        if is_group:
            assert group_id is not None
            result_member = await db.execute(
                select(GroupMember).filter(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
            if not result_member.scalar():
                await websocket.close(code=4003)
                return

        user.last_active = datetime.now()

    leave_key = (channel_id, user_id)
    old_task = _pending_leave.pop(leave_key, None)
    if old_task:
        old_task.cancel()

    await manager.connect(websocket, channel_id, user_id)

    await manager.broadcast_to_channel_except(
        dumps(
            {"type": "user_online", "user_id": user_id, "user_name": escape(user_name)}
        ),
        channel_id,
        websocket,
    )

    for other_uid in manager.get_other_user_ids_in_channel(channel_id, websocket):
        await websocket.send_text(
            dumps({"type": "user_online", "user_id": other_uid, "user_name": ""})
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
                    if is_group:
                        assert group_id is not None
                        new_message = GroupMessage(
                            content=message,
                            group_id=group_id,
                            created_at=datetime.now(),
                            user_id=user_id,
                        )
                    else:
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


@ws_router.websocket("/ws/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    await handle_ws_connection(websocket, channel_id)


@ws_router.websocket("/ws/group/{group_id}")
async def websocket_group_endpoint(websocket: WebSocket, group_id: int):
    await handle_ws_connection(
        websocket, f"group_{group_id}", is_group=True, group_id=group_id
    )

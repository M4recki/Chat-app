from datetime import datetime
from typing import cast

import pytest
from conftest import (
    NONEXISTENT_ID,
    async_session_scope,
    create_channel,
    create_user,
    make_request,
    make_request_with_cookie,
)
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer as Serializer
from sqlalchemy.ext.asyncio import AsyncSession

from project.python.database import get_async_db
from project.python.models import (
    Channel,
    Friend as FriendModel,
    FriendStatus,
    Message,
    User,
)
from project.python.routes.helpers import (
    authentication_in_header,
    get_channel_id_map,
    get_channel_or_404,
    get_current_user_id,
    get_friend_status_map,
    get_message_or_404,
    get_or_create_channel,
    get_paginated_messages,
    get_user,
    get_user_by_id,
    get_user_from_request,
    is_authenticated,
    message_to_json,
    require_channel_participant,
)
from project.python.routes.template import (
    encode_avatar,
    user_image,
    user_name,
)
from project.python.settings import settings as app_settings
from tests.model_test import TestingSessionLocal


@pytest.mark.asyncio
async def test_get_user_by_id_found():
    db_sync = TestingSessionLocal()
    user = create_user(
        db_sync,
        "Helper",
        "One",
        "helper1@example.com",
    )
    db_sync.close()

    async with async_session_scope() as db:
        result = await get_user_by_id(db, user.id)
    assert result is not None
    assert result.id == user.id
    assert result.name == "Helper"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found():

    async with async_session_scope() as db:
        result = await get_user_by_id(db, NONEXISTENT_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_message_or_404_found():
    db_sync = TestingSessionLocal()
    user = create_user(
        db_sync,
        "Msg",
        "User",
        "msg-user@example.com",
    )
    msg = Message(
        content="test", channel_id="ch", created_at=datetime.now(), user_id=user.id
    )
    db_sync.add(msg)
    db_sync.commit()
    msg_id = msg.id
    db_sync.close()

    async with async_session_scope() as db:
        result = await get_message_or_404(db, msg_id)
    assert result.id == msg_id


@pytest.mark.asyncio
async def test_get_message_or_404_not_found():
    async with async_session_scope() as db:
        with pytest.raises(HTTPException) as exc:
            await get_message_or_404(db, NONEXISTENT_ID)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_friend_status_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync,
        "FSM",
        "One",
        "fsm1@example.com",
    )
    u2 = create_user(
        db_sync,
        "FSM",
        "Two",
        "fsm2@example.com",
    )
    rel = FriendModel(
        user1_id=u1.id,
        user2_id=u2.id,
        status=FriendStatus.ACCEPTED,
        last_sent=datetime.now(),
    )
    db_sync.add(rel)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        smap = await get_friend_status_map(db, u1.id, [cast(int, u2.id)])
    assert smap[cast(int, u2.id)] == FriendStatus.ACCEPTED


@pytest.mark.asyncio
async def test_get_channel_id_map():
    db_sync = TestingSessionLocal()
    u1 = create_user(
        db_sync,
        "CIM",
        "One",
        "cim1@example.com",
    )
    u2 = create_user(
        db_sync,
        "CIM",
        "Two",
        "cim2@example.com",
    )

    ch = Channel(channel_id="test-ch", user1_id=u1.id, user2_id=u2.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        cmap = await get_channel_id_map(db, u1.id, [cast(int, u2.id)])
    assert cmap[cast(int, u2.id)] == "test-ch"


@pytest.mark.asyncio
async def test_is_authenticated_expired_token(monkeypatch):
    s = Serializer(app_settings.chat_secret_key)
    token = s.dumps({"user_id": NONEXISTENT_ID})
    monkeypatch.setattr(app_settings, "token_max_age", -1)
    request = make_request_with_cookie(token)

    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_is_authenticated_bad_signature():
    request = make_request_with_cookie("not-a-valid-token")
    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_is_authenticated_user_not_found():
    s = Serializer(app_settings.chat_secret_key)
    token = s.dumps({"user_id": NONEXISTENT_ID})
    request = make_request_with_cookie(token)
    with pytest.raises(HTTPException) as exc_info:
        await is_authenticated(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User not found"


def test_authentication_in_header_valid():
    serializer = Serializer(app_settings.chat_secret_key)
    token = serializer.dumps({"user_id": 1})
    result = authentication_in_header(make_request_with_cookie(token))
    assert result == {"is_authenticated": True}


def test_authentication_in_header_no_token():
    result = authentication_in_header(make_request())
    assert result == {"is_authenticated": False}


def test_authentication_in_header_invalid_token():
    result = authentication_in_header(make_request_with_cookie("forged"))
    assert result == {"is_authenticated": False}


@pytest.mark.parametrize(
    "func,expected",
    [
        (authentication_in_header, {"is_authenticated": False}),
        (user_image, {"user_image": ""}),
        (user_name, {"user_name": None}),
    ],
)
def test_not_request(func, expected):
    assert func("not-a-request") == expected


@pytest.mark.asyncio
async def test_get_user_from_request_no_token():
    request = make_request()
    user, user_id = await get_user_from_request(request)
    assert user is None
    assert user_id is None


@pytest.mark.asyncio
async def test_get_user_from_request_invalid_token():
    user, user_id = await get_user_from_request(make_request_with_cookie("bad"))
    assert user is None
    assert user_id is None


def test_get_user_not_found():
    user = get_user(NONEXISTENT_ID)
    assert user is None


def test_encode_avatar_empty():
    user = cast(User, type("FakeUser", (), {"avatar": None})())
    assert encode_avatar(user) == ""


def test_encode_avatar_with_avatar():
    user = cast(User, type("FakeUserWithAvatar", (), {"avatar": b"fake-binary-data"})())
    result = encode_avatar(user)
    assert isinstance(result, str)
    assert len(result) > 0


def test_encode_avatar_no_user():
    assert encode_avatar(None) == ""


def test_user_image_no_token():
    assert user_image(make_request()) == {"user_image": ""}


def test_user_image_invalid_token():
    assert user_image(make_request_with_cookie("bad")) == {"user_image": ""}


def test_user_name_no_token():
    assert user_name(make_request()) == {"user_name": None}


def test_user_name_invalid_token():
    assert user_name(make_request_with_cookie("bad")) == {"user_name": None}


def test_get_current_user_id_valid():
    serializer = Serializer(app_settings.chat_secret_key)
    token = serializer.dumps({"user_id": 42})
    request = make_request_with_cookie(token)
    assert get_current_user_id(request) == 42


def test_get_current_user_id_invalid():
    assert get_current_user_id(make_request()) is None


def test_get_user_found():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "Found", "User", "found@example.com")
    db_sync.close()
    result = get_user(user.id)
    assert result is not None
    assert result.name == "Found"


@pytest.mark.asyncio
async def test_get_or_create_channel_creates_new():
    db_sync = TestingSessionLocal()
    u1 = create_user(db_sync, "New", "Channel", "newch@example.com")
    u2 = create_user(db_sync, "Other", "Side", "other@example.com")
    db_sync.close()
    async with async_session_scope() as db:
        ch = await get_or_create_channel(db, u1.id, u2.id)
    assert ch is not None
    assert ch.user1_id == u1.id
    assert ch.user2_id == u2.id


@pytest.mark.asyncio
async def test_get_or_create_channel_returns_existing():
    db_sync = TestingSessionLocal()
    u1 = create_user(db_sync, "Existing", "Ch", "existch@example.com")
    u2 = create_user(db_sync, "Existing", "Other", "existother@example.com")
    ch = create_channel(db_sync, u1, u2)
    existing_id = ch.channel_id
    db_sync.close()
    async with async_session_scope() as db:
        result = await get_or_create_channel(db, u1.id, u2.id)
    assert result.channel_id == existing_id


@pytest.mark.asyncio
async def test_get_async_db_yields_session():
    gen = get_async_db()
    db = await gen.__anext__()
    assert isinstance(db, AsyncSession)
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


def test_message_to_json_basic():
    msg = Message(
        id=1,
        user_id=10,
        channel_id="ch-1",
        content="hello",
        created_at=datetime(2026, 1, 1, 12, 0),
    )
    result = message_to_json(msg, "John Doe")
    assert result["id"] == 1
    assert result["user_id"] == 10
    assert result["sender_name"] == "John Doe"
    assert result["content"] == "hello"
    assert result["created_at"] == "12:00, 2026-01-01"
    assert result["edited_at"] is None


def test_message_to_json_with_edited_at():
    msg = Message(
        id=2,
        user_id=20,
        channel_id="ch-2",
        content="edited",
        created_at=datetime(2026, 6, 15, 8, 30),
        edited_at=datetime(2026, 6, 15, 9, 0),
    )
    result = message_to_json(msg, "Jane Smith")
    assert result["edited_at"] == "09:00, 2026-06-15"
    assert result["content"] == "edited"


@pytest.mark.asyncio
async def test_get_paginated_messages_basic():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "Pag", "User", "pag-user@example.com")
    friend = create_user(db_sync, "Pag", "Friend", "pag-friend@example.com")
    ch = Channel(channel_id="pag-ch-1", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    for i in range(5):
        msg = Message(
            content=f"msg {i}",
            channel_id="pag-ch-1",
            user_id=user.id,
            created_at=datetime(2026, 1, 1, 12, i),
        )
        db_sync.add(msg)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        total, messages, users_map = await get_paginated_messages(
            db, Message, Message.channel_id, "pag-ch-1"
        )
    assert total == 5
    assert len(messages) == 5
    assert messages[0].content == "msg 0"
    assert user.id in users_map


@pytest.mark.asyncio
async def test_get_paginated_messages_empty():
    async with async_session_scope() as db:
        total, messages, users_map = await get_paginated_messages(
            db, Message, Message.channel_id, "nonexistent-ch"
        )
    assert total == 0
    assert messages == []
    assert users_map == {}


@pytest.mark.asyncio
async def test_get_channel_or_404_found():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CH", "Found", "ch-found@example.com")
    friend = create_user(db_sync, "CH", "Other", "ch-other@example.com")
    ch = Channel(channel_id="ch-test-1", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        result = await get_channel_or_404(db, "ch-test-1")
    assert result.channel_id == "ch-test-1"


@pytest.mark.asyncio
async def test_get_channel_or_404_not_found():
    async with async_session_scope() as db:
        with pytest.raises(HTTPException) as exc_info:
            await get_channel_or_404(db, "nonexistent-ch")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_require_channel_participant_ok():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CP", "Ok", "cp-ok@example.com")
    friend = create_user(db_sync, "CP", "Friend", "cp-friend@example.com")
    ch = Channel(channel_id="cp-ch-1", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        await require_channel_participant(db, "cp-ch-1", user.id)


@pytest.mark.asyncio
async def test_require_channel_participant_not_member():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CP", "Not", "cp-not@example.com")
    friend = create_user(db_sync, "CP", "Friend2", "cp-friend2@example.com")
    outsider = create_user(db_sync, "CP", "Out", "cp-out@example.com")
    ch = Channel(channel_id="cp-ch-2", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        with pytest.raises(HTTPException) as exc_info:
            await require_channel_participant(db, "cp-ch-2", outsider.id)
    assert exc_info.value.status_code == 403

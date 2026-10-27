from datetime import datetime

import pytest
from conftest import (
    async_session_scope,
    create_group,
    create_group_member,
    create_user,
)

from project.python.models import (
    Channel,
    GroupMessage,
    Message,
    UserChannelRead,
    UserGroupRead,
)
from project.python.routes.helpers import (
    compute_channel_unread_counts,
    compute_group_unread_counts,
    mark_channel_read,
    mark_group_read,
)
from tests.model_test import TestingSessionLocal


@pytest.mark.asyncio
async def test_mark_channel_read_creates():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "MCR", "Create", "mcr-create@example.com")
    friend = create_user(db_sync, "MCR", "Friend", "mcr-friend@example.com")
    ch = Channel(channel_id="mcr-ch-1", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    msg = Message(
        content="latest",
        channel_id="mcr-ch-1",
        user_id=friend.id,
        created_at=datetime.now(),
    )
    db_sync.add(msg)
    db_sync.commit()
    msg_id = msg.id
    db_sync.close()

    async with async_session_scope() as db:
        await mark_channel_read(db, user.id, "mcr-ch-1")

    db_check = TestingSessionLocal()
    ucr = (
        db_check.query(UserChannelRead)
        .filter(
            UserChannelRead.user_id == user.id,
            UserChannelRead.channel_id == "mcr-ch-1",
        )
        .first()
    )
    assert ucr is not None
    assert ucr.last_read_message_id == msg_id
    db_check.close()


@pytest.mark.asyncio
async def test_mark_channel_read_updates():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "MCR", "Update", "mcr-update@example.com")
    friend = create_user(db_sync, "MCR", "Friend2", "mcr-friend2@example.com")
    ch = Channel(channel_id="mcr-ch-2", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    msg1 = Message(
        content="old",
        channel_id="mcr-ch-2",
        user_id=friend.id,
        created_at=datetime.now(),
    )
    db_sync.add(msg1)
    db_sync.commit()

    async with async_session_scope() as db:
        await mark_channel_read(db, user.id, "mcr-ch-2")

    msg2 = Message(
        content="new",
        channel_id="mcr-ch-2",
        user_id=friend.id,
        created_at=datetime.now(),
    )
    db_sync.add(msg2)
    db_sync.commit()
    msg2_id = msg2.id
    db_sync.close()

    async with async_session_scope() as db:
        await mark_channel_read(db, user.id, "mcr-ch-2")

    db_check = TestingSessionLocal()
    ucr = (
        db_check.query(UserChannelRead)
        .filter(
            UserChannelRead.user_id == user.id,
            UserChannelRead.channel_id == "mcr-ch-2",
        )
        .first()
    )
    assert ucr.last_read_message_id == msg2_id
    db_check.close()


@pytest.mark.asyncio
async def test_mark_channel_read_empty_channel():
    async with async_session_scope() as db:
        await mark_channel_read(db, 99999, "empty-ch")
    assert True


@pytest.mark.asyncio
async def test_mark_group_read_creates():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "MGR", "Create", "mgr-create@example.com")
    group = create_group(db_sync, "MGR Group", user)
    create_group_member(db_sync, group.id, user)
    gmsg = GroupMessage(
        content="latest",
        group_id=group.id,
        user_id=user.id,
        created_at=datetime.now(),
    )
    db_sync.add(gmsg)
    db_sync.commit()
    gmsg_id = gmsg.id
    db_sync.close()

    async with async_session_scope() as db:
        await mark_group_read(db, user.id, group.id)

    db_check = TestingSessionLocal()
    ugr = (
        db_check.query(UserGroupRead)
        .filter(
            UserGroupRead.user_id == user.id,
            UserGroupRead.group_id == group.id,
        )
        .first()
    )
    assert ugr is not None
    assert ugr.last_read_message_id == gmsg_id
    db_check.close()


@pytest.mark.asyncio
async def test_mark_group_read_updates():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "MGR", "Update", "mgr-update@example.com")
    group = create_group(db_sync, "MGR Group 2", user)
    create_group_member(db_sync, group.id, user)
    gmsg1 = GroupMessage(
        content="old", group_id=group.id, user_id=user.id, created_at=datetime.now()
    )
    db_sync.add(gmsg1)
    db_sync.commit()

    async with async_session_scope() as db:
        await mark_group_read(db, user.id, group.id)

    gmsg2 = GroupMessage(
        content="new", group_id=group.id, user_id=user.id, created_at=datetime.now()
    )
    db_sync.add(gmsg2)
    db_sync.commit()
    gmsg2_id = gmsg2.id
    db_sync.close()

    async with async_session_scope() as db:
        await mark_group_read(db, user.id, group.id)

    db_check = TestingSessionLocal()
    ugr = (
        db_check.query(UserGroupRead)
        .filter(
            UserGroupRead.user_id == user.id,
            UserGroupRead.group_id == group.id,
        )
        .first()
    )
    assert ugr.last_read_message_id == gmsg2_id
    db_check.close()


@pytest.mark.asyncio
async def test_mark_group_read_empty_group():
    async with async_session_scope() as db:
        await mark_group_read(db, 99999, 99999)
    assert True


@pytest.mark.asyncio
async def test_compute_channel_unread_counts_basic():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CCU", "Basic", "ccu-basic@example.com")
    friend = create_user(db_sync, "CCU", "Friend", "ccu-friend@example.com")
    ch = Channel(channel_id="ccu-ch-1", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    for i in range(3):
        msg = Message(
            content=f"m{i}",
            channel_id="ccu-ch-1",
            user_id=friend.id,
            created_at=datetime.now(),
        )
        db_sync.add(msg)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        counts = await compute_channel_unread_counts(db, user.id, ["ccu-ch-1"])
    assert counts["ccu-ch-1"] == 3


@pytest.mark.asyncio
async def test_compute_channel_unread_counts_all_read():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CCU", "Read", "ccu-read@example.com")
    friend = create_user(db_sync, "CCU", "Friend2", "ccu-friend2@example.com")
    ch = Channel(channel_id="ccu-ch-2", user1_id=user.id, user2_id=friend.id)
    db_sync.add(ch)
    db_sync.commit()
    msg = Message(
        content="m0",
        channel_id="ccu-ch-2",
        user_id=friend.id,
        created_at=datetime.now(),
    )
    db_sync.add(msg)
    db_sync.commit()
    db_sync.close()

    async with async_session_scope() as db:
        await mark_channel_read(db, user.id, "ccu-ch-2")

    async with async_session_scope() as db:
        counts = await compute_channel_unread_counts(db, user.id, ["ccu-ch-2"])
    assert counts["ccu-ch-2"] == 0


@pytest.mark.asyncio
async def test_compute_channel_unread_counts_empty():
    async with async_session_scope() as db:
        counts = await compute_channel_unread_counts(db, 99999, [])
    assert counts == {}


@pytest.mark.asyncio
async def test_compute_group_unread_counts_basic():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CGU", "Basic", "cgu-basic@example.com")
    other = create_user(db_sync, "CGU", "Other", "cgu-other@example.com")
    group = create_group(db_sync, "CGU Group", user)
    create_group_member(db_sync, group.id, user)
    create_group_member(db_sync, group.id, other)
    for i in range(4):
        gmsg = GroupMessage(
            content=f"g{i}",
            group_id=group.id,
            user_id=other.id,
            created_at=datetime.now(),
        )
        db_sync.add(gmsg)
    db_sync.commit()
    group_id = group.id
    db_sync.close()

    async with async_session_scope() as db:
        counts = await compute_group_unread_counts(db, user.id, [group_id])
    assert counts[group_id] == 4


@pytest.mark.asyncio
async def test_compute_group_unread_counts_all_read():
    db_sync = TestingSessionLocal()
    user = create_user(db_sync, "CGU", "Read", "cgu-read@example.com")
    other = create_user(db_sync, "CGU", "Other2", "cgu-other2@example.com")
    group = create_group(db_sync, "CGU Group 2", user)
    create_group_member(db_sync, group.id, user)
    create_group_member(db_sync, group.id, other)
    gmsg = GroupMessage(
        content="g0", group_id=group.id, user_id=other.id, created_at=datetime.now()
    )
    db_sync.add(gmsg)
    db_sync.commit()
    group_id = group.id
    db_sync.close()

    async with async_session_scope() as db:
        await mark_group_read(db, user.id, group_id)

    async with async_session_scope() as db:
        counts = await compute_group_unread_counts(db, user.id, [group_id])
    assert counts[group_id] == 0


@pytest.mark.asyncio
async def test_compute_group_unread_counts_empty():
    async with async_session_scope() as db:
        counts = await compute_group_unread_counts(db, 99999, [])
    assert counts == {}

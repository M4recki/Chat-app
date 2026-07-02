from uuid import uuid4

from conftest import (
    authed_client,
    create_channel,
    create_friendship,
    create_message,
    create_user,
    create_group,
    create_group_member,
    create_group_message,
    NONEXISTENT_ID,
)
from project.python.models import (
    Channel,
    FriendStatus,
    Message,
)
from project.python.routes.helpers import generate_csrf_token
from tests.model_test import TestingSessionLocal


def test_single_chat_returns_200():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Single",
        "Chat",
        "single-chat@example.com",
    )
    friend = create_user(
        db,
        "Friend",
        "One",
        "friend-one@example.com",
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_channel(db, user, friend)

    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


def test_single_chat_no_friends():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Single",
        "Alone",
        "single-alone@example.com",
    )

    local_client = authed_client(user)
    response = local_client.get("/single_chat")
    assert response.status_code == 200


def test_single_chat_creates_channel():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "SC",
        "Create",
        "sc-create@example.com",
    )
    friend = create_user(
        db,
        "SC",
        "Friend",
        "sc-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.get("/single_chat")

    assert response.status_code == 200


def test_single_chat_accepts_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "SCA",
        "User",
        "sca-user@example.com",
    )
    friend = create_user(
        db,
        "SCA",
        "Friend",
        "sca-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_friendship(db, friend, user, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.get("/single_chat")

    assert response.status_code == 200


def test_friend_chat_page_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FC",
        "User",
        "fc-user@example.com",
    )
    friend = create_user(
        db,
        "FC",
        "Friend",
        "fc-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/nonexistent/{friend.id}")

    assert response.status_code == 404


def test_friend_chat_page_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FC2",
        "User",
        "fc2-user@example.com",
    )
    friend = create_user(
        db,
        "FC2",
        "Friend",
        "fc2-friend@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    db.commit()
    create_message(db, "hi", ch_id, user)
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/{ch_id}/{friend.id}")

    assert response.status_code == 200


def test_friend_chat_page_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "FNF",
        "User",
        "fnf-user@example.com",
    )
    db.close()
    local_client = authed_client(user)
    response = local_client.get(f"/friend_chat/some-ch/{NONEXISTENT_ID}")

    assert response.status_code == 404


def test_edit_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Edit",
        "User",
        "edit-user@example.com",
    )
    friend = create_user(
        db,
        "Edit",
        "Friend",
        "edit-friend@example.com",
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "original", ch_id, user)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "updated", "csrf_token": csrf},
    )

    assert response.status_code == 200

    db2 = TestingSessionLocal()
    updated = db2.query(Message).filter(Message.id == msg.id).first()

    assert updated is not None
    assert updated.content == "updated"
    assert updated.edited_at is not None
    db2.close()


def test_edit_message_not_owner():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Edit2",
        "User",
        "edit2-user@example.com",
    )
    other = create_user(
        db,
        "Edit2",
        "Other",
        "edit2-other@example.com",
    )
    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=other.id)
    db.add(channel)
    msg = create_message(db, "mine", ch_id, other)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "hacked", "csrf_token": csrf},
    )

    assert response.status_code == 403


def test_edit_message_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "ENF",
        "User",
        "enf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{NONEXISTENT_ID}",
        data={"content": "test", "csrf_token": csrf},
    )

    assert response.status_code == 404


def test_delete_message_success():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Del",
        "User",
        "del-user@example.com",
    )
    friend = create_user(
        db,
        "Del",
        "Friend",
        "del-friend@example.com",
    )

    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "delete me", ch_id, user)
    msg_id = msg.id

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_message/{msg_id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 200

    db2 = TestingSessionLocal()
    deleted = db2.query(Message).filter(Message.id == msg_id).first()

    assert deleted is None
    db2.close()


def test_delete_message_not_owner():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Del2",
        "User",
        "del2-user@example.com",
    )
    other = create_user(
        db,
        "Del2",
        "Other",
        "del2-other@example.com",
    )

    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=other.id)
    db.add(channel)
    msg = create_message(db, "not mine", ch_id, other)

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_message/{msg.id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 403


def test_delete_message_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "DNF",
        "User",
        "dnf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/delete_message/{NONEXISTENT_ID}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 404


def test_edit_message_empty_content():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "EMC",
        "User",
        "emc-user@example.com",
    )
    friend = create_user(
        db,
        "EMC",
        "Friend",
        "emc-friend@example.com",
    )

    ch_id = str(uuid4())
    channel = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(channel)
    msg = create_message(db, "hello", ch_id, user)
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/edit_message/{msg.id}",
        data={"content": "   ", "csrf_token": csrf},
    )

    assert response.status_code == 400


def test_api_chat_messages_basic():
    db = TestingSessionLocal()
    user = create_user(db, "API", "User", "api-user@example.com")
    friend = create_user(db, "API", "Friend", "api-friend@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    create_message(db, "hello", ch_id, user)
    create_message(db, "hi there", ch_id, friend)
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "has_more" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "hello"
    assert data["messages"][1]["content"] == "hi there"


def test_api_chat_messages_empty():
    db = TestingSessionLocal()
    user = create_user(db, "API", "Empty", "api-empty@example.com")
    friend = create_user(db, "API", "Friend2", "api-friend2@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_api_chat_messages_not_participant():
    db = TestingSessionLocal()
    user = create_user(db, "API", "NP", "api-np@example.com")
    friend = create_user(db, "API", "Friend3", "api-friend3@example.com")
    outsider = create_user(db, "API", "Outsider", "api-outsider@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    local_client = authed_client(outsider)
    response = local_client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 403


def test_api_chat_messages_no_auth():
    from conftest import client as _client

    _client.cookies.clear()

    db = TestingSessionLocal()
    user = create_user(db, "API", "NoAuth", "api-noauth@example.com")
    friend = create_user(db, "API", "Friend4", "api-friend4@example.com")

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    ch_id = str(uuid4())
    ch = Channel(channel_id=ch_id, user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    response = _client.get(f"/api/chat_messages/{ch_id}")

    assert response.status_code == 401


def test_api_group_messages_basic():
    db = TestingSessionLocal()
    user = create_user(db, "API", "Group", "api-group@example.com")
    member = create_user(db, "API", "GMember", "api-gmember@example.com")

    group = create_group(db, "API Group", user)
    create_group_member(db, group.id, user)
    create_group_member(db, group.id, member)
    create_group_message(db, group.id, user, "group msg 1")
    create_group_message(db, group.id, member, "group msg 2")
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "has_more" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "group msg 1"
    assert data["messages"][1]["content"] == "group msg 2"


def test_api_group_messages_empty():
    db = TestingSessionLocal()
    user = create_user(db, "API", "GEmpty", "api-gempty@example.com")

    group = create_group(db, "API Group Empty", user)
    create_group_member(db, group.id, user)
    db.close()

    local_client = authed_client(user)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_api_group_messages_not_member():
    db = TestingSessionLocal()
    user = create_user(db, "API", "GNM", "api-gnm@example.com")
    outsider = create_user(db, "API", "GOut", "api-gout@example.com")

    group = create_group(db, "API Group NM", user)
    create_group_member(db, group.id, user)
    db.close()

    local_client = authed_client(outsider)
    response = local_client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 403


def test_api_group_messages_no_auth():
    from conftest import client as _client

    _client.cookies.clear()

    db = TestingSessionLocal()
    user = create_user(db, "API", "GNoAuth", "api-gnoauth@example.com")

    group = create_group(db, "API Group NoAuth", user)
    create_group_member(db, group.id, user)
    db.close()

    response = _client.get(f"/api/group_messages/{group.id}")

    assert response.status_code == 401

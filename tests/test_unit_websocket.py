import json
from datetime import datetime
from io import BytesIO

import pytest
from conftest import (
    DEFAULT_AVATAR,
    NONEXISTENT_ID,
    client,
)
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer as Serializer
from PIL import Image
from starlette.testclient import TestClient as WSClient

from project.python.main import app, app as ws_app
from project.python.models import Channel, GroupChat, GroupMember, User
from project.python.settings import settings as app_settings
from tests.model_test import TestingSessionLocal


def create_test_user(db, name="TestUser", email_suffix=""):
    user = User(
        name=name,
        surname="User",
        email=f"ws-test{email_suffix}@example.com",
        password="hash",
        avatar=b"fake",
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    return user


def test_websocket_send_and_receive():
    db = TestingSessionLocal()
    user = create_test_user(db)
    friend = create_test_user(db, name="Friend", email_suffix="-friend")
    ch = Channel(channel_id="test-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/test-ch") as ws:
        ws.send_json(
            {
                "type": "message",
                "message": "Hello!",
            }
        )
        data = ws.receive_text()

        assert '"Hello!"' in data
        assert '"TestUser"' in data


def test_websocket_message_has_type_field():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-2")
    friend = create_test_user(db, name="Friend", email_suffix="-friend2")
    ch = Channel(channel_id="type-ch", user1_id=user.id, user2_id=friend.id)

    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/type-ch") as ws:
        ws.send_json(
            {
                "type": "message",
                "message": "Hi",
            }
        )

        data = json.loads(ws.receive_text())
        assert data["type"] == "message"
        assert data["content"] == "Hi"
        assert data["senderName"] == "TestUser"


def test_online_users_endpoint():
    TestClient(app)
    db = TestingSessionLocal()
    img_binary = BytesIO()

    with Image.open(DEFAULT_AVATAR) as img:
        img.save(img_binary, format="PNG")

    user = User(
        name="Online",
        surname="Test",
        email="online-test@example.com",
        password="hash",
        avatar=img_binary.getvalue(),
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()

    token = Serializer(
        app_settings.chat_secret_key,
    ).dumps({"user_id": user.id})
    client.cookies.set("access_token", token)

    response = client.get("/online-users")
    data = response.json()

    assert response.status_code == 200
    assert "online_user_ids" in data
    assert isinstance(data["online_user_ids"], list)
    db.close()


def test_websocket_auth_failure_no_token():
    ws_client = WSClient(ws_app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/ws/no-token-ch"):
            pass
    assert exc_info.value.code == 4008


def test_websocket_user_not_found():
    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": NONEXISTENT_ID})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/ws/no-user-ch"):
            pass
    assert exc_info.value.code == 4008


def test_websocket_typing():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-typing")
    friend = create_test_user(db, name="Friend", email_suffix="-typing-friend")
    ch = Channel(channel_id="typing-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    ws_client2 = WSClient(ws_app)
    ws_client2.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/typing-ch") as ws1:
        with ws_client2.websocket_connect("/ws/typing-ch") as ws2:
            data = ws2.receive_text()
            parsed = json.loads(data)
            assert parsed["type"] == "user_online"

            ws1.send_json({"type": "typing", "typing": True})
            data = ws2.receive_text()
            parsed = json.loads(data)
            assert parsed["type"] == "typing"
            assert parsed["user_name"] == "TestUser"
            assert parsed["typing"] is True


def test_websocket_group_chat():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-group")
    friend = create_test_user(db, name="GFriend", email_suffix="-group-friend")
    group = GroupChat(name="Test Group", created_at=datetime.now(), created_by=user.id)
    db.add(group)
    db.commit()
    gm = GroupMember(group_id=group.id, user_id=user.id, joined_at=datetime.now())
    gm2 = GroupMember(group_id=group.id, user_id=friend.id, joined_at=datetime.now())
    db.add(gm)
    db.add(gm2)
    group_id = group.id
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect(f"/ws/group/{group_id}") as ws:
        ws.send_json({"type": "message", "message": "Hello group!"})
        data = ws.receive_text()
        parsed = json.loads(data)
        assert parsed["type"] == "message"
        assert parsed["content"] == "Hello group!"
        assert parsed["senderName"] == "TestUser"


def test_websocket_group_non_member():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-gnm")
    other = create_test_user(db, name="Other", email_suffix="-gnm-other")
    group = GroupChat(
        name="Private Group", created_at=datetime.now(), created_by=other.id
    )
    db.add(group)
    db.commit()
    gm = GroupMember(group_id=group.id, user_id=other.id, joined_at=datetime.now())
    db.add(gm)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/ws/group/{group.id}"):
            pass
    assert exc_info.value.code == 4003


def test_websocket_invalid_channel():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-badch")
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/nonexistent-channel") as ws:
        ws.send_json({"type": "message", "message": "Hello?"})
        ws.send_json({"type": "typing", "typing": False})
        ws.close()


def test_websocket_reconnect_cancels_pending_leave():
    db = TestingSessionLocal()
    user = create_test_user(db, email_suffix="-recon")
    friend = create_test_user(db, name="FriendR", email_suffix="-recon-f")
    ch = Channel(channel_id="recon-ch", user1_id=user.id, user2_id=friend.id)
    db.add(ch)
    db.commit()
    db.close()

    token = Serializer(app_settings.chat_secret_key).dumps({"user_id": user.id})
    ws_client = WSClient(ws_app)
    ws_client.cookies.set("access_token", token)

    with ws_client.websocket_connect("/ws/recon-ch") as ws:
        ws.send_json({"type": "message", "message": "first"})
        data = ws.receive_text()
        assert "first" in data

    with ws_client.websocket_connect("/ws/recon-ch") as ws:
        ws.send_json({"type": "message", "message": "reconnect"})
        data = ws.receive_text()
        assert "reconnect" in data

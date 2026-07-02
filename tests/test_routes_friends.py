from datetime import datetime, timedelta

from conftest import (
    authed_client,
    create_friendship,
    create_user,
    NONEXISTENT_ID,
)
from project.python.models import FriendStatus
from project.python.routes.helpers import generate_csrf_token
from tests.model_test import TestingSessionLocal


def test_add_friend_old_pending_renews_last_sent():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Old",
        "Pending",
        "old-pending@example.com",
    )
    target = create_user(
        db,
        "Target",
        "Old",
        "target-old@example.com",
    )
    old_date = datetime.now() - timedelta(days=20)
    create_friendship(db, user, target, FriendStatus.PENDING, last_sent=old_date)

    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_add_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Friend",
        "add-friend@example.com",
    )
    target = create_user(
        db,
        "Target",
        "User",
        "target-user@example.com",
    )
    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_add_friend_duplicate_pending():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Dup",
        "add-dup@example.com",
    )
    target = create_user(
        db,
        "Target",
        "Dup",
        "target-dup@example.com",
    )

    create_friendship(db, user, target, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 400


def test_add_friend_duplicate_denied():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Add",
        "Den",
        "add-den@example.com",
    )
    target = create_user(
        db,
        "Target",
        "Den",
        "target-den@example.com",
    )
    create_friendship(
        db, user, target, FriendStatus.DENIED, last_sent=datetime(2020, 1, 1)
    )

    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_accept_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Accept",
        "User",
        "accept-user@example.com",
    )
    requester = create_user(
        db,
        "Request",
        "er",
        "requester@example.com",
    )

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_accept_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "AFNF",
        "User",
        "afnf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{NONEXISTENT_ID}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 404


def test_deny_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Deny",
        "User",
        "deny-user@example.com",
    )
    requester = create_user(
        db,
        "Request",
        "deny",
        "requester-deny@example.com",
    )

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_deny_friend_not_found():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "DNFNF",
        "User",
        "dnfnf-user@example.com",
    )

    db.close()
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{NONEXISTENT_ID}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 404


def test_add_friend_redirects_to_search_user():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "User", "rf-user@example.com")
    target = create_user(db, "RF", "Target", "rf-target@example.com")

    local_client = authed_client(user)
    response = local_client.post(
        f"/add_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/search_user" in response.headers["location"]


def test_accept_friend_redirects_to_friend_requests():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "Accept", "rf-accept@example.com")
    requester = create_user(db, "RF", "Requester", "rf-requester@example.com")

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/accept_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/friend_requests" in response.headers["location"]


def test_deny_friend_redirects_to_friend_requests():
    db = TestingSessionLocal()
    user = create_user(db, "RF", "Deny", "rf-deny@example.com")
    requester = create_user(db, "RF", "DenyReq", "rf-denyreq@example.com")

    create_friendship(db, requester, user, FriendStatus.PENDING)
    local_client = authed_client(user)
    response = local_client.post(
        f"/deny_friend/{requester.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/friend_requests" in response.headers["location"]


def test_block_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Block",
        "User",
        "block-user@example.com",
    )
    target = create_user(
        db,
        "Blocked",
        "Target",
        "blocked-target@example.com",
    )

    create_friendship(db, user, target, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.post(
        f"/block_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200


def test_unblock_friend():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Unblock",
        "User",
        "unblock-user@example.com",
    )
    target = create_user(
        db,
        "Unblocked",
        "Target",
        "unblocked-target@example.com",
    )

    create_friendship(db, user, target, FriendStatus.BLOCKED)
    local_client = authed_client(user)
    response = local_client.post(
        f"/unblock_friend/{target.id}",
        data={"csrf_token": generate_csrf_token(user.id)},
    )

    assert response.status_code == 200

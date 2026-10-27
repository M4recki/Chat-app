from conftest import (
    authed_client,
    client,
    create_channel,
    create_friendship,
    create_user,
)

from project.python.models import FriendStatus
from tests.model_test import TestingSessionLocal


def test_search_user_returns_other_users():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search",
        "Owner",
        "search-owner@example.com",
    )
    other = create_user(
        db,
        "Search",
        "Target",
        "search-target@example.com",
    )

    from conftest import set_access_token as _sat

    _sat(user.id)

    response = client.get("/search_user")

    assert response.status_code == 200
    assert other.name in response.text
    assert other.surname in response.text


def test_search_user_no_token():
    response = client.get("/search_user")
    assert response.status_code == 401


def test_search_user_with_friends():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search",
        "User",
        "search-user@example.com",
    )
    friend = create_user(
        db,
        "Search",
        "Friend",
        "search-friend@example.com",
    )
    other = create_user(
        db,
        "Other",
        "User",
        "other-user@example.com",
    )
    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    create_friendship(db, other, user, FriendStatus.PENDING)

    create_channel(db, user, friend)

    local_client = authed_client(user)
    response = local_client.get("/search_user")
    assert response.status_code == 200


def test_search_user_with_friend_no_channel():
    db = TestingSessionLocal()
    user = create_user(
        db,
        "Search2",
        "User",
        "search-user2@example.com",
    )
    friend = create_user(
        db,
        "Search2",
        "Friend",
        "search-friend2@example.com",
    )

    create_friendship(db, user, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(user)
    response = local_client.get("/search_user")

    assert response.status_code == 200


def test_search_user_with_query_filters_by_name():
    db = TestingSessionLocal()
    user = create_user(db, "SQ", "Owner", "sq-owner@example.com")
    jan = create_user(db, "Jan", "Kowalski", "sq-jan@example.com")
    create_user(db, "Piotr", "Nowak", "sq-piotr@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=Jan")

    assert response.status_code == 200
    assert jan.name in response.text
    assert jan.surname in response.text


def test_search_user_with_query_filters_by_email():
    db = TestingSessionLocal()
    user = create_user(db, "SQ2", "Owner", "sq2-owner@example.com")
    target = create_user(db, "Target", "Unique", "unique-email@example.com")
    create_user(db, "Other", "User", "other@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=unique-email")

    assert response.status_code == 200
    assert target.name in response.text
    assert target.surname in response.text


def test_search_user_with_query_no_results():
    db = TestingSessionLocal()
    user = create_user(db, "SQ3", "Owner", "sq3-owner@example.com")
    create_user(db, "Some", "User", "some@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=xyz123nonexistent")

    assert response.status_code == 200
    assert "Some" not in response.text


def test_search_user_with_empty_query_returns_all():
    db = TestingSessionLocal()
    user = create_user(db, "SQ4", "Owner", "sq4-owner@example.com")
    user1 = create_user(db, "Alpha", "User", "alpha@example.com")
    user2 = create_user(db, "Beta", "User", "beta@example.com")

    local_client = authed_client(user)
    response = local_client.get("/search_user?q=")

    assert response.status_code == 200
    assert user1.name in response.text
    assert user2.name in response.text

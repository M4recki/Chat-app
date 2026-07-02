from conftest import (
    authed_client,
    create_friendship,
    create_group,
    create_group_member,
    create_group_message,
    create_user,
    NONEXISTENT_ID,
)
from project.python.models import (
    FriendStatus,
    GroupChat,
    GroupMember,
    GroupMessage,
)
from project.python.routes.helpers import generate_csrf_token
from tests.model_test import TestingSessionLocal


def test_group_chat_list_empty():
    db = TestingSessionLocal()
    user = create_user(db, "GL", "Empty", "gl-empty@example.com")
    local_client = authed_client(user)
    response = local_client.get("/group_chat_list")
    assert response.status_code == 200


def test_group_chat_list_with_groups():
    db = TestingSessionLocal()
    user = create_user(db, "GL", "With", "gl-with@example.com")
    group = create_group(db, "Test Group", user)
    create_group_member(db, group.id, user)
    local_client = authed_client(user)
    response = local_client.get("/group_chat_list")
    assert response.status_code == 200


def test_create_group_form():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Form", "cg-form@example.com")
    local_client = authed_client(user)
    response = local_client.get("/create_group")
    assert response.status_code == 200


def test_create_group_success():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Create", "cg-create@example.com")
    friend = create_user(db, "CG", "Friend", "cg-friend@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "New Group",
            "member_ids": str(friend.id),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/group_chat/" in response.headers["location"]
    db_check = TestingSessionLocal()
    groups = db_check.query(GroupChat).all()
    assert len(groups) == 1
    assert groups[0].name == "New Group"
    members = (
        db_check.query(GroupMember).filter(GroupMember.group_id == groups[0].id).all()
    )
    assert len(members) == 2


def test_create_group_empty_name():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "Empty", "cg-empty@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "",
            "member_ids": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 422


def test_create_group_whitespace_name():
    db = TestingSessionLocal()
    user = create_user(db, "CG", "WS", "cg-ws@example.com")

    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        "/create_group",
        data={
            "name": "   ",
            "member_ids": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_group_chat_page():
    db = TestingSessionLocal()
    user = create_user(db, "GP", "View", "gp-view@example.com")

    group = create_group(db, "View Group", user)
    create_group_member(db, group.id, user)
    local_client = authed_client(user)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 200


def test_group_chat_page_not_member():
    db = TestingSessionLocal()
    user = create_user(db, "GP", "NoMember", "gp-nomember@example.com")
    owner = create_user(db, "GP", "Owner", "gp-owner@example.com")

    group = create_group(db, "Private", owner)
    create_group_member(db, group.id, owner)
    local_client = authed_client(user)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 403


def test_group_chat_page_creator_with_friends():
    db = TestingSessionLocal()
    creator = create_user(db, "GP", "Creator", "gp-creator@example.com")
    friend = create_user(db, "GP", "Friend", "gp-friend@example.com")
    other = create_user(db, "GP", "Other", "gp-other@example.com")

    group = create_group(db, "With Friends", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    create_friendship(db, creator, friend, FriendStatus.ACCEPTED)
    local_client = authed_client(creator)
    response = local_client.get(f"/group_chat/{group.id}")

    assert response.status_code == 200
    assert friend.name in response.text


def test_add_group_member():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator", "ag-creator@example.com")
    friend = create_user(db, "AG", "Friend", "ag-friend@example.com")

    group = create_group(db, "Add Member", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": friend.id,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    db_check = TestingSessionLocal()
    member = (
        db_check.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == friend.id)
        .first()
    )
    assert member is not None


def test_add_group_member_not_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator2", "ag-creator2@example.com")
    other = create_user(db, "AG", "Other", "ag-other@example.com")
    friend = create_user(db, "AG", "Friend2", "ag-friend2@example.com")

    group = create_group(db, "Add Member 2", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": friend.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_add_group_member_already_member():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator3", "ag-creator3@example.com")
    member = create_user(db, "AG", "Member", "ag-member@example.com")

    group = create_group(db, "Add Member 3", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_add_group_member_nonexistent_user():
    db = TestingSessionLocal()
    creator = create_user(db, "AG", "Creator4", "ag-creator4@example.com")

    group = create_group(db, "Bad Add", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/add_group_member/{group.id}",
        data={
            "user_id": str(NONEXISTENT_ID),
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 404


def test_remove_group_member():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator", "rg-creator@example.com")
    member = create_user(db, "RG", "Member", "rg-member@example.com")

    group = create_group(db, "Remove Member", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_check = TestingSessionLocal()
    remaining = (
        db_check.query(GroupMember).filter(GroupMember.group_id == group.id).all()
    )
    assert len(remaining) == 1
    assert remaining[0].user_id == creator.id


def test_remove_group_member_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator2", "rg-creator2@example.com")

    group = create_group(db, "Remove Creator", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": creator.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_remove_group_member_not_creator():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator3", "rg-creator3@example.com")
    other = create_user(db, "RG", "Other", "rg-other@example.com")
    member = create_user(db, "RG", "Member3", "rg-member3@example.com")

    group = create_group(db, "Remove Not Creator", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, other)
    create_group_member(db, group.id, member)
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": member.id,
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_remove_group_member_nonexistent():
    db = TestingSessionLocal()
    creator = create_user(db, "RG", "Creator4", "rg-creator4@example.com")

    group = create_group(db, "Remove Missing", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/remove_group_member/{group.id}",
        data={
            "user_id": str(NONEXISTENT_ID),
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 404


def test_edit_group_message():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "Edit", "eg-edit@example.com")

    group = create_group(db, "Edit Msg", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "original content")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "updated content",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    db_check = TestingSessionLocal()
    updated = db_check.query(GroupMessage).filter(GroupMessage.id == msg.id).first()
    assert updated is not None
    assert updated.content == "updated content"
    assert updated.edited_at is not None


def test_edit_group_message_not_owner():
    db = TestingSessionLocal()
    owner = create_user(db, "EG", "Owner", "eg-owner@example.com")
    other = create_user(db, "EG", "Other", "eg-other2@example.com")

    group = create_group(db, "Edit Other", owner)
    create_group_member(db, group.id, owner)
    create_group_member(db, group.id, other)
    msg = create_group_message(db, group.id, owner, "owner msg")
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "hacked",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_edit_group_message_empty_content():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "Empty", "eg-empty2@example.com")

    group = create_group(db, "Edit Empty", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "some content")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 422


def test_edit_group_message_whitespace_content():
    db = TestingSessionLocal()
    user = create_user(db, "EG", "WS", "eg-ws@example.com")

    group = create_group(db, "Edit WS", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "original")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)

    response = local_client.post(
        f"/edit_group_message/{msg.id}",
        data={
            "content": "   ",
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 400


def test_delete_group_message():
    db = TestingSessionLocal()
    user = create_user(db, "DG", "Delete", "dg-delete@example.com")

    group = create_group(db, "Delete Msg", user)
    create_group_member(db, group.id, user)
    msg = create_group_message(db, group.id, user, "to delete")
    local_client = authed_client(user)
    csrf = generate_csrf_token(user.id)
    response = local_client.post(
        f"/delete_group_message/{msg.id}",
        data={
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    db_check = TestingSessionLocal()
    deleted = db_check.query(GroupMessage).filter(GroupMessage.id == msg.id).first()
    assert deleted is None


def test_delete_group_message_not_owner():
    db = TestingSessionLocal()
    owner = create_user(db, "DG", "Owner", "dg-owner@example.com")
    other = create_user(db, "DG", "Other", "dg-other@example.com")

    group = create_group(db, "Delete Other", owner)
    create_group_member(db, group.id, owner)
    create_group_member(db, group.id, other)
    msg = create_group_message(db, group.id, owner, "owner msg")
    local_client = authed_client(other)
    csrf = generate_csrf_token(other.id)

    response = local_client.post(
        f"/delete_group_message/{msg.id}",
        data={
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_group_members_json():
    db = TestingSessionLocal()
    creator = create_user(db, "Alice", "Creator", "gm-creator@example.com")
    member = create_user(db, "Bob", "Member", "gm-member@example.com")

    group = create_group(db, "Members JSON", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    response = local_client.get(f"/group_members/{group.id}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    names = {u["name"] for u in data}
    assert "Alice" in names
    assert "Bob" in names


def test_group_members_json_not_member():
    db = TestingSessionLocal()
    creator = create_user(db, "GM", "Creator2", "gm-creator2@example.com")
    outsider = create_user(db, "GM", "Outsider", "gm-outsider@example.com")

    group = create_group(db, "Members JSON 2", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(outsider)
    response = local_client.get(f"/group_members/{group.id}")

    assert response.status_code == 403


def test_leave_group_success():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator", "lg-creator@example.com")
    member = create_user(db, "LG", "Member", "lg-member@example.com")

    group = create_group(db, "Leave Group", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(member)
    csrf = generate_csrf_token(member.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/group_chat_list"

    db_check = TestingSessionLocal()
    remaining = (
        db_check.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == member.id)
        .first()
    )
    assert remaining is None
    db_check.close()


def test_leave_group_creator_forbidden():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator2", "lg-creator2@example.com")
    member = create_user(db, "LG", "Member2", "lg-member2@example.com")

    group = create_group(db, "Leave Group 2", creator)
    create_group_member(db, group.id, creator)
    create_group_member(db, group.id, member)
    local_client = authed_client(creator)
    csrf = generate_csrf_token(creator.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 400
    assert "Creator cannot leave" in response.text


def test_leave_group_not_member():
    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator3", "lg-creator3@example.com")
    outsider = create_user(db, "LG", "Outsider", "lg-outsider@example.com")

    group = create_group(db, "Leave Group 3", creator)
    create_group_member(db, group.id, creator)
    local_client = authed_client(outsider)
    csrf = generate_csrf_token(outsider.id)

    response = local_client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 404


def test_leave_group_no_auth():
    from conftest import client

    db = TestingSessionLocal()
    creator = create_user(db, "LG", "Creator4", "lg-creator4@example.com")
    group = create_group(db, "Leave Group 4", creator)
    create_group_member(db, group.id, creator)

    response = client.post(
        f"/leave_group/{group.id}",
        data={"csrf_token": generate_csrf_token(0)},
    )

    assert response.status_code == 401

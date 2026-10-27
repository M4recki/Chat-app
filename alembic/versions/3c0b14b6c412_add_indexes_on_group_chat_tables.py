"""add indexes on group chat tables

Revision ID: 3c0b14b6c412
Revises: b5a749014470
Create Date: 2026-10-27 18:48:36.452426
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3c0b14b6c412"
down_revision = "b5a749014470"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_group_chats_created_by", "group_chats", ["created_by"]),
    ("ix_group_members_group_id", "group_members", ["group_id"]),
    ("ix_group_members_user_id", "group_members", ["user_id"]),
    ("ix_group_messages_group_id", "group_messages", ["group_id"]),
    ("ix_group_messages_user_id", "group_messages", ["user_id"]),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)

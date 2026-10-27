"""add indexes on channels friends messages

Revision ID: bd39a0675b4a
Revises: 3c0b14b6c412
Create Date: 2026-10-27 19:05:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "bd39a0675b4a"
down_revision = "3c0b14b6c412"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_channels_user1_id", "channels", ["user1_id"]),
    ("ix_channels_user2_id", "channels", ["user2_id"]),
    ("ix_chatbot_messages_user_id", "chatbot_messages", ["user_id"]),
    ("ix_friends_user1_id", "friends", ["user1_id"]),
    ("ix_friends_user2_id", "friends", ["user2_id"]),
    ("ix_friends_blocked_by_user", "friends", ["blocked_by_user"]),
    ("ix_messages_channel_id", "messages", ["channel_id"]),
    ("ix_messages_user_id", "messages", ["user_id"]),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)

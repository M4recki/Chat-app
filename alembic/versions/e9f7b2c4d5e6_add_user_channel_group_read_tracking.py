"""add_user_channel_group_read_tracking

Revision ID: e9f7b2c4d5e6
Revises: 8f2e8a1b3c4d
Create Date: 2026-07-01 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e9f7b2c4d5e6"
down_revision = "8f2e8a1b3c4d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_channel_read",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "channel_id",
            sa.String(100),
            sa.ForeignKey("channels.channel_id"),
            nullable=False,
        ),
        sa.Column(
            "last_read_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
    )
    op.create_table(
        "user_group_read",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("group_chats.id"), nullable=False
        ),
        sa.Column(
            "last_read_message_id",
            sa.Integer(),
            sa.ForeignKey("group_messages.id"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_table("user_group_read")
    op.drop_table("user_channel_read")

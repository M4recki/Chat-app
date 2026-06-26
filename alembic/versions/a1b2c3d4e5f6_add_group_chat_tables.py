"""add group chat tables

Revision ID: a1b2c3d4e5f6
Revises: 347cfe570c0f
Create Date: 2026-06-09 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "347cfe570c0f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "group_chats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_group_chats_created_by"), "group_chats", ["created_by"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["group_chats.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_group_members_group_id"), "group_members", ["group_id"])
    op.create_index(op.f("ix_group_members_user_id"), "group_members", ["user_id"])

    op.create_table(
        "group_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["group_chats.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_group_messages_group_id"), "group_messages", ["group_id"])
    op.create_index(op.f("ix_group_messages_user_id"), "group_messages", ["user_id"])


def downgrade():
    op.drop_table("group_messages")
    op.drop_table("group_members")
    op.drop_table("group_chats")

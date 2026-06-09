"""create_initial_schema

Revision ID: 593b10fbbc14
Revises:
Create Date: 2026-06-01 20:28:34.271650
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "593b10fbbc14"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("surname", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("password", sa.String(length=100), nullable=False),
        sa.Column("avatar", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Create channels table
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("user1_id", sa.Integer(), nullable=False),
        sa.Column("user2_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user1_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user2_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id"),
    )

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.channel_id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create friends table
    op.create_table(
        "friends",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user1_id", sa.Integer(), nullable=False),
        sa.Column("user2_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("blocked_by_user", sa.Integer(), nullable=True),
        sa.Column("last_sent", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["blocked_by_user"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user1_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user2_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create chatbot_messages table
    op.create_table(
        "chatbot_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("chatbot_messages")
    op.drop_table("friends")
    op.drop_table("messages")
    op.drop_table("channels")
    op.drop_table("users")

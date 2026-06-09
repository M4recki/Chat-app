"""change_message_content_to_text

Revision ID: 347cfe570c0f
Revises: 37366e2ef87a
Create Date: 2026-06-09 11:35:05.223945
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "347cfe570c0f"
down_revision = "37366e2ef87a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column(
            "content",
            existing_type=sa.String(500),
            type_=sa.Text,
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column(
            "content",
            existing_type=sa.Text,
            type_=sa.String(500),
            existing_nullable=False,
        )


"""add_edited_at_to_messages

Revision ID: c3e3f08c8e90
Revises: 347cfe570c0f
Create Date: 2026-06-30 13:26:51.962329
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3e3f08c8e90'
down_revision = '347cfe570c0f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("edited_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("edited_at")

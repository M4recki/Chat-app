"""add_last_active_to_users

Revision ID: 8f2e8a1b3c4d
Revises: c3e3f08c8e90
Create Date: 2026-07-01 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8f2e8a1b3c4d"
down_revision = "c3e3f08c8e90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("last_active", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_active")

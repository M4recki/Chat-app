"""increase_password_length

Revision ID: 37366e2ef87a
Revises: 593b10fbbc14
Create Date: 2026-06-08 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "37366e2ef87a"
down_revision = "593b10fbbc14"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "users", "password",
        type_=sa.String(255),
        existing_type=sa.String(100),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "users", "password",
        type_=sa.String(100),
        existing_type=sa.String(255),
        nullable=False,
    )

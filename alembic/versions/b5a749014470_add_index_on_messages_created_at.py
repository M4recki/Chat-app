"""add index on messages.created_at

Revision ID: b5a749014470
Revises: e9f7b2c4d5e6
Create Date: 2026-06-15 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5a749014470"
down_revision: Union[str, None] = "e9f7b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_messages_created_at", "messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_created_at")

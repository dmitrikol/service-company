"""add is_active to clients

Revision ID: d7f4a2c9e3b1
Revises: c5e3a1b2f4d6
Create Date: 2026-08-11 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7f4a2c9e3b1'
down_revision: Union[str, Sequence[str], None] = 'c5e3a1b2f4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clients', sa.Column(
        'is_active', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clients', 'is_active')

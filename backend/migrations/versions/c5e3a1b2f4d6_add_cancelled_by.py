"""add cancelled_by to appointments

Revision ID: c5e3a1b2f4d6
Revises: 095ffd6dc1af
Create Date: 2026-08-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e3a1b2f4d6'
down_revision: Union[str, Sequence[str], None] = '095ffd6dc1af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('appointments', sa.Column('cancelled_by', sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('appointments', 'cancelled_by')

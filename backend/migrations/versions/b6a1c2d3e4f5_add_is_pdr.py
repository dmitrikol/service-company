"""add is_pdr to services

PDR-записи (выпрямление вмятин) не пересекаются с записями на другие услуги:
у PDR свой учёт времени. Существующую услугу с PDR в названии помечаем сразу.

Revision ID: b6a1c2d3e4f5
Revises: d7f4a2c9e3b1
Create Date: 2026-08-12 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6a1c2d3e4f5'
down_revision: Union[str, Sequence[str], None] = 'd7f4a2c9e3b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('services', sa.Column('is_pdr', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
    op.execute("UPDATE services SET is_pdr = true WHERE name ILIKE '%pdr%'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('services', 'is_pdr')

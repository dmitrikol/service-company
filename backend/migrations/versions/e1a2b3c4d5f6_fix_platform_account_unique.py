"""fix platform_account unique constraint to (platform, external_id)

Revision ID: e1a2b3c4d5f6
Revises: f2b3c4d5e6a7
Create Date: 2026-08-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, Sequence[str], None] = 'f2b3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Раньше `external_id` был уникален сам по себе — это ломается, если у
    У пользователей разных платформ случайно совпадают числовые ID (независимые
    пространства ID). Правильная уникальность — по паре (platform, external_id).
    """
    op.drop_constraint(
        'platform_accounts_external_id_key', 'platform_accounts', type_='unique')
    op.create_unique_constraint(
        'uq_platform_accounts_platform_external_id',
        'platform_accounts', ['platform', 'external_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_platform_accounts_platform_external_id',
        'platform_accounts', type_='unique')
    op.create_unique_constraint(
        'platform_accounts_external_id_key', 'platform_accounts', ['external_id'])

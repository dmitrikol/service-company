"""add reminder retry tracking to appointments

Revision ID: b8c9d0e1f2a3
Revises: a7c8d9e0f1b2
Create Date: 2026-11-26 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7c8d9e0f1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет счётчик неудач и время последней ошибки отправки напоминания."""
    op.add_column(
        'appointments',
        sa.Column('reminder_last_error_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'appointments',
        sa.Column(
            'reminder_failures',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('appointments', 'reminder_failures')
    op.drop_column('appointments', 'reminder_last_error_at')

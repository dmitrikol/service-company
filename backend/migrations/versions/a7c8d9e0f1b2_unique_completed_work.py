"""add unique constraint on completed_works.appointment_id

Revision ID: a7c8d9e0f1b2
Revises: e1a2b3c4d5f6
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c8d9e0f1b2'
down_revision: Union[str, Sequence[str], None] = 'e1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Одна запись — одна работа в журнале.

    Старые дубли (если повторное завершение создавало несколько строк)
    удаляются: остаётся самая ранняя запись. На уровне БД ставим ограничение,
    чтобы гонка двух запросов не создала вторую работу.
    """
    op.execute(
        """
        DELETE FROM completed_works c
        USING completed_works d
        WHERE c.appointment_id IS NOT NULL
          AND c.appointment_id = d.appointment_id
          AND c.id > d.id
        """
    )
    op.create_unique_constraint(
        'uq_completed_works_appointment_id',
        'completed_works',
        ['appointment_id'],
    )


def downgrade() -> None:
    """Снимает ограничение, дубли при этом не восстанавливаются."""
    op.drop_constraint(
        'uq_completed_works_appointment_id',
        'completed_works',
        type_='unique',
    )

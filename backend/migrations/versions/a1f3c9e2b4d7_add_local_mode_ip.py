"""add local_mode_ip to rooms

Revision ID: a1f3c9e2b4d7
Revises: 6af920147b13
Create Date: 2026-10-27 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f3c9e2b4d7'
down_revision: Union[str, None] = '6af920147b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rooms', sa.Column('local_mode_ip', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('rooms', 'local_mode_ip')

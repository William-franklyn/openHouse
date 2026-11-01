"""add state_json for snapshot-style game kinds

Revision ID: 70bb17974952
Revises: f7b2e9c4a815
Create Date: 2026-10-31 19:44:46.544964
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '70bb17974952'
down_revision: Union[str, None] = 'f7b2e9c4a815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('games', sa.Column('state_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('games', 'state_json')

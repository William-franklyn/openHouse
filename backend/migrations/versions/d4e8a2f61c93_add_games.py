"""add games table

Revision ID: d4e8a2f61c93
Revises: a1f3c9e2b4d7
Create Date: 2026-10-31 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8a2f61c93'
down_revision: Union[str, None] = 'a1f3c9e2b4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'games',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('room_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('white_member_id', sa.String(length=32), nullable=False),
        sa.Column('black_member_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('moves_json', sa.Text(), nullable=False),
        sa.Column('result', sa.String(length=8), nullable=True),
        sa.Column('termination', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_games_room_id'), 'games', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_games_room_id'), table_name='games')
    op.drop_table('games')

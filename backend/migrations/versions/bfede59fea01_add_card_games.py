"""add card games

Revision ID: bfede59fea01
Revises: 3d2df6a0db27
Create Date: 2026-11-01 11:23:50.360530
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bfede59fea01'
down_revision: Union[str, None] = '3d2df6a0db27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'card_games',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('room_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('host_member_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('participants_json', sa.Text(), nullable=False),
        sa.Column('starting_chips', sa.Integer(), nullable=False),
        sa.Column('state_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_card_games_room_id'), 'card_games', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_card_games_room_id'), table_name='card_games')
    op.drop_table('card_games')

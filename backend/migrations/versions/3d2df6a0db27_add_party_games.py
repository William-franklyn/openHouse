"""add party games

Revision ID: 3d2df6a0db27
Revises: 70bb17974952
Create Date: 2026-11-01 01:37:47.843640
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3d2df6a0db27'
down_revision: Union[str, None] = '70bb17974952'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'party_games',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('room_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('host_member_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('participants_json', sa.Text(), nullable=False),
        sa.Column('scores_json', sa.Text(), nullable=False),
        sa.Column('round_index', sa.Integer(), nullable=False),
        sa.Column('total_rounds', sa.Integer(), nullable=False),
        sa.Column('state_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_party_games_room_id'), 'party_games', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_party_games_room_id'), table_name='party_games')
    op.drop_table('party_games')

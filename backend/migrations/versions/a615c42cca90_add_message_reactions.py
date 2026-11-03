"""add message reactions

Revision ID: a615c42cca90
Revises: bfede59fea01
Create Date: 2026-11-03 09:08:37.928143
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a615c42cca90'
down_revision: Union[str, None] = 'bfede59fea01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'message_reactions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('message_id', sa.String(length=32), nullable=False),
        sa.Column('member_id', sa.String(length=32), nullable=False),
        sa.Column('emoji', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'member_id', 'emoji', name='uq_reaction_message_member_emoji'),
    )
    op.create_index(op.f('ix_message_reactions_message_id'), 'message_reactions', ['message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_message_reactions_message_id'), table_name='message_reactions')
    op.drop_table('message_reactions')

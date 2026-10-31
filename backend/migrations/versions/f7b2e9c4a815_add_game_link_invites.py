"""allow nullable black_member_id and add link_token for chess link invites

Revision ID: f7b2e9c4a815
Revises: d4e8a2f61c93
Create Date: 2026-10-31 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7b2e9c4a815'
down_revision: Union[str, None] = 'd4e8a2f61c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('games', 'black_member_id', existing_type=sa.String(length=32), nullable=True)
    op.add_column('games', sa.Column('link_token', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_games_link_token'), 'games', ['link_token'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_games_link_token'), table_name='games')
    op.drop_column('games', 'link_token')
    op.alter_column('games', 'black_member_id', existing_type=sa.String(length=32), nullable=False)

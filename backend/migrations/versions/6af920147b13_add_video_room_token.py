"""add video_room_token to rooms

Revision ID: 6af920147b13
Revises: 302d103d56b7
Create Date: 2026-10-26 12:00:00.000000
"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6af920147b13'
down_revision: Union[str, None] = '302d103d56b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable first - existing rows need a value before this can become
    # NOT NULL, and that has to happen row-by-row in Python (not a single
    # server-side default) since every room needs its OWN unguessable
    # token, not one shared value.
    op.add_column('rooms', sa.Column('video_room_token', sa.String(length=32), nullable=True))

    conn = op.get_bind()
    rooms = conn.execute(sa.text("SELECT id FROM rooms WHERE video_room_token IS NULL")).fetchall()
    for (room_id,) in rooms:
        conn.execute(
            sa.text("UPDATE rooms SET video_room_token = :token WHERE id = :id"),
            {"token": secrets.token_hex(16), "id": room_id},
        )

    op.alter_column('rooms', 'video_room_token', nullable=False)


def downgrade() -> None:
    op.drop_column('rooms', 'video_room_token')

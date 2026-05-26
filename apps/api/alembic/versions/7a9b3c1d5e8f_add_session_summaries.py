"""add session_summaries table for cross-session memory

Revision ID: 7a9b3c1d5e8f
Revises: fe85e4504f2b
Create Date: 2026-05-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a9b3c1d5e8f'
down_revision: Union[str, Sequence[str], None] = 'fe85e4504f2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('session_summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'session_id', name='uq_session_summaries_user_session'),
    )
    op.create_index(op.f('ix_session_summaries_user_id'), 'session_summaries', ['user_id'])
    op.create_index(op.f('ix_session_summaries_session_id'), 'session_summaries', ['session_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_session_summaries_session_id'), table_name='session_summaries')
    op.drop_index(op.f('ix_session_summaries_user_id'), table_name='session_summaries')
    op.drop_table('session_summaries')

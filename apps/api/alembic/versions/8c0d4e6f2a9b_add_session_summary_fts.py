"""Add search_vector (tsvector+GIN) and key_insights (JSONB) to session_summaries for PostgreSQL FTS

PRD Phase 2a: Cross-session memory with PostgreSQL full-text search.
- key_insights JSONB stores structured LLM-extracted insights
- search_vector TSVECTOR is auto-maintained via trigger on summary column
- GIN index enables fast full-text search queries

Revision ID: 8c0d4e6f2a9b
Revises: b7c9d3e5f1a8
Create Date: 2026-05-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR


revision: str = '8c0d4e6f2a9b'
down_revision: Union[str, Sequence[str], None] = 'b7c9d3e5f1a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION session_summaries_search_vector_update()
RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple', COALESCE(NEW.summary, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_TRIGGER_FUNCTION = """
DROP FUNCTION IF EXISTS session_summaries_search_vector_update() CASCADE;
"""


def upgrade() -> None:
    # 1. Add key_insights JSONB column (nullable)
    op.add_column(
        'session_summaries',
        sa.Column('key_insights', JSONB, nullable=True,
                    comment='结构化洞察: preferred_skills, salary_range, screening_patterns, rejected_reasons 等'),
    )

    # 2. Add search_vector TSVECTOR column (nullable initially)
    op.add_column(
        'session_summaries',
        sa.Column('search_vector', TSVECTOR, nullable=True,
                    comment='全文搜索向量 (由 trigger 自动从 summary 更新)'),
    )

    # 3. Create GIN index on search_vector
    op.create_index(
        'ix_session_summaries_search_vector',
        'session_summaries',
        ['search_vector'],
        postgresql_using='gin',
    )

    # 4. Create trigger function that auto-updates search_vector on INSERT/UPDATE of summary
    op.execute(TRIGGER_FUNCTION)

    # 5. Apply trigger: before INSERT or UPDATE of summary, recalculate search_vector
    op.execute(
        "CREATE TRIGGER trg_session_summaries_search_vector "
        "BEFORE INSERT OR UPDATE OF summary ON session_summaries "
        "FOR EACH ROW EXECUTE FUNCTION session_summaries_search_vector_update()"
    )

    # 6. Backfill existing rows — compute search_vector from current summary text
    op.execute(
        "UPDATE session_summaries "
        "SET search_vector = to_tsvector('simple', COALESCE(summary, '')) "
        "WHERE search_vector IS NULL"
    )


def downgrade() -> None:
    # 1. Drop trigger
    op.execute(
        "DROP TRIGGER IF EXISTS trg_session_summaries_search_vector ON session_summaries"
    )

    # 2. Drop trigger function
    op.execute(DROP_TRIGGER_FUNCTION)

    # 3. Drop GIN index
    op.drop_index('ix_session_summaries_search_vector', table_name='session_summaries')

    # 4. Drop columns
    op.drop_column('session_summaries', 'search_vector')
    op.drop_column('session_summaries', 'key_insights')

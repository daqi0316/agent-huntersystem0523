"""normalize_candidate_status_enum

Revision ID: 9e3062a04839
Revises: 7a9b3c1d5e8f
Create Date: 2026-05-26 19:10:10.469464

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9e3062a04839'
down_revision: Union[str, Sequence[str], None] = '7a9b3c1d5e8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_STATUSES = ('ACTIVE', 'ARCHIVED', 'BLACKLISTED')
NEW_STATUSES = ('active', 'archived', 'blacklisted')


def upgrade() -> None:
    conn = op.get_bind()

    # Create helper function to lowercase the old enum values
    conn.execute(sa.text(
        "CREATE OR REPLACE FUNCTION _temp_lower_candidate_status(s candidate_status) "
        "RETURNS TEXT AS $$ BEGIN RETURN lower(s::text); END; $$ LANGUAGE plpgsql"
    ))

    # Create new enum with all lowercase values
    conn.execute(sa.text(
        "CREATE TYPE candidate_status_new AS ENUM ("
        "'active','archived','blacklisted','pending_eval','evaluating',"
        "'evaluated','in_interview','completed','failed')"
    ))

    # Migrate column
    conn.execute(sa.text(
        "ALTER TABLE candidates ALTER COLUMN status TYPE candidate_status_new "
        "USING _temp_lower_candidate_status(status)::text::candidate_status_new"
    ))

    # Drop old type and function, rename new type
    conn.execute(sa.text("DROP FUNCTION _temp_lower_candidate_status"))
    conn.execute(sa.text("DROP TYPE candidate_status"))
    conn.execute(sa.text("ALTER TYPE candidate_status_new RENAME TO candidate_status"))


def downgrade() -> None:
    conn = op.get_bind()

    # Create helper function to uppercase first three values
    conn.execute(sa.text(
        "CREATE OR REPLACE FUNCTION _temp_upper_candidate_status(s candidate_status) "
        "RETURNS TEXT AS $$ "
        "BEGIN "
        "  RETURN CASE "
        "    WHEN s::text IN ('active','archived','blacklisted') THEN upper(s::text) "
        "    ELSE s::text "
        "  END; "
        "END; $$ LANGUAGE plpgsql"
    ))

    # Recreate old enum
    conn.execute(sa.text(
        "CREATE TYPE candidate_status_old AS ENUM ("
        "'ACTIVE','ARCHIVED','BLACKLISTED','pending_eval','evaluating',"
        "'evaluated','in_interview','completed','failed')"
    ))

    # Migrate column
    conn.execute(sa.text(
        "ALTER TABLE candidates ALTER COLUMN status TYPE candidate_status_old "
        "USING _temp_upper_candidate_status(status)::text::candidate_status_old"
    ))

    # Drop new type and function, rename old type
    conn.execute(sa.text("DROP FUNCTION _temp_upper_candidate_status"))
    conn.execute(sa.text("DROP TYPE candidate_status"))
    conn.execute(sa.text("ALTER TYPE candidate_status_old RENAME TO candidate_status"))

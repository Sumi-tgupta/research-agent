"""Phase 12 — request quotas (daily usage counters)

Creates: usage_counters (one row per subject per UTC day; see
app/db/models.py :: UsageCounterModel and app/rate_limit.py).

Coexistence note: like 0001, the app also calls Base.metadata.create_all() on
startup (app/db/session.py :: init_db) for zero-setup local SQLite, so the
table may already exist when this migration runs. The create is therefore
guarded by an inspector check — `alembic upgrade head` is safe whether or not
create_all has already made the table, and vice versa.

Revision ID: 0002_phase12_usage_counters
Revises: 0001_phase11_library
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_phase12_usage_counters"
down_revision = "0001_phase11_library"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    if "usage_counters" not in _existing_tables():
        op.create_table(
            "usage_counters",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("subject_key", sa.String(length=80), nullable=False),
            sa.Column("day", sa.String(length=10), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("subject_key", "day", name="uq_usage_subject_day"),
        )
        op.create_index("ix_usage_subject_day", "usage_counters", ["subject_key", "day"])


def downgrade() -> None:
    if "usage_counters" in _existing_tables():
        op.drop_table("usage_counters")

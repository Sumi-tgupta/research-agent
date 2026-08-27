"""Phase 11 — saved library (normalized, user-scoped)

Creates: folders, tags, research_sessions, reports, sources, claims, charts,
follow_ups, session_tags.

Coexistence note: the app also calls Base.metadata.create_all() on startup
(app/db/session.py :: init_db) for zero-setup local SQLite. So a table may
already exist when this migration runs. Each create is therefore guarded by an
inspector check — running `alembic upgrade head` is safe whether or not
create_all has already made the tables, and vice versa.

Revision ID: 0001_phase11_library
Revises:
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_phase11_library"
down_revision = None
branch_labels = None
depends_on = None


# Order matters for FKs on create (parents first) and drop (children first).
_TABLES_IN_DEP_ORDER = [
    "folders",
    "tags",
    "research_sessions",
    "reports",
    "sources",
    "claims",
    "charts",
    "follow_ups",
    "session_tags",
]


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    def missing(name: str) -> bool:
        return name not in existing

    if missing("folders"):
        op.create_table(
            "folders",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "name", name="uq_folder_user_name"),
        )
        op.create_index("ix_folders_user_id", "folders", ["user_id"])

    if missing("tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
        )
        op.create_index("ix_tags_user_id", "tags", ["user_id"])

    if missing("research_sessions"):
        op.create_table(
            "research_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("error_text", sa.Text(), nullable=True),
            sa.Column("citation_style", sa.String(length=10), nullable=False),
            sa.Column("target_language", sa.String(length=60), nullable=False),
            sa.Column("num_sub_questions", sa.Integer(), nullable=False),
            sa.Column("max_results_per_subquestion", sa.Integer(), nullable=False),
            sa.Column("revision_count", sa.Integer(), nullable=False),
            sa.Column("review_decision", sa.String(length=20), nullable=False),
            sa.Column("review_feedback", sa.Text(), nullable=False),
            sa.Column("plan_json", sa.JSON(), nullable=True),
            sa.Column("errors_json", sa.JSON(), nullable=True),
            sa.Column("folder_id", sa.String(length=36), nullable=True),
            sa.Column("starred", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_research_sessions_user_id", "research_sessions", ["user_id"])
        op.create_index("ix_research_sessions_status", "research_sessions", ["status"])
        op.create_index("ix_research_sessions_folder_id", "research_sessions", ["folder_id"])
        op.create_index("ix_session_user_created", "research_sessions", ["user_id", "created_at"])

    if missing("reports"):
        op.create_table(
            "reports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("final_report", sa.Text(), nullable=False),
            sa.Column("draft", sa.Text(), nullable=False),
            sa.Column("pdf_url", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("session_id", name="uq_report_session"),
        )
        op.create_index("ix_reports_session_id", "reports", ["session_id"])

    if missing("sources"):
        op.create_table(
            "sources",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("authors", sa.JSON(), nullable=True),
            sa.Column("abstract", sa.Text(), nullable=True),
            sa.Column("snippet", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False),
            sa.Column("kind", sa.String(length=10), nullable=False),
            sa.Column("published_date", sa.String(length=60), nullable=True),
            sa.Column("citation_count", sa.Integer(), nullable=True),
            sa.Column("relevance_score", sa.Float(), nullable=True),
            sa.Column("raw_id", sa.String(length=120), nullable=True),
            sa.Column("sub_question", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_sources_session_id", "sources", ["session_id"])

    if missing("claims"):
        op.create_table(
            "claims",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("sub_question", sa.Text(), nullable=False),
            sa.Column("verdict", sa.String(length=20), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("supporting_sources", sa.JSON(), nullable=True),
            sa.Column("contradicting_sources", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_claims_session_id", "claims", ["session_id"])

    if missing("charts"):
        op.create_table(
            "charts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("chart_type", sa.String(length=10), nullable=False),
            sa.Column("x_label", sa.String(length=200), nullable=False),
            sa.Column("y_label", sa.String(length=200), nullable=False),
            sa.Column("labels", sa.JSON(), nullable=True),
            sa.Column("values", sa.JSON(), nullable=True),
            sa.Column("png_url", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_charts_session_id", "charts", ["session_id"])

    if missing("follow_ups"):
        op.create_table(
            "follow_ups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_follow_ups_session_id", "follow_ups", ["session_id"])

    if missing("session_tags"):
        op.create_table(
            "session_tags",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("tag_id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("session_id", "tag_id", name="uq_session_tag"),
        )
        op.create_index("ix_session_tags_session_id", "session_tags", ["session_id"])
        op.create_index("ix_session_tags_tag_id", "session_tags", ["tag_id"])


def downgrade() -> None:
    existing = _existing_tables()
    # Drop children before parents.
    for name in reversed(_TABLES_IN_DEP_ORDER):
        if name in existing:
            op.drop_table(name)

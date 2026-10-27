"""PDF drawings: drawing fragments, drawing_fact audit table, part identity grouping

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27

Data note: part records are now keyed by part identity (``P-3001`` and ``3001`` are one part).
After upgrading an existing database run ``uv run cnc rebuild`` once to regroup stored
fragments into records; nothing needs re-ingesting.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingest_run", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "ingest_run",
        sa.Column("extraction", sa.String(length=16), server_default="text", nullable=False),
    )

    op.add_column(
        "part_fragment",
        sa.Column("base_key", sa.String(length=64), server_default="", nullable=False),
    )
    op.add_column(
        "part_fragment",
        sa.Column("kind", sa.String(length=16), server_default="sheet", nullable=False),
    )
    op.add_column(
        "part_fragment",
        sa.Column("drawing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_part_fragment_base_key", "part_fragment", ["base_key"])

    # Backfill the base number of every stored fragment with the same rule the app uses.
    from app.ingestion.parts import base_of

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, part_key FROM part_fragment")).all()
    for row_id, part_key in rows:
        conn.execute(
            sa.text("UPDATE part_fragment SET base_key = :b WHERE id = :i"),
            {"b": base_of(part_key), "i": row_id},
        )

    op.create_table(
        "drawing_fact",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("fact_id", sa.String(length=512), nullable=False),
        sa.Column("part_key", sa.String(length=64), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("canonical", sa.String(length=64), nullable=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("bboxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("points_to", sa.String(length=512), nullable=True),
        sa.Column(
            "text_search",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(label, '') || ' ' || coalesce(value, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["ingest_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "fact_id"),
    )
    op.create_index("ix_drawing_fact_run_id", "drawing_fact", ["run_id"])
    op.create_index("ix_drawing_fact_part_key", "drawing_fact", ["part_key"])
    op.create_index(
        "ix_drawing_fact_text_search", "drawing_fact", ["text_search"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_fact_text_search", table_name="drawing_fact")
    op.drop_index("ix_drawing_fact_part_key", table_name="drawing_fact")
    op.drop_index("ix_drawing_fact_run_id", table_name="drawing_fact")
    op.drop_table("drawing_fact")
    op.drop_index("ix_part_fragment_base_key", table_name="part_fragment")
    op.drop_column("part_fragment", "drawing")
    op.drop_column("part_fragment", "kind")
    op.drop_column("part_fragment", "base_key")
    op.drop_column("ingest_run", "extraction")
    op.drop_column("ingest_run", "page_count")

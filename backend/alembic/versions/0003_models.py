"""IGES 3D models: model fragments and the model_fact audit table

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27

Data note: nothing to backfill. Ingest IGES files with ``uv run cnc ingest``; existing records
gain their models and three-way cross-checks when those files arrive.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "part_fragment", sa.Column("model", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_table(
        "model_fact",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("fact_id", sa.String(length=512), nullable=False),
        sa.Column("part_key", sa.String(length=64), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("canonical", sa.String(length=64), nullable=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column(
            "text_search",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(label, '') || ' ' || coalesce(value, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["ingest_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "fact_id"),
    )
    op.create_index("ix_model_fact_run_id", "model_fact", ["run_id"])
    op.create_index("ix_model_fact_part_key", "model_fact", ["part_key"])
    op.create_index(
        "ix_model_fact_text_search", "model_fact", ["text_search"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_model_fact_text_search", table_name="model_fact")
    op.drop_index("ix_model_fact_part_key", table_name="model_fact")
    op.drop_index("ix_model_fact_run_id", table_name="model_fact")
    op.drop_table("model_fact")
    op.drop_column("part_fragment", "model")

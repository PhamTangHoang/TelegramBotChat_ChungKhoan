"""create initial application schema

Revision ID: 0001_initial
Revises:
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "exchange", name="uq_symbols_symbol_exchange"),
    )
    op.create_table(
        "market_candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol_id", sa.Integer(), sa.ForeignKey("symbols.id"), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("adjusted_close", sa.Numeric(20, 6)),
        sa.Column("price_basis", sa.String(32), nullable=False, server_default="RAW_OHLCV"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True)),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("symbol_id", "trading_date", name="uq_market_candles_symbol_date"),
    )
    op.create_index(
        "ix_market_candles_symbol_date", "market_candles", ["symbol_id", "trading_date"]
    )
    op.create_table(
        "market_indices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("index_code", sa.String(32), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True)),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("index_code", "trading_date", name="uq_market_indices_code_date"),
    )
    op.create_index("ix_market_indices_code_date", "market_indices", ["index_code", "trading_date"])
    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("url", name="uq_news_url"),
    )
    op.create_index("ix_news_published_at", "news", ["published_at"])
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_snapshot", json_type, nullable=False),
        sa.Column("indicator_snapshot", json_type, nullable=False),
        sa.Column("rule_result", json_type, nullable=False),
        sa.Column("data_provenance", json_type, nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("data_schema_version", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("llm_response", json_type),
        sa.Column("rule_signal", sa.String(32), nullable=False),
        sa.Column("explanation_conflict", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("analysis_kind", sa.String(16), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_analysis_runs_symbol_as_of", "analysis_runs", ["symbol", "exchange", "as_of"]
    )
    op.create_index(
        "ix_analysis_runs_final", "analysis_runs", ["symbol", "trading_date", "is_final"]
    )
    op.create_table(
        "scheduler_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scheduler_runs")
    op.drop_index("ix_analysis_runs_final", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_symbol_as_of", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_news_published_at", table_name="news")
    op.drop_table("news")
    op.drop_index("ix_market_indices_code_date", table_name="market_indices")
    op.drop_table("market_indices")
    op.drop_index("ix_market_candles_symbol_date", table_name="market_candles")
    op.drop_table("market_candles")
    op.drop_table("symbols")

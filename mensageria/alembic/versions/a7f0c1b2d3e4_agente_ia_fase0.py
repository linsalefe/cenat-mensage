"""agente ia fase0: channels.agent_enabled + agent_products/sessions/followups/turn_logs

Revision ID: a7f0c1b2d3e4
Revises: b7e41c9d2a10
Create Date: 2026-07-29

Aditiva. `channels.agent_enabled` nasce NOT NULL DEFAULT false → nenhum canal
existente passa a ser processado pelo agente sem ativação explícita. As 4 tabelas
novas são independentes; nada do comportamento atual muda.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a7f0c1b2d3e4"
down_revision: Union[str, None] = "b7e41c9d2a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    # --- interruptor mestre do agente (default False) ---
    op.add_column(
        "channels",
        sa.Column(
            "agent_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    # --- catálogo de produtos (fonte da verdade de preços/lotes) ---
    op.create_table(
        "agent_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("doity_event_id", sa.Integer(), nullable=True),
        sa.Column("event_dates", sa.String(length=120), nullable=True),
        sa.Column("checkout_url", sa.String(length=500), nullable=False),
        sa.Column("submission_url", sa.String(length=500), nullable=True),
        sa.Column("landing_url", sa.String(length=500), nullable=True),
        sa.Column("faq", JSONB(), server_default="[]", nullable=False),
        sa.Column("schedule", JSONB(), server_default="[]", nullable=False),
        sa.Column("tickets", JSONB(), server_default="[]", nullable=False),
        sa.Column("policies", JSONB(), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("synced_from_doity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_products_doity_event_id", "agent_products", ["doity_event_id"], schema=SCHEMA
    )

    # --- sessões (máquina de estado durável por contato) ---
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contact_wa_id", sa.String(length=100), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("product_slug", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("history", JSONB(), server_default="[]", nullable=False),
        sa.Column("history_summary", sa.Text(), nullable=True),
        sa.Column("turns_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["channel_id"], [f"{SCHEMA}.channels.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_sessions_contact_wa_id", "agent_sessions", ["contact_wa_id"], schema=SCHEMA
    )

    # --- follow-ups (cadência) ---
    op.create_table(
        "agent_followups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("contact_wa_id", sa.String(length=100), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=True),
        sa.Column("payload", JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{SCHEMA}.agent_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_followups_contact_wa_id", "agent_followups", ["contact_wa_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_agent_followups_run_at", "agent_followups", ["run_at"], schema=SCHEMA
    )

    # --- auditoria de turnos (eval/custo) ---
    op.create_table(
        "agent_turn_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_calls", JSONB(), nullable=True),
        sa.Column("guardrail", JSONB(), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_turn_logs_session_id", "agent_turn_logs", ["session_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_agent_turn_logs_session_id", "agent_turn_logs", schema=SCHEMA)
    op.drop_table("agent_turn_logs", schema=SCHEMA)
    op.drop_index("ix_agent_followups_run_at", "agent_followups", schema=SCHEMA)
    op.drop_index("ix_agent_followups_contact_wa_id", "agent_followups", schema=SCHEMA)
    op.drop_table("agent_followups", schema=SCHEMA)
    op.drop_index("ix_agent_sessions_contact_wa_id", "agent_sessions", schema=SCHEMA)
    op.drop_table("agent_sessions", schema=SCHEMA)
    op.drop_index("ix_agent_products_doity_event_id", "agent_products", schema=SCHEMA)
    op.drop_table("agent_products", schema=SCHEMA)
    op.drop_column("channels", "agent_enabled", schema=SCHEMA)

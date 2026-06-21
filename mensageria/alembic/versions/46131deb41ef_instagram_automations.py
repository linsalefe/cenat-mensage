"""instagram automations

Revision ID: 46131deb41ef
Revises: 24ec9c9e697e
Create Date: 2026-06-20 13:05:01.272297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '46131deb41ef'
down_revision: Union[str, None] = '24ec9c9e697e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.create_table(
        "instagram_automations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("action_config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("once_per_contact", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], [f"{SCHEMA}.channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_mensageria_instagram_automations_channel_id"),
        "instagram_automations",
        ["channel_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "instagram_automation_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("trigger_ref", sa.String(length=255), nullable=False),
        sa.Column("contact_wa_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["automation_id"], [f"{SCHEMA}.instagram_automations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], [f"{SCHEMA}.channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_mensageria_instagram_automation_executions_automation_id"),
        "instagram_automation_executions",
        ["automation_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_mensageria_instagram_automation_executions_trigger_ref"),
        "instagram_automation_executions",
        ["trigger_ref"],
        unique=False,
        schema=SCHEMA,
    )
    # Rede de dedup: no máximo UMA execução "sent" por (automação, trigger_ref).
    op.create_index(
        "uq_ig_autoexec_sent",
        "instagram_automation_executions",
        ["automation_id", "trigger_ref"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'sent'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ig_autoexec_sent", table_name="instagram_automation_executions", schema=SCHEMA)
    op.drop_index(
        op.f("ix_mensageria_instagram_automation_executions_trigger_ref"),
        table_name="instagram_automation_executions",
        schema=SCHEMA,
    )
    op.drop_index(
        op.f("ix_mensageria_instagram_automation_executions_automation_id"),
        table_name="instagram_automation_executions",
        schema=SCHEMA,
    )
    op.drop_table("instagram_automation_executions", schema=SCHEMA)
    op.drop_index(
        op.f("ix_mensageria_instagram_automations_channel_id"),
        table_name="instagram_automations",
        schema=SCHEMA,
    )
    op.drop_table("instagram_automations", schema=SCHEMA)

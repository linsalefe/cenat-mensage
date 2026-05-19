"""add_campaign_runs

Revision ID: f4be31f57134
Revises: 4a3a0aa2188a
Create Date: 2026-05-19 02:36:16.448629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4be31f57134'
down_revision: Union[str, None] = '4a3a0aa2188a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flow_id", sa.Integer(), sa.ForeignKey("mensageria.chatbot_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("mensageria.channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("list_id", sa.Integer(), sa.ForeignKey("mensageria.contact_lists.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_targets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_interval_seconds", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("mensageria.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        schema="mensageria",
    )
    op.add_column(
        "chatbot_sessions",
        sa.Column("campaign_run_id", sa.Integer(), sa.ForeignKey("mensageria.campaign_runs.id", ondelete="SET NULL"), nullable=True),
        schema="mensageria",
    )
    op.create_index(
        "ix_chatbot_sessions_campaign_run_id",
        "chatbot_sessions",
        ["campaign_run_id"],
        schema="mensageria",
    )


def downgrade() -> None:
    op.drop_index("ix_chatbot_sessions_campaign_run_id", table_name="chatbot_sessions", schema="mensageria")
    op.drop_column("chatbot_sessions", "campaign_run_id", schema="mensageria")
    op.drop_table("campaign_runs", schema="mensageria")

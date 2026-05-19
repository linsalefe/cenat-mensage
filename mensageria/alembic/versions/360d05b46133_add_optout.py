"""add_optout

Revision ID: 360d05b46133
Revises: f4be31f57134
Create Date: 2026-05-19 02:47:33.069523

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '360d05b46133'
down_revision: Union[str, None] = 'f4be31f57134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_KEYWORDS = ["sair", "parar", "cancelar", "remover", "stop", "unsubscribe"]


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("opt_out_keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="mensageria",
    )
    op.add_column(
        "contacts",
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default="false"),
        schema="mensageria",
    )
    op.add_column(
        "contacts",
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        schema="mensageria",
    )
    op.execute(
        f"UPDATE mensageria.channels SET opt_out_keywords = '{json.dumps(DEFAULT_KEYWORDS)}'::jsonb WHERE opt_out_keywords IS NULL"
    )


def downgrade() -> None:
    op.drop_column("contacts", "opted_out_at", schema="mensageria")
    op.drop_column("contacts", "opted_out", schema="mensageria")
    op.drop_column("channels", "opt_out_keywords", schema="mensageria")

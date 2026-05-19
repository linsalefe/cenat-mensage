"""add_meta_templates

Revision ID: 6fd07e6102d4
Revises: 6142947c97aa
Create Date: 2026-05-19 01:53:39.757288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6fd07e6102d4'
down_revision: Union[str, None] = '6142947c97aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meta_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("mensageria.channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="pt_BR"),
        sa.Column("category", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("meta_template_id", sa.String(50), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("channel_id", "name", "language", name="uq_meta_template_channel_name_lang"),
        schema="mensageria",
    )
    op.create_index("ix_meta_templates_channel_id", "meta_templates", ["channel_id"], schema="mensageria")


def downgrade() -> None:
    op.drop_index("ix_meta_templates_channel_id", table_name="meta_templates", schema="mensageria")
    op.drop_table("meta_templates", schema="mensageria")

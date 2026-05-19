"""add_contact_lists

Revision ID: d9b069e47ad3
Revises: 6fd07e6102d4
Create Date: 2026-05-19 02:05:05.426673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd9b069e47ad3'
down_revision: Union[str, None] = '6fd07e6102d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("mensageria.channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("mensageria.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="mensageria",
    )
    op.create_table(
        "contact_list_members",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("list_id", sa.Integer(), sa.ForeignKey("mensageria.contact_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wa_id", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("custom_vars", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="{}"),
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("list_id", "wa_id", name="uq_contact_list_member_list_wa"),
        schema="mensageria",
    )
    op.create_index("ix_contact_list_members_list_id", "contact_list_members", ["list_id"], schema="mensageria")
    op.create_index("ix_contact_list_members_wa_id", "contact_list_members", ["wa_id"], schema="mensageria")


def downgrade() -> None:
    op.drop_index("ix_contact_list_members_wa_id", table_name="contact_list_members", schema="mensageria")
    op.drop_index("ix_contact_list_members_list_id", table_name="contact_list_members", schema="mensageria")
    op.drop_table("contact_list_members", schema="mensageria")
    op.drop_table("contact_lists", schema="mensageria")

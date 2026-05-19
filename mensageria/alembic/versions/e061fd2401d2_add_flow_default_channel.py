"""add_flow_default_channel

Revision ID: e061fd2401d2
Revises: 360d05b46133
Create Date: 2026-05-19 03:37:04.608665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e061fd2401d2'
down_revision: Union[str, None] = '360d05b46133'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chatbot_flows",
        sa.Column("default_channel_id", sa.Integer(), nullable=True),
        schema="mensageria",
    )
    op.create_foreign_key(
        "fk_chatbot_flows_default_channel",
        "chatbot_flows", "channels",
        ["default_channel_id"], ["id"],
        source_schema="mensageria", referent_schema="mensageria",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_chatbot_flows_default_channel",
        "chatbot_flows",
        schema="mensageria",
        type_="foreignkey",
    )
    op.drop_column("chatbot_flows", "default_channel_id", schema="mensageria")

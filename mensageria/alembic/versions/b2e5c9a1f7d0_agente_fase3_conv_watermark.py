"""agente fase3: agent_products.conv_synced_at (watermark do polling de conversão)

Revision ID: b2e5c9a1f7d0
Revises: a7f0c1b2d3e4
Create Date: 2026-07-29

Aditiva. Cursor de `data_atualizacao` do polling de participantes (Fase 3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2e5c9a1f7d0"
down_revision: Union[str, None] = "a7f0c1b2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.add_column(
        "agent_products",
        sa.Column("conv_synced_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("agent_products", "conv_synced_at", schema=SCHEMA)

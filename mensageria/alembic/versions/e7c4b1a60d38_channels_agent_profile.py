"""channels.agent_profile: perfil do agente por canal (vendas | atendimento)

Revision ID: e7c4b1a60d38
Revises: d4a1e7b3c920
Create Date: 2026-10-19

Puramente aditiva. Uma coluna, NOT NULL com server_default 'vendas', então as
linhas existentes (canais 6, 9 e 11) já nascem classificadas como o agente que
roda hoje — o de vendas do canal 6. Nenhum backfill necessário e o código
antigo ignora a coluna.

Por que uma coluna e não uma setting: o perfil é propriedade do CANAL, não do
processo. A trava de canal da Nat (`AGENT_ATENDIMENTO_CHANNEL_ID`) ainda é
setting, mas o perfil precisa ser consultável junto do canal em
`agent_should_handle` e nos workers, que resolvem o canal pelo contato.

Sem CHECK constraint, por consistência com `operation_mode` (mesma forma: string
curta com valores acordados no código). Valor desconhecido faz
`agent_should_handle` devolver False — fail-closed, o agente não responde.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7c4b1a60d38"
down_revision: Union[str, None] = "d4a1e7b3c920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column(
            "agent_profile",
            sa.String(20),
            nullable=False,
            server_default="vendas",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("channels", "agent_profile", schema=SCHEMA)

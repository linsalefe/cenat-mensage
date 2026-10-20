"""messages.transcript: texto do áudio transcrito (voice note → texto)

Revision ID: f1b9d3e52a74
Revises: e7c4b1a60d38
Create Date: 2026-10-20

Puramente aditiva. Coluna nullable, sem default: `NULL` = áudio ainda não
transcrito (ou mensagem que não é áudio), distinto de string vazia.

Por que persistir em vez de transcrever a cada leitura:
- custo. A transcrição é cobrada por minuto de áudio; reprocessar o mesmo
  voice note (retry do webhook, turno que estourou e repetiu o lote) pagaria
  de novo;
- latência. O turno seguinte reaproveita em vez de esperar a rede;
- o inbox pode mostrar o texto do áudio para o atendente — ganho que vale
  sozinho, independente do agente.

Fica em `messages` e não numa tabela à parte porque é 1:1 com a mensagem e é
lido exatamente junto dela (`handler._display`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1b9d3e52a74"
down_revision: Union[str, None] = "e7c4b1a60d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("transcript", sa.Text(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("messages", "transcript", schema=SCHEMA)

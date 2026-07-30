"""agente pós: agent_products.kind + promo + info; checkout_url nullable

Revision ID: c3f8d2a94b61
Revises: b2e5c9a1f7d0
Create Date: 2026-07-30

Aditiva, com uma exceção controlada: relaxa `checkout_url` para nullable.
Pós-graduação não tem checkout (a entrada é por processo seletivo), então a
coluna não pode seguir NOT NULL. Relaxar NOT NULL é compatível com o código
antigo — ele sempre escreve um valor nos congressos.

- `kind`: 'congresso' | 'pos'. NOT NULL com server_default 'congresso', então
  as linhas existentes (os 2 congressos) já nascem classificadas certo.
- `promo`: JSONB nullable {descricao, valido_de, valido_ate, cupom, condicao}.
  Nullable de propósito: `NULL` = sem promoção, distinto de `{}`.
- `info`: JSONB dos campos estruturados da pós (carga horária, aulas, módulos,
  coordenação, investimento...). Congresso segue usando tickets/policies.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3f8d2a94b61"
down_revision: Union[str, None] = "b2e5c9a1f7d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.add_column(
        "agent_products",
        sa.Column(
            "kind",
            sa.String(20),
            nullable=False,
            server_default="congresso",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "agent_products",
        sa.Column("promo", postgresql.JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "agent_products",
        sa.Column(
            "info",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_products_kind", "agent_products", ["kind"], schema=SCHEMA
    )
    # Pós não tem checkout — a inscrição passa por processo seletivo.
    op.alter_column(
        "agent_products",
        "checkout_url",
        existing_type=sa.String(500),
        nullable=True,
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Só volta a NOT NULL se não houver linha sem checkout_url (as pós teriam
    # que sair antes) — senão o ALTER falha e é isso que queremos saber.
    op.alter_column(
        "agent_products",
        "checkout_url",
        existing_type=sa.String(500),
        nullable=False,
        schema=SCHEMA,
    )
    op.drop_index("ix_agent_products_kind", "agent_products", schema=SCHEMA)
    op.drop_column("agent_products", "info", schema=SCHEMA)
    op.drop_column("agent_products", "promo", schema=SCHEMA)
    op.drop_column("agent_products", "kind", schema=SCHEMA)

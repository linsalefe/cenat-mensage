"""widen wa_id for instagram igsid

Revision ID: 24ec9c9e697e
Revises: e061fd2401d2
Create Date: 2026-06-20 11:59:56.509031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24ec9c9e697e'
down_revision: Union[str, None] = 'e061fd2401d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = "mensageria"


def upgrade() -> None:
    # O IGSID prefixado com ``ig:`` (ex.: ``ig:17841400000000000``) precisa caber em
    # contacts.wa_id e na FK messages.contact_wa_id. O histórico de migrations criou
    # essas colunas como VARCHAR(20), pequeno demais até para os JIDs de grupo (23 chars)
    # já em uso; o banco live foi alargado à mão para VARCHAR(100) sem migration. Aqui
    # convergimos o histórico para 100 (mesmo tamanho dos demais *_wa_id do schema),
    # eliminando o drift e garantindo espaço para o Instagram. Em banco já 100 é no-op.
    op.alter_column(
        "contacts",
        "wa_id",
        type_=sa.String(100),
        existing_type=sa.String(20),
        existing_nullable=False,
        schema=SCHEMA,
    )
    op.alter_column(
        "messages",
        "contact_wa_id",
        type_=sa.String(100),
        existing_type=sa.String(20),
        existing_nullable=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "messages",
        "contact_wa_id",
        type_=sa.String(20),
        existing_type=sa.String(100),
        existing_nullable=False,
        schema=SCHEMA,
    )
    op.alter_column(
        "contacts",
        "wa_id",
        type_=sa.String(20),
        existing_type=sa.String(100),
        existing_nullable=False,
        schema=SCHEMA,
    )

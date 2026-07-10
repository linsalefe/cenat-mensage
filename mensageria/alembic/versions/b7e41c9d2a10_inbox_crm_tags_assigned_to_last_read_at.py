"""inbox crm: contact_tags, contact_tag_links, contacts.assigned_to, contacts.last_read_at

Revision ID: b7e41c9d2a10
Revises: 008340c06ff9
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7e41c9d2a10"
down_revision: Union[str, None] = "008340c06ff9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    op.create_table(
        "contact_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=20), server_default="blue", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema=SCHEMA,
    )
    op.create_table(
        "contact_tag_links",
        # contacts.id é BigInteger; users.id é Integer. Tipos batem com models.py.
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"], [f"{SCHEMA}.contacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], [f"{SCHEMA}.contact_tags.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("contact_id", "tag_id"),
        schema=SCHEMA,
    )
    op.add_column(
        "contacts",
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_contacts_assigned_to_users",
        "contacts",
        "users",
        ["assigned_to"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    # DateTime SEM timezone de propósito: Message.timestamp é naive em horário de
    # São Paulo (ver app/messaging/persistence.py e app/meta/parser.py). Usar
    # timestamptz aqui faria a comparação de não-lidas errar por 3 horas.
    op.add_column(
        "contacts",
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("contacts", "last_read_at", schema=SCHEMA)
    op.drop_constraint(
        "fk_contacts_assigned_to_users", "contacts", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("contacts", "assigned_to", schema=SCHEMA)
    op.drop_table("contact_tag_links", schema=SCHEMA)
    op.drop_table("contact_tags", schema=SCHEMA)

"""crm pipeline

Revision ID: 4c61c707a6ec
Revises: 46131deb41ef
Create Date: 2026-06-20 14:49:53.967248

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4c61c707a6ec'
down_revision: Union[str, None] = '46131deb41ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"

DEFAULT_COLUMNS = [
    {"key": "novo", "label": "Novos Contatos", "color": "#10b981", "order": 0},
    {"key": "em_contato", "label": "Em Contato", "color": "#f59e0b", "order": 1},
    {"key": "qualificado", "label": "Qualificados", "color": "#8b5cf6", "order": 2},
    {"key": "negociando", "label": "Negociando", "color": "#06b6d4", "order": 3},
    {"key": "convertido", "label": "Convertido", "color": "#22c55e", "order": 4},
    {"key": "perdido", "label": "Perdido", "color": "#ef4444", "order": 5},
]


def upgrade() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.add_column(
        "contacts",
        sa.Column("pipeline_id", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_contacts_pipeline_id", "contacts", "pipelines",
        ["pipeline_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )
    op.add_column(
        "channels",
        sa.Column("default_pipeline_id", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_channels_default_pipeline_id", "channels", "pipelines",
        ["default_pipeline_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )

    # Seed: 1 pipeline default + backfill (sem deixar contato/canal órfão).
    cols_json = json.dumps(DEFAULT_COLUMNS)
    conn = op.get_bind()
    pid = conn.execute(
        sa.text(
            f"INSERT INTO {SCHEMA}.pipelines (name, columns, is_default, \"order\") "
            f"VALUES ('Funil de Vendas', :cols ::jsonb, true, 0) RETURNING id"
        ),
        {"cols": cols_json},
    ).scalar()
    conn.execute(sa.text(f"UPDATE {SCHEMA}.contacts SET pipeline_id = :pid WHERE pipeline_id IS NULL"), {"pid": pid})
    conn.execute(sa.text(f"UPDATE {SCHEMA}.channels SET default_pipeline_id = :pid WHERE default_pipeline_id IS NULL"), {"pid": pid})
    # Contatos legados sem lead_status válido caem na 1ª coluna.
    keys_sql = ", ".join("'%s'" % c["key"] for c in DEFAULT_COLUMNS)
    conn.execute(
        sa.text(
            f"UPDATE {SCHEMA}.contacts SET lead_status = 'novo' "
            f"WHERE lead_status IS NULL OR lead_status NOT IN ({keys_sql})"
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_channels_default_pipeline_id", "channels", schema=SCHEMA, type_="foreignkey")
    op.drop_column("channels", "default_pipeline_id", schema=SCHEMA)
    op.drop_constraint("fk_contacts_pipeline_id", "contacts", schema=SCHEMA, type_="foreignkey")
    op.drop_column("contacts", "pipeline_id", schema=SCHEMA)
    op.drop_table("pipelines", schema=SCHEMA)

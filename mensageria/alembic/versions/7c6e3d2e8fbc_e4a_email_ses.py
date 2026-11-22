"""E4a: canal de e-mail via Amazon SES (email_jobs/messages/suppressions + e-mail em contatos e listas)

Revision ID: 7c6e3d2e8fbc
Revises: f1b9d3e52a74
Create Date: 2026-11-22

Aditiva. Nenhuma coluna é renomeada ou removida. A ÚNICA alteração em coluna
existente é relaxar `contact_list_members.wa_id` para nullable (membro só-e-mail),
protegida por um CHECK que exige telefone OU e-mail. Quem lê lista para WhatsApp
(broadcast/audience_resolver, campaign/worker) passa a filtrar `wa_id IS NOT NULL`.

- contacts.email (+ índice em lower(email)), email_opted_out, email_opted_out_at
- contact_list_members.email (+ único parcial (list_id, lower(email)))
- email_jobs, email_messages, email_suppressions (todas timestamptz)

Downgrade restaura o NOT NULL de wa_id SÓ se não houver membro só-e-mail — se
houver, levanta erro em vez de apagar dados.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "7c6e3d2e8fbc"
down_revision: Union[str, None] = "f1b9d3e52a74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mensageria"


def upgrade() -> None:
    # --- contacts ---------------------------------------------------------
    op.add_column("contacts", sa.Column("email", sa.String(255), nullable=True), schema=SCHEMA)
    op.add_column(
        "contacts",
        sa.Column("email_opted_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema=SCHEMA,
    )
    op.add_column(
        "contacts",
        sa.Column("email_opted_out_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_contacts_email_lower", "contacts", [sa.text("lower(email)")], schema=SCHEMA
    )

    # --- contact_list_members --------------------------------------------
    op.add_column(
        "contact_list_members", sa.Column("email", sa.String(255), nullable=True), schema=SCHEMA
    )
    op.alter_column(
        "contact_list_members", "wa_id", existing_type=sa.String(20), nullable=True, schema=SCHEMA
    )
    op.create_check_constraint(
        "ck_contact_list_member_wa_or_email",
        "contact_list_members",
        "wa_id IS NOT NULL OR email IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_index(
        "uq_contact_list_member_list_email",
        "contact_list_members",
        ["list_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
        schema=SCHEMA,
    )

    # --- email_jobs -------------------------------------------------------
    op.create_table(
        "email_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("audience_type", sa.String(30), nullable=False),
        sa.Column("audience_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_targets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    # --- email_messages ---------------------------------------------------
    op.create_table(
        "email_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.email_jobs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("to_email", sa.String(255), nullable=False),
        sa.Column("to_name", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(998), nullable=True),
        sa.Column("ses_message_id", sa.String(255), nullable=True, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_email_messages_job_id", "email_messages", ["job_id"], schema=SCHEMA)
    op.create_index("ix_email_messages_to_email", "email_messages", ["to_email"], schema=SCHEMA)
    op.create_index("ix_email_messages_sent_at", "email_messages", ["sent_at"], schema=SCHEMA)

    # --- email_suppressions -----------------------------------------------
    op.create_table(
        "email_suppressions",
        sa.Column("email", sa.String(255), primary_key=True),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    bind = op.get_bind()
    so_email = bind.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.contact_list_members WHERE wa_id IS NULL")
    ).scalar()
    if so_email:
        raise RuntimeError(
            f"{so_email} membro(s) de lista sem wa_id (só e-mail). Remova-os antes do "
            "downgrade — restaurar o NOT NULL de wa_id falharia/apagaria dados."
        )

    op.drop_table("email_suppressions", schema=SCHEMA)
    op.drop_index("ix_email_messages_sent_at", table_name="email_messages", schema=SCHEMA)
    op.drop_index("ix_email_messages_to_email", table_name="email_messages", schema=SCHEMA)
    op.drop_index("ix_email_messages_job_id", table_name="email_messages", schema=SCHEMA)
    op.drop_table("email_messages", schema=SCHEMA)
    op.drop_table("email_jobs", schema=SCHEMA)

    op.drop_index(
        "uq_contact_list_member_list_email", table_name="contact_list_members", schema=SCHEMA
    )
    op.drop_constraint(
        "ck_contact_list_member_wa_or_email", "contact_list_members", type_="check", schema=SCHEMA
    )
    op.alter_column(
        "contact_list_members", "wa_id", existing_type=sa.String(20), nullable=False, schema=SCHEMA
    )
    op.drop_column("contact_list_members", "email", schema=SCHEMA)

    op.drop_index("ix_contacts_email_lower", table_name="contacts", schema=SCHEMA)
    op.drop_column("contacts", "email_opted_out_at", schema=SCHEMA)
    op.drop_column("contacts", "email_opted_out", schema=SCHEMA)
    op.drop_column("contacts", "email", schema=SCHEMA)

"""s1: atribuicao ctwa em contacts + tabela conversion_events

Revision ID: 008340c06ff9
Revises: 4c61c707a6ec
Create Date: 2026-06-21 12:50:04.604342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008340c06ff9'
down_revision: Union[str, None] = '4c61c707a6ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # S1 — atribuição CTWA. Apenas mudanças deste sprint; renomes/ajustes de
    # índices não relacionados que o autogenerate detectou (drift pré-existente
    # de naming_convention em chatbot_sessions/contact_list_members/meta_templates)
    # foram removidos de propósito — não fazem parte da S1.
    op.add_column('contacts', sa.Column('source', sa.String(length=30), nullable=True), schema='mensageria')
    op.add_column('contacts', sa.Column('ctwa_clid', sa.String(length=512), nullable=True), schema='mensageria')
    op.add_column('contacts', sa.Column('ctwa_clid_at', sa.DateTime(timezone=True), nullable=True), schema='mensageria')
    op.add_column('contacts', sa.Column('ad_id', sa.String(length=64), nullable=True), schema='mensageria')
    op.add_column('contacts', sa.Column('ad_headline', sa.String(length=255), nullable=True), schema='mensageria')
    op.add_column('contacts', sa.Column('ad_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='mensageria')
    op.create_index(op.f('ix_mensageria_contacts_ctwa_clid'), 'contacts', ['ctwa_clid'], unique=False, schema='mensageria')

    op.create_table('conversion_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('contact_wa_id', sa.String(length=100), nullable=False),
    sa.Column('event_name', sa.String(length=40), nullable=False),
    sa.Column('value', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('ctwa_clid', sa.String(length=512), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('meta_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='mensageria'
    )
    op.create_index(op.f('ix_mensageria_conversion_events_contact_wa_id'), 'conversion_events', ['contact_wa_id'], unique=False, schema='mensageria')
    op.create_index('uq_conv_event_sent', 'conversion_events', ['contact_wa_id', 'event_name'], unique=True, schema='mensageria', postgresql_where=sa.text("status = 'sent'"))


def downgrade() -> None:
    op.drop_index('uq_conv_event_sent', table_name='conversion_events', schema='mensageria', postgresql_where=sa.text("status = 'sent'"))
    op.drop_index(op.f('ix_mensageria_conversion_events_contact_wa_id'), table_name='conversion_events', schema='mensageria')
    op.drop_table('conversion_events', schema='mensageria')

    op.drop_index(op.f('ix_mensageria_contacts_ctwa_clid'), table_name='contacts', schema='mensageria')
    op.drop_column('contacts', 'ad_payload', schema='mensageria')
    op.drop_column('contacts', 'ad_headline', schema='mensageria')
    op.drop_column('contacts', 'ad_id', schema='mensageria')
    op.drop_column('contacts', 'ctwa_clid_at', schema='mensageria')
    op.drop_column('contacts', 'ctwa_clid', schema='mensageria')
    op.drop_column('contacts', 'source', schema='mensageria')

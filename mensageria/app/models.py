"""Modelos SQLAlchemy do backend mensageria (mono-tenant, schema `mensageria`).

Portado de backend/app/models.py do EduFlow Hub, com as seguintes simplificações:
- REMOVIDO `tenant_id` e relacionamentos com Tenant (mono-tenant CENAT).
- REMOVIDAS FKs para modelos não portados: User, Pipeline, Tag, LandingPage,
  FormSubmission, KnowledgeDocument, AIConfig, CallLog, AIConversationSummary,
  LeadAgentContext, Subscription, Task.
- Todos os modelos vivem no schema `mensageria` (isolado das tabelas Prisma
  da Evolution API em `public`).
- Campos de negócio (JSONB graph/variables, operation_mode, is_published,
  ai_memory etc.) preservados integralmente.

Decisão: `Contact.wa_id` passa a ser `unique=True` — em mono-tenant o identificador
natural do contato é o próprio wa_id (no multi-tenant original, o unique real era
a tupla `(tenant_id, wa_id)`). Necessário porque Message.contact_wa_id aponta para
contacts.wa_id e Postgres exige unique constraint no alvo da FK.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base

SCHEMA = "mensageria"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login_at = Column(DateTime, nullable=True)


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=True)
    phone_number_id = Column(String(50), nullable=True)
    whatsapp_token = Column(Text, nullable=True)
    waba_id = Column(String(50))
    type = Column(String(20), default="whatsapp")
    provider = Column(String(20), default="official")
    instance_name = Column(String(100), nullable=True)
    instance_token = Column(Text, nullable=True)
    page_id = Column(String(50), nullable=True)
    instagram_id = Column(String(50), nullable=True)
    access_token = Column(Text, nullable=True)
    is_connected = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    operation_mode = Column(String(20), nullable=False, default="ai")  # ai | chatbot | none
    active_chatbot_flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.chatbot_flows.id", ondelete="SET NULL"),
        nullable=True,
    )

    contacts = relationship("Contact", back_populates="channel")
    messages = relationship("Message", back_populates="channel")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wa_id = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=True)
    profile_picture_url = Column(String, nullable=True)
    lead_status = Column(String(30), default="novo")
    notes = Column(Text, nullable=True)
    ai_active = Column(Boolean, default=False)
    last_inbound_at = Column(DateTime, nullable=True)
    reengagement_count = Column(Integer, default=0)
    channel_id = Column(Integer, ForeignKey(f"{SCHEMA}.channels.id"))
    deal_value = Column(Numeric(10, 2), nullable=True, default=0)
    is_group = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    ai_memory = Column(JSONB, nullable=True, server_default="{}")
    ai_memory_updated_at = Column(DateTime(timezone=True), nullable=True)

    messages = relationship("Message", back_populates="contact")
    channel = relationship("Channel", back_populates="contacts")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wa_message_id = Column(String(255), unique=True, nullable=False, index=True)
    contact_wa_id = Column(
        String(20),
        ForeignKey(f"{SCHEMA}.contacts.wa_id"),
        nullable=False,
        index=True,
    )
    channel_id = Column(Integer, ForeignKey(f"{SCHEMA}.channels.id"))
    direction = Column(String(10), nullable=False)
    message_type = Column(String(20), nullable=False)
    content = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    status = Column(String(20), default="received")
    sent_by_ai = Column(Boolean, default=False)
    sender_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    contact = relationship("Contact", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")


class AutomationFlow(Base):
    __tablename__ = "automation_flows"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    stage = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="SET NULL"),
        nullable=True,
    )


class AutomationStep(Base):
    __tablename__ = "automation_steps"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.automation_flows.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order = Column(Integer, nullable=False)
    delay_hours = Column(Integer, nullable=False, default=1)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    delay_minutes = Column(Integer, nullable=False, default=60)


class AutomationExecution(Base):
    __tablename__ = "automation_executions"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.automation_flows.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_wa_id = Column(String(100), nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    next_send_at = Column(DateTime, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class ChatbotFlow(Base):
    __tablename__ = "chatbot_flows"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Rascunho em edição (editor visual salva aqui)
    graph = Column(JSONB, nullable=False, server_default='{"nodes":[],"edges":[]}')

    # Snapshot ativo (runtime executa isto — só atualiza ao publicar)
    is_published = Column(Boolean, nullable=False, default=False)
    published_graph = Column(JSONB, nullable=True)

    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatbotSession(Base):
    __tablename__ = "chatbot_sessions"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.chatbot_flows.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_wa_id = Column(String(100), nullable=False, index=True)

    # ID do nó corrente dentro do grafo (IDs do React Flow são strings)
    current_node_id = Column(String(100), nullable=True)

    # Variáveis capturadas durante o fluxo: {"nome": "João", "cpf": "..."}
    variables = Column(JSONB, nullable=False, server_default="{}")

    # active | waiting | completed | timeout | cancelled
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime, server_default=func.now())
    last_interaction_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatbotScheduledResume(Base):
    __tablename__ = "chatbot_scheduled_resumes"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.chatbot_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_at = Column(DateTime, nullable=False)
    node_id = Column(String(100), nullable=False)
    # pending | processed | cancelled
    status = Column(String(20), nullable=False, default="pending")
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# Broadcast (Fase 5.1) — jobs, logs e assets de mídia
# ============================================================
class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    # flow_id nullable: permite broadcast ad-hoc sem flow associado
    flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.chatbot_flows.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    # all_groups | selected_groups | contacts_tag | csv | single_contact
    audience_type = Column(String(30), nullable=False)
    # Ex: {"group_ids": ["123@g.us"]} | {"instance_name": "mkt"} |
    #     {"contacts": [{"wa_id": "55...", "name": "..."}]}
    audience_spec = Column(JSONB, nullable=False, server_default="{}")
    # Ex: {"text": "Olá {nome}", "media_url": "/api/media/5",
    #      "media_type": "image", "caption": "..."}
    message_payload = Column(JSONB, nullable=False, server_default="{}")
    interval_seconds = Column(Integer, nullable=False, default=5)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    # Placeholder pra recorrência (Fase futura — não usado agora)
    recurrence = Column(JSONB, nullable=True)
    # pending | running | completed | failed | cancelled
    status = Column(String(20), nullable=False, default="pending")
    total_targets = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message = Column(Text, nullable=True)


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.broadcast_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # grupo (@g.us) ou contato (@s.whatsapp.net)
    target_wa_id = Column(String(100), nullable=False)
    target_name = Column(String(255), nullable=True)
    # sent | error | skipped
    status = Column(String(20), nullable=False)
    error_detail = Column(Text, nullable=True)
    sent_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    # image | audio | video | document
    media_type = Column(String(20), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_by = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

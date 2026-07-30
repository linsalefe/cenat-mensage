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
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
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
    default_pipeline_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.pipelines.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_connected = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    operation_mode = Column(String(20), nullable=False, default="ai")  # ai | chatbot | none
    active_chatbot_flow_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.chatbot_flows.id", ondelete="SET NULL"),
        nullable=True,
    )
    opt_out_keywords = Column(JSONB, nullable=True)
    # Interruptor mestre do agente de IA (PLANO_AGENTE.md §0.2). Default False:
    # o agente NUNCA processa inbound de um canal sem ativação explícita, mesmo
    # que operation_mode já seja "ai" (que é o default do model e está ligado em
    # produção — ver AUDITORIA.md). Desligar = efeito imediato, sem deploy.
    agent_enabled = Column(Boolean, nullable=False, server_default=text("false"))

    contacts = relationship("Contact", back_populates="channel")
    messages = relationship("Message", back_populates="channel")


class ContactTag(Base):
    """Etiqueta livre aplicável a contatos (inbox)."""

    __tablename__ = "contact_tags"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(20), nullable=False, default="blue")
    created_at = Column(DateTime, server_default=func.now())


contact_tag_links = Table(
    "contact_tag_links",
    Base.metadata,
    Column(
        "contact_id",
        BigInteger,
        ForeignKey(f"{SCHEMA}.contacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey(f"{SCHEMA}.contact_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema=SCHEMA,
)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wa_id = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=True)
    profile_picture_url = Column(String, nullable=True)
    lead_status = Column(String(30), default="novo")
    notes = Column(Text, nullable=True)
    ai_active = Column(Boolean, default=False)
    # SDR responsável pelo contato no inbox.
    assigned_to = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Marco de leitura do inbox. Naive em horário de São Paulo, mesma convenção
    # de Message.timestamp — comparar com timestamptz daria erro de 3h.
    last_read_at = Column(DateTime, nullable=True)
    last_inbound_at = Column(DateTime, nullable=True)
    reengagement_count = Column(Integer, default=0)
    channel_id = Column(Integer, ForeignKey(f"{SCHEMA}.channels.id"))
    pipeline_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.pipelines.id", ondelete="SET NULL"),
        nullable=True,
    )
    deal_value = Column(Numeric(10, 2), nullable=True, default=0)
    is_group = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    ai_memory = Column(JSONB, nullable=True, server_default="{}")
    ai_memory_updated_at = Column(DateTime(timezone=True), nullable=True)
    opted_out = Column(Boolean, nullable=False, default=False)
    opted_out_at = Column(DateTime(timezone=True), nullable=True)

    # Atribuição CTWA (Click-to-WhatsApp)
    source = Column(String(30), nullable=True)        # "ctwa" | "organic" | "broadcast"
    ctwa_clid = Column(String(512), nullable=True, index=True)
    ctwa_clid_at = Column(DateTime(timezone=True), nullable=True)  # início da janela 72h
    ad_id = Column(String(64), nullable=True)         # referral.source_id
    ad_headline = Column(String(255), nullable=True)
    ad_payload = Column(JSONB, nullable=True)         # referral inteiro (auditoria)

    messages = relationship("Message", back_populates="contact")
    channel = relationship("Channel", back_populates="contacts")
    # selectin: carrega as tags de todos os contatos numa segunda query, evitando
    # N+1 no list_contacts (lazy padrão nem funcionaria em sessão async).
    tags = relationship("ContactTag", secondary=contact_tag_links, lazy="selectin")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wa_message_id = Column(String(255), unique=True, nullable=False, index=True)
    contact_wa_id = Column(
        String(100),
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
    default_channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="SET NULL"),
        nullable=True,
    )
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

    campaign_run_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.campaign_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


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
    # delay_advance (default, retoma e avança) | reply_timeout (espera resposta com timeout)
    kind = Column(String(30), nullable=False, default="delay_advance")
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


class CampaignRun(Base):
    __tablename__ = "campaign_runs"
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
    list_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.contact_lists.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(20), nullable=False, default="pending")
    total_targets = Column(Integer, nullable=False, default=0)
    sessions_created = Column(Integer, nullable=False, default=0)
    sessions_completed = Column(Integer, nullable=False, default=0)
    sessions_failed = Column(Integer, nullable=False, default=0)
    batch_interval_seconds = Column(Integer, nullable=False, default=2)
    daily_limit = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message = Column(Text, nullable=True)


class ContactList(Base):
    __tablename__ = "contact_lists"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContactListMember(Base):
    __tablename__ = "contact_list_members"
    __table_args__ = (
        UniqueConstraint("list_id", "wa_id", name="uq_contact_list_member_list_wa"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    list_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.contact_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wa_id = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    custom_vars = Column(JSONB, nullable=True, server_default="{}")
    opted_out = Column(Boolean, nullable=False, default=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class MetaTemplate(Base):
    __tablename__ = "meta_templates"
    __table_args__ = (
        UniqueConstraint("channel_id", "name", "language", name="uq_meta_template_channel_name_lang"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    language = Column(String(20), nullable=False, default="pt_BR")
    category = Column(String(30), nullable=True)
    status = Column(String(30), nullable=False, default="UNKNOWN")
    components = Column(JSONB, nullable=True)
    meta_template_id = Column(String(50), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# Instagram — automações por evento (Sprint 2)
# ============================================================
class InstagramAutomation(Base):
    """Regra enxuta gatilho → condição → ação para um canal Instagram.

    Não reusa AutomationFlow/ChatbotFlow (drip/chatbot-visual): aqui é evento→ação único.
    """
    __tablename__ = "instagram_automations"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    # dm_received | comment | reaction | postback | mention | story_reply
    trigger_type = Column(String(30), nullable=False)
    # Condições (ver convenção no schema). Ex.: {"keywords":["preço"],"match":"any","media_id":null}
    trigger_config = Column(JSONB, nullable=False, server_default="{}")
    # send_dm | private_reply | public_comment_reply
    action_type = Column(String(30), nullable=False)
    # Ex.: {"text":"Oi! Te respondo no direct 👇"}
    action_config = Column(JSONB, nullable=False, server_default="{}")
    once_per_contact = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Pipeline(Base):
    """Funil de CRM com colunas customizáveis (JSON). Mono-tenant."""
    __tablename__ = "pipelines"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    # Lista de {key,label,color,order}
    columns = Column(JSONB, nullable=False, server_default="[]")
    is_default = Column(Boolean, nullable=False, default=False)
    order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstagramAutomationExecution(Base):
    """Log de execução + rede de dedup das automações de Instagram."""
    __tablename__ = "instagram_automation_executions"
    __table_args__ = (
        # Rede de segurança: no máximo UMA execução "sent" por (automação, trigger_ref).
        # Parcial (status='sent') pra ainda permitir logar tentativas error/skipped.
        Index(
            "uq_ig_autoexec_sent",
            "automation_id",
            "trigger_ref",
            unique=True,
            postgresql_where=text("status = 'sent'"),
        ),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    automation_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.instagram_automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id = Column(Integer, ForeignKey(f"{SCHEMA}.channels.id", ondelete="CASCADE"))
    # Chave de dedup: comment_id, ou ig:<igsid>, ou <mid>
    trigger_ref = Column(String(255), nullable=False, index=True)
    contact_wa_id = Column(String(100), nullable=True)
    # sent | error | skipped
    status = Column(String(20), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConversionEvent(Base):
    """Eventos de conversão CTWA (infra p/ S2/S3 — envio à CAPI da Meta).

    Reusa o padrão de dedup do InstagramAutomationExecution: índice parcial
    único garante no máximo UM evento "sent" por (contato, event_name),
    permitindo logar tentativas pending/failed/skipped.
    """
    __tablename__ = "conversion_events"
    __table_args__ = (
        Index(
            "uq_conv_event_sent",
            "contact_wa_id",
            "event_name",
            unique=True,
            postgresql_where=text("status = 'sent'"),
        ),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    contact_wa_id = Column(String(100), nullable=False, index=True)
    event_name = Column(String(40), nullable=False)   # "Purchase" | "LeadSubmitted"
    value = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="BRL")
    ctwa_clid = Column(String(512), nullable=True)    # snapshot no momento do evento
    status = Column(String(20), nullable=False, default="pending")  # pending|sent|failed|skipped
    meta_response = Column(JSONB, nullable=True)
    event_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Agente de IA de vendas (PLANO_AGENTE.md — Fase 0). Aditivo: nenhum model
# existente muda além de Channel.agent_enabled. A memória de conta do lead
# reusa Contact.ai_memory (JSONB, já existente); estas tabelas guardam catálogo
# de produtos, sessões de conversa, follow-ups e auditoria de turnos.
# ---------------------------------------------------------------------------
class AgentProduct(Base):
    """Catálogo de produtos (congressos e pós). FONTE DA VERDADE de preços/lotes/links,
    sincronizada da Doity (worker Fase 3). Regra de ouro (§7.2): nada disto vive
    no prompt — o agente sempre consulta via tool sobre esta tabela versionada.

    `kind` separa os dois modos de atendimento:
    - "congresso": venda direta, tem checkout_url e doity_event_id, preço em `tickets`.
    - "pos": o agente só INFORMA e direciona ao comercial. Sem checkout_url e sem
      doity_event_id (logo, fora do sync e do polling de conversão da Doity);
      dados estruturados em `info`, promoção com validade em `promo`.
    """

    __tablename__ = "agent_products"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(80), unique=True, nullable=False)          # "genero-2026" | "pos-tea"
    name = Column(String(255), nullable=False)
    kind = Column(String(20), nullable=False, server_default="congresso", index=True)  # congresso|pos
    doity_event_id = Column(Integer, nullable=True, index=True)
    event_dates = Column(String(120), nullable=True)                # "13 e 14/11/2026"
    # nullable: pós não tem checkout (entrada por processo seletivo)
    checkout_url = Column(String(500), nullable=True)
    submission_url = Column(String(500), nullable=True)
    landing_url = Column(String(500), nullable=True)
    faq = Column(JSONB, nullable=False, server_default="[]")         # [{q, a}]
    schedule = Column(JSONB, nullable=False, server_default="[]")    # programação por dia
    tickets = Column(JSONB, nullable=False, server_default="[]")     # [{tier, price_cents, lot_name, lot_deadline, doity_lote_id, active}]
    policies = Column(JSONB, nullable=False, server_default="{}")    # reembolso/pagamento/certificado/submissão
    # kind="pos": campos estruturados da landing (carga_horaria, aulas, inicio_aulas,
    # investimento, modulos, coordenacao, publico, avisos_extracao...)
    info = Column(JSONB, nullable=False, server_default="{}")
    # NULL = sem promoção. {descricao, valido_de, valido_ate, cupom, condicao}
    # A vigência é filtrada de forma determinística na tool (promo vencida é
    # invisível para o modelo) — ver app/agent/tools.py.
    promo = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    synced_from_doity_at = Column(DateTime(timezone=True), nullable=True)
    conv_synced_at = Column(DateTime(timezone=True), nullable=True)  # watermark do polling de conversão (Fase 3)
    version = Column(Integer, nullable=False, server_default="1")    # incrementa a cada sync com mudança
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentSession(Base):
    """Máquina de estado durável por contato (§3.1). Sem processo vivo esperando:
    o estado da conversa vive aqui e é acordado por evento (inbound/follow-up)."""

    __tablename__ = "agent_sessions"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_wa_id = Column(String(100), nullable=False, index=True)
    channel_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_slug = Column(String(80), nullable=True)                # congresso em foco (roteado)
    status = Column(String(20), nullable=False, server_default="active")  # active|waiting|handed_off|converted|closed
    history = Column(JSONB, nullable=False, server_default="[]")     # turnos p/ Responses API (compactável)
    history_summary = Column(Text, nullable=True)                   # resumo após compactação
    turns_count = Column(Integer, nullable=False, server_default="0")
    last_inbound_at = Column(DateTime(timezone=True), nullable=True)
    last_outbound_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentFollowup(Base):
    """Cadência de follow-up (Fase 3). Vencidos são processados pelo worker de
    follow-ups, respeitando janela 24h, opt-out e cadência máxima."""

    __tablename__ = "agent_followups"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.agent_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    contact_wa_id = Column(String(100), nullable=False, index=True)
    run_at = Column(DateTime(timezone=True), nullable=False, index=True)
    kind = Column(String(40), nullable=True)   # lot_deadline|abandoned_checkout|no_reply|custom
    payload = Column(JSONB, nullable=False, server_default="{}")
    status = Column(String(20), nullable=False, server_default="pending")  # pending|sent|cancelled|skipped
    created_at = Column(DateTime, server_default=func.now())


class AgentTurnLog(Base):
    """Auditoria/eval: todo turno gravado (tokens, latência, tools, guardrail).
    Base para o dashboard de custo e para a métrica de alucinação de preço."""

    __tablename__ = "agent_turn_logs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=True, index=True)
    direction = Column(String(10), nullable=True)   # inbound|outbound
    content = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=True)
    guardrail = Column(JSONB, nullable=True)         # resultado do validador de saída
    model = Column(String(60), nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

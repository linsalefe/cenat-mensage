from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    SECRET_KEY: str

    DATABASE_URL: str
    DB_SCHEMA: str = "mensageria"

    EVOLUTION_API_URL: str
    EVOLUTION_API_KEY: str
    EDUFLOW_WEBHOOK_URL: str = "http://localhost:3020/api/evolution/webhook"
    MEDIA_DIR: str = "/home/ubuntu/mensageria/uploads"

    # Broadcast media (Fase 5.1)
    MEDIA_ROOT: str = "/var/lib/mensageria/media"
    MEDIA_MAX_BYTES: int = 16 * 1024 * 1024  # 16 MB

    # Conversão de documentos (página Documentos). Ver docker/docconv/Dockerfile.
    DOC_CONVERT_IMAGE: str = "docconv:1"
    DOC_CONVERT_DIR: str = "/var/lib/mensageria/docconv"
    DOC_CONVERT_TIMEOUT: int = 120  # segundos
    DOC_CONVERT_MEMORY: str = "512m"
    # 1 container por vez: pico medido do soffice é ~153 MB e a máquina tem
    # ~620 MB livres compartilhados com o Postgres e o Next.
    DOC_CONVERT_CONCURRENCY: int = 1
    DOC_MAX_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # Remux de áudio do inbox (webm/opus -> ogg/opus). Ver docker/audioconv/.
    AUDIO_CONVERT_IMAGE: str = "audioconv:1"
    AUDIO_CONVERT_DIR: str = "/var/lib/mensageria/audioconv"
    AUDIO_CONVERT_TIMEOUT: int = 60  # segundos
    AUDIO_CONVERT_MEMORY: str = "128m"

    # Vazio = webhook aberto (dev). Preenchido = exige header X-Webhook-Secret
    WEBHOOK_SECRET: str = ""

    # Ponte Mensage <-> Customer (Sprint S1)
    # Segredo que o Customer envia no header X-Service-Token ao chamar o Mensage.
    SERVICE_TOKEN: str = ""
    # Base URL do Customer pra onde o Mensage relaya inbound/status/progresso.
    CUSTOMER_RELAY_URL: str = ""

    META_APP_SECRET: str = ""
    META_WEBHOOK_VERIFY_TOKEN: str = ""
    META_ACCESS_TOKEN: str = ""
    GRAPH_API_VERSION: str = "v21.0"

    # Conversions API CTWA (declarados na S1, consumidos na S2)
    META_DATASET_ID: str = ""   # dataset de mensagens do Events Manager
    META_CAPI_TOKEN: str = ""   # token CAPI/system user

    # Gatilhos de conversao (S3)
    CRM_WON_STAGE_KEYS: str = "ganho"   # keys de etapa de "ganho/venda" (CSV: "ganho,venda,fechado")
    PAYMENT_WEBHOOK_TOKEN: str = ""     # hottok (Hotmart) / secret (Kiwify)

    # Qualificacao -> LeadSubmitted (S4)
    CRM_QUALIFIED_STAGE_KEYS: str = "qualificado"   # keys de etapa "qualificado" (CSV)

    # Instagram Direct (app Meta SEPARADO do WhatsApp). Reusa GRAPH_API_VERSION.
    IG_APP_SECRET: str = ""
    IG_WEBHOOK_VERIFY_TOKEN: str = ""

    CORS_ORIGINS: str = ""

    # --- Agente de IA de vendas (PLANO_AGENTE.md) ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_MAIN: str = "gpt-5.4-mini"
    OPENAI_MODEL_GUARD: str = "gpt-5.4-nano"
    DOITY_TOKEN: str = ""
    DOITY_BASE_URL: str = "https://api.doity.com.br/public/v1"
    AGENT_DEBOUNCE_SECONDS: float = 8.0
    AGENT_MAX_TURNS_BEFORE_COMPACT: int = 30
    AGENT_MAX_TOOL_ITERS: int = 6
    AGENT_MAX_OUTPUT_TOKENS: int = 700
    AGENT_HANDOFF_NOTIFY_WA: str = ""   # número interno p/ avisar handoff (opcional)
    # Domínios liberados para links na saída do agente (guardrail Fase 4).
    AGENT_LINK_ALLOWLIST: str = "doity.com.br,cenatsaudemental.com,cenatcursos.com.br,materiais.cenatcursos.com.br"

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 3020
    APP_ENV: str = "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

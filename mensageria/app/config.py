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

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 3020
    APP_ENV: str = "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

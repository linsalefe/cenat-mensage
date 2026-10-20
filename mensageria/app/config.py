from functools import lru_cache

from pydantic import Field, field_validator
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
    # MODO SANDBOX. Números de teste separados por vírgula, só dígitos com DDI
    # (ex.: "5583999999999,5511888888888").
    # NÃO-VAZIA  → sandbox: o agente só atende esses números; para qualquer outro
    #              contato o comportamento é idêntico a agente desligado. Permite
    #              ligar agent_enabled no canal REAL sem nenhum cliente ver o agente.
    # VAZIA      → produção: gating normal (só agent_enabled + estado do contato).
    AGENT_TEST_WA_ALLOWLIST: str = ""

    # --- Agente de ATENDIMENTO ("Nat") — perfil agent_profile='atendimento' ---
    # Trava de canal. A Nat responde SOMENTE no canal cujo id está aqui, e esse
    # canal ainda precisa ser provider='evolution' com agent_profile
    # ='atendimento'. None (default) = Nat desligada em qualquer lugar, mesmo que
    # algum canal esteja marcado como de atendimento com agent_enabled=true.
    AGENT_ATENDIMENTO_CHANNEL_ID: int | None = None
    # Sandbox PRÓPRIO do atendimento, mesmo formato de AGENT_TEST_WA_ALLOWLIST.
    # Os dois são independentes: ligar este NÃO coloca o canal 6 (vendas) em
    # sandbox, e vice-versa.
    AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST: str = ""
    # Humano respondeu pelo painel ou pelo celular do número do atendimento →
    # pausa a IA para aquele contato (ai_active=false). O eco da própria
    # mensagem da IA não conta como humano (registro anti-eco no handler).
    AGENT_ATENDIMENTO_PAUSE_ON_HUMAN: bool = True
    # Base de conhecimento da Nat: até este tamanho total vai INTEIRA no system
    # prompt; acima dele o modelo recebe só o índice e ganha a tool buscar_base.
    AGENT_KB_INLINE_MAX_CHARS: int = 15000
    # Transcrição de voice note no perfil ATENDIMENTO. Sem isto, quem manda
    # áudio recebe silêncio (o agente nem é acordado). Só vale para o perfil
    # 'atendimento' — o canal 6 de vendas segue ignorando mídia.
    AGENT_AUDIO_TRANSCRIBE: bool = True
    OPENAI_MODEL_TRANSCRIBE: str = "whisper-1"
    # Corte de tamanho do áudio (o limite da API é 25 MB). Áudio muito longo
    # custa caro por minuto e demora mais do que a paciência de quem espera.
    AGENT_AUDIO_MAX_BYTES: int = 20 * 1024 * 1024

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 3020
    APP_ENV: str = "development"

    @field_validator("AGENT_ATENDIMENTO_CHANNEL_ID", mode="before")
    @classmethod
    def _canal_atendimento_vazio_e_none(cls, v):
        """`AGENT_ATENDIMENTO_CHANNEL_ID=` (vazio) significa Nat desligada.

        Sem isto, a string vazia — que é o estado natural de "desligado" e é como
        a var aparece no .env.example — levanta ValidationError e o processo NÃO
        SOBE. Numa var de desligar agente, falhar fechado tem que ser desligar o
        agente, não derrubar o backend inteiro em produção.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

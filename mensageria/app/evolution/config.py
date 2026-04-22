"""Config do módulo evolution — lê do Settings global (pydantic-settings)."""
from app.config import get_settings

_settings = get_settings()

EVOLUTION_API_URL = _settings.EVOLUTION_API_URL
EVOLUTION_API_KEY = _settings.EVOLUTION_API_KEY
EDUFLOW_WEBHOOK_URL = _settings.EDUFLOW_WEBHOOK_URL
MEDIA_DIR = _settings.MEDIA_DIR

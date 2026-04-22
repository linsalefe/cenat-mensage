# mensageria — backend CENAT

Backend FastAPI mono-tenant de mensageria (evolution/chatbot/automations), portado do EduFlow Hub.

## Stack

- Python 3.12 (gerenciado via `uv`)
- FastAPI + SQLAlchemy async + Alembic
- Pydantic v2
- Postgres existente (database `evolution`), schema dedicado `mensageria`

## Porta

3020 (3010 = webhook-backend legado, 5000 = webhook legado)

## Setup local

```bash
cd ~/mensageria
uv sync                    # instala deps no .venv
source .venv/bin/activate
alembic upgrade head       # aplica migrations
uvicorn app.main:app --port 3020 --reload
```

## Parar

```bash
pkill -f "uvicorn app.main"
```

## Estrutura

```
app/
  main.py        FastAPI app + health + CORS
  config.py      settings via pydantic-settings (.env)
  database.py    engine async SQLAlchemy
  deps.py        get_db
  models.py      modelos SQLAlchemy (schema mensageria)
  evolution/     módulo portado do EduFlow (Fase 1)
alembic/         migrations
.env             secrets (permissão 600)
```

## Operação

- Nenhum webhook de instância Evolution real é alterado automaticamente.
- `EDUFLOW_WEBHOOK_URL` só define o default de novas instâncias criadas por este backend.
- Migração de webhooks das instâncias existentes é manual.

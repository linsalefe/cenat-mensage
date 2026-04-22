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

## Broadcasts (Fase 5.1)

### Tabelas

- `mensageria.broadcast_jobs` — um registro por envio (em massa ou individual).
  Campos chave: `audience_type`, `audience_spec` (JSONB), `message_payload`
  (JSONB), `interval_seconds`, `scheduled_at`, `status`, contadores de progresso
  (`sent_count`, `error_count`).
- `mensageria.broadcast_logs` — linha por destinatário (tentativa de envio).
  Retenção: **7 dias** (task periódica de limpeza).
- `mensageria.media_assets` — upload de mídia reutilizável entre jobs.

### Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | /api/media/upload | Upload multipart. Retorna `{id, url, media_type, size_bytes}`. Max 16 MB. |
| GET | /api/media | Lista últimos 50 uploads (admin vê todos) |
| GET | /api/media/{id} | Baixa o arquivo com Content-Type correto |
| DELETE | /api/media/{id} | Remove (dono ou admin) |
| GET | /api/evolution/instances/{name}/groups | Lista grupos via Evolution (cache 60s, apikey server-side) |
| POST | /api/broadcasts | Cria job. `audience_type` ∈ `{all_groups, selected_groups, contacts_tag, csv, single_contact}` |
| GET | /api/broadcasts | Lista (filtros: `status`, `channel_id`, `limit`, `offset`) |
| GET | /api/broadcasts/{id} | Detalhe |
| GET | /api/broadcasts/{id}/logs | Logs de envio do job |
| POST | /api/broadcasts/{id}/cancel | Só se status ∈ `{pending, running}` |
| DELETE | /api/broadcasts/{id} | Hard delete (criador ou admin) |

### Upload de mídia (curl)

```bash
TOKEN=$(curl -s -X POST http://localhost:3020/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"linsalefe@gmail.com","password":"..."}' \
  | jq -r .access_token)

curl -X POST http://localhost:3020/api/media/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/caminho/imagem.jpg;type=image/jpeg"
```

Tipos aceitos: `image/jpeg`, `image/png`, `image/webp`, `audio/ogg`, `audio/mpeg`,
`video/mp4`, `application/pdf`.

### Estrutura de `audience_spec` por tipo

| audience_type | audience_spec |
|---|---|
| `all_groups` | `{}` (resolvido em runtime a partir da instância do canal) |
| `selected_groups` | `{"group_ids": ["123@g.us", "456@g.us"]}` |
| `contacts_tag` | `{"tag": "cliente_vip"}` (Fase futura — depende de Tag) |
| `csv` | `{"contacts": [{"wa_id": "5511...", "name": "..."}]}` |
| `single_contact` | `{"wa_id": "5511...", "name": "..."}` |

### Armazenamento de mídia

Arquivos em `/var/lib/mensageria/media/` (dono `ubuntu:ubuntu`, `750`). Nome gerado
como `<uuid4>.<ext>`. Limite por arquivo: `MEDIA_MAX_BYTES` (default 16 MB).

### Retenção

Task `start_broadcast_cleanup_task` roda a cada 24h (1ª execução 10 min após boot)
e apaga `broadcast_logs.sent_at` mais antigos que 7 dias.

## Broadcast execution (Fase 5.3)

Worker assíncrono (`app/broadcast/worker.py`) rodando no mesmo processo uvicorn.

### Comportamento

- **1 worker serial**, poll a cada 10 s. Processa 1 job por vez, um destinatário
  por vez (respeitando `interval_seconds` entre sends).
- **Audience**: suporta `all_groups`, `selected_groups`, `single_contact`.
  `contacts_tag` e `csv` ainda não implementados (job vira `failed` com
  `error_message` descritiva).
- **Retry por target**: 2 tentativas com backoff `[5s, 15s]` só em erros
  transientes (timeout, 5xx, 429). Erro permanente (4xx exceto 429) marca o log
  como erro e segue para o próximo target.
- **Cancel**: antes de cada envio o worker recarrega `job.status`; se virou
  `cancelled`, interrompe o loop.
- **Mídia**: carrega base64 do `MediaAsset` uma vez por job e reutiliza.
- **Interpolação**: `{nome}` / `{grupo_nome}` / `{wa_id}` no `text`.
- **Scheduling**: jobs com `scheduled_at` futuro são ignorados até o horário
  passar (latência ≤ 10 s do poll).
- **Crash recovery**: ao boot, jobs em `running` com `updated_at > 10 min`
  voltam para `pending`.

### Ligar / desligar

O worker é startado no lifespan do FastAPI — controlar via systemd:

```bash
sudo systemctl stop mensageria    # para tudo (API + worker)
sudo systemctl start mensageria   # sobe API + worker
sudo systemctl restart mensageria
```

Log de startup em `/var/log/mensageria.log`:
```
📡 Broadcast worker started (poll=10s)
```

### Forçar retry de um job `failed` / `cancelled`

```sql
UPDATE mensageria.broadcast_jobs
SET status='pending', started_at=NULL, completed_at=NULL, error_message=NULL
WHERE id = <X>;
```

Na próxima iteração do poll o worker pega.

### Limitações conhecidas

- Serial (1 job por vez, 1 target por vez). Múltiplos workers exigiria
  refatorar o `_pick_next_job` e pensar em isolamento de mídia carregada.
- `contacts_tag` e `csv` não implementados — jobs desse tipo falham.
- `recurrence` é só placeholder no schema — não há execução recorrente.
- Logger interno usa `logging` padrão (nível WARNING). Só o banner de startup
  e eventos de crash aparecem em log sem subir o nível.


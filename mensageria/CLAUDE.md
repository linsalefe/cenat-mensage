# CLAUDE.md — Guia operacional do CENAT Mensage (produção)

> **Este servidor É produção.** cenat.whatsflow.cloud atende clientes reais.
> Trate mudanças com cuidado: confirme antes de reiniciar serviços, rodar migrações
> ou gravar no banco. Nunca imprima secrets/tokens.

## O que é
Backend de mensageria do CENAT: WhatsApp (Meta Cloud API + Evolution), Instagram Direct,
chatbot/automações, CRM/pipelines, disparos (broadcast/campaign), conversão CTWA e ponte
com o Customer (cenatdata.online). FastAPI + Postgres.

## Arquitetura real (o que roda de fato)

| Componente | Como roda | Porta | Path |
|-----------|-----------|-------|------|
| **Backend** | `mensageria.service` (systemd) → uvicorn `app.main:app` **--workers 1** | `127.0.0.1:3020` | `/home/ubuntu/mensageria` |
| **Frontend** | `mensageria-frontend.service` → `pnpm start` (Next.js) | `:3030` | `/home/ubuntu/mensageria-frontend` |
| **Postgres** | container docker `postgres` (pg 15-alpine) | `127.0.0.1:5432` | db `evolution`, schema **`mensageria`** |
| **Evolution API** | container docker `evolution-api` v2.3.7 | `8080` | — |
| **Nginx** | reverse proxy, TLS | `80/443` | site `cenat` |

Serviços legados no host (NÃO são o mensageria): `fastapi-webhook.service` (3010),
`webhook.service` (5000). O nginx `/webhook/` aponta pro 3010 (legado), **não** pro mensageria.

**Python:** 3.12.13, venv em `.venv` (gerenciado por `uv`). Deps chave: fastapi 0.136, sqlalchemy 2.0 (async),
asyncpg, alembic 1.18, httpx 0.28, pydantic 2.13. `openai` **não** instalado.

## Roteamento público (nginx site `cenat` → `cenat.whatsflow.cloud`)
- `/api/` → `127.0.0.1:3020/api/` (backend)
- `/` → `127.0.0.1:3030` (frontend)
- `/webhook/` → `127.0.0.1:3010` (app **legada**, não mensageria)
- **Webhook Meta (WhatsApp+Instagram):** `https://cenat.whatsflow.cloud/api/meta/webhook` (GET verify + POST eventos)
- `/health` mora na **raiz** do backend (`127.0.0.1:3020/health`) — **não** exposto publicamente.

## Como rodar / reiniciar
```bash
# Backend (reinicia o processo que roda os 4 background workers no lifespan)
sudo systemctl restart mensageria.service
sudo systemctl status mensageria.service

# Frontend — PRECISA build antes se mudou código do front:
cd /home/ubuntu/mensageria-frontend && pnpm build && sudo systemctl restart mensageria-frontend.service

# Logs (NÃO use journalctl pro app — ele loga em arquivo):
tail -f /var/log/mensageria.log
tail -f /var/log/mensageria-frontend.log

# Postgres (read-only exemplo):
docker exec postgres psql -U evolution -d evolution -c "select * from mensageria.channels;"

# Alembic (do dir de deploy, que AGORA está na branch feature/agente-ia):
.venv/bin/python -m alembic current   # b2e5c9a1f7d0 (head)
.venv/bin/python -m alembic heads
```
⚠️ **Mantenha `--workers 1`.** Os 4 background tasks (chatbot scheduler, broadcast worker,
broadcast cleanup, campaign worker) rodam no lifespan do processo uvicorn; múltiplos workers
os **duplicariam**.

## Estrutura do código (`app/`)
`main.py` (lifespan + include_routers) · `models.py` (todos os models, 1 arquivo) ·
módulos: `meta/` (WhatsApp oficial + webhook + bridge), `evolution/`, `instagram/`,
`chatbot/` (engine + scheduler + routes), `broadcast/`, `campaign/`, `crm/`, `contact_lists/`,
`documents/` (conversão em container docconv), `messaging/`, `payments/`, `relay/` (ponte Customer).

- **Inbound Meta** (`app/meta/routes.py::_process_inbound`): persiste msg → relaya ao Customer.
  **Não dispara chatbot/IA** nesse caminho hoje.
- **Chatbot engine** (`app/chatbot/engine.py`): só atua quando `channel.operation_mode == "chatbot"`.
- **`operation_mode`** (coluna `channels.operation_mode`, `String(20)`, **default `"ai"`**):
  valores aceitos `ai | chatbot | none`. **"ai" hoje é no-op** (não há implementação de IA).

## Banco (schema `mensageria`)
Postgres 15, ~260 MB. Migrações Alembic (dir `alembic/`). **PROD está em `b2e5c9a1f7d0` (head)** — o
agente de IA (Fases 0–4) foi implantado 29/07/2026 e o dir de deploy está na branch `feature/agente-ia`.
Tabelas principais: `channels`, `contacts`, `messages`, `chatbot_flows/sessions`,
`broadcast_jobs/logs`, `campaign_runs`, `pipelines`, `contact_lists`, `conversion_events`,
`meta_templates`, `instagram_automations`, `automation_flows/steps/executions`.
- `models.py` está consistente com o banco (`contact_tag_links` é tabela de associação sem classe).
- ❗ **Sem rotina de backup.** Faça `pg_dump` antes de migração/gravação nova relevante.

## Canais (estado atual)
- **6 — "Cenat - disparos"** — WhatsApp **official** (Meta Cloud), `operation_mode=ai`, ativo. **Canal conversacional principal** (tem inbound). Nº no banco: +5511936235780 (⚠️ diverge do +5581995345775 citado externamente — confirmar `phone_number_id`).
- **9 — "comunicados"** — WhatsApp **evolution**, `operation_mode=ai`, ativo. Só disparo (0 inbound).
- **11 — "cenatsaudemental"** — Instagram, `operation_mode=none`. Recebimento de DM historicamente bloqueado (token de System User, precisa Page token).

## Convenções / avisos de produção
- **Timezone São Paulo (-03).** `Message.timestamp` é **UTC-3 naive** — comparar com `timestamptz` erra 3h.
- **`wa_id`**: `contacts.wa_id`/`messages.contact_wa_id` = VARCHAR(100). Instagram usa prefixo `ig:`.
- **Instagram é um app Meta SEPARADO** do WhatsApp: `IG_APP_SECRET` ≠ `META_APP_SECRET`.
- Segredos vivem em `/home/ubuntu/mensageria/.env` (perm 600, `APP_ENV=production`). **Nunca imprimir valores.**
- `docconv:1` e `audioconv:1` são imagens docker build-à-mão (conversão de documento/áudio). Não some com elas.
- Deploy roda em **feature branch sem git remote** (hoje `documentos-conversao-20260710`), não em `main`.
  Repo é deploy local; sync manual (ver histórico do projeto). Working tree limpo.
- Ponte Mensage→Customer (`CUSTOMER_RELAY_URL=https://cenatdata.online`): endpoints de relay
  retornaram **404** historicamente — best-effort, não derruba o fluxo, mas pode estar quebrada.

## Scripts úteis
- `scripts/create_admin.py` — cria usuário admin.
- `testar_doity.py` / `backfill_doity.py` — diagnóstico/backfill da API Doity.
  Leem `DOITY_TOKEN` e `DOITY_EVENTO_IDS` **do ambiente** (exportar ad-hoc). Base:
  `https://api.doity.com.br/public/v1`, endpoints `/eventos/{id}` e `/eventos/{id}/participantes`.

## Agente de IA (OpenAI) — Fases 0–4 IMPLANTADAS e DESATIVADAS (29/07/2026)
Agente de vendas de congressos conforme `PLANO_AGENTE.md`. **Deploy em produção concluído**: o dir de
deploy está na branch `feature/agente-ia`, banco no head `b2e5c9a1f7d0`, serviço reiniciado (PID novo,
saudável). **`channels.agent_enabled=false` em TODOS os canais → o agente NÃO responde ninguém ainda.**

**Módulo `app/agent/`:** `handler` (debounce 8s, gating de 5 condições, watermark de idempotência,
envio) · `loop` (OpenAI Responses + tool loop + guardrails + log de turnos) · `tools`/`tools_write`
(leitura + escrita sobre agent_products/Contact) · `prompt` · `router` · `doity` · `guardrails`
(entrada nano + saída determinística) · `workers` (sync 30min, conversão 5min, follow-up 60s).
Integração: `app/meta/routes.py::_process_inbound` (após commit, background, relay intacto).
Evals: `tests/agent/eval_agent.py` (8 personas + juiz; alucinação de preço = 0).

**Workers no lifespan:** sync (sempre; atualiza preços via Doity `/lotes`), conversão e follow-up
(**GATED por agent_enabled** — dormentes enquanto nenhum canal estiver ligado; zero efeito externo).

### Como ATIVAR (ato deliberado — decisão humana)
1. **Confirmar o canal/número.** O agente atende o canal WhatsApp **official** (id 6). O nº no banco
   (+5511936235780) diverge do +5581995345775 das landings — confirme o `phone_number_id` antes.
2. **Sandbox primeiro** (rollout §7): teste com contatos internos. Para ligar num canal:
   `UPDATE mensageria.channels SET agent_enabled=true WHERE id=<canal>;` (efeito imediato, sem deploy).
   Por contato: o gatilho exige `Contact.ai_active=true` (novos inbounds já nascem assim) e
   `not opted_out and not is_group`.
3. Monitore pelo painel (mensagens do agente têm `sent_by_ai=true`) e por `mensageria.agent_turn_logs`
   (tokens/latência/guardrail/custo por turno).

### Interruptores de EMERGÊNCIA (desligam na hora, sem deploy)
- Por canal: `UPDATE mensageria.channels SET agent_enabled=false WHERE id=...;`
- Por contato: `UPDATE mensageria.contacts SET ai_active=false WHERE wa_id=...;`

### Pendências externas (não bloqueiam o deploy; bloqueiam FUNÇÕES específicas ao ativar)
- **Templates WABA** `lembrete_lote` e `retomada_conversa` (utility): precisam ser criados e aprovados
  na Meta para follow-up FORA da janela de 24h. Sem eles, esses follow-ups são marcados `skipped`
  (dentro de 24h funciona com texto livre). WABA está com pagamento restrito (ver memória
  `broadcast-template-state`).
- **CAPI de conversão**: `META_DATASET_ID` e `META_CAPI_TOKEN` estão vazios → `fire_conversion` no-op
  (a conversão ainda marca `lead_status=ganho` e cancela follow-ups; só não envia o evento à Meta).
- Confirmar `doity_event_id` se novos congressos entrarem (descobrir via HTML da landing: `evento_id`).

**Rollback do deploy** (se necessário): `git -C /home/ubuntu/mensageria checkout documentos-conversao-20260710`
+ `sudo systemctl restart mensageria.service`. O banco fica em `b2e5c9a1f7d0` (aditivo, o código antigo
ignora as colunas/tabelas novas). Backups em `/home/ubuntu/backups/mensageria/`.

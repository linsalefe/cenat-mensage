# AUDITORIA DE PRODUÇÃO — CENAT Mensage

> Auditoria **somente leitura** executada em **2026-07-29** para validar as premissas
> do agente de IA de vendas (OpenAI) contra a realidade do servidor.
> Nenhum arquivo de aplicação, migração, serviço ou registro de banco foi modificado.

> 📌 **Atualização pós-auditoria (29/07/2026):** a **Fase 0 já foi executada** — vários bloqueios abaixo
> foram resolvidos (chaves no `.env`, IDs Doity descobertos, backup+cron, migração `a7f0c1b2d3e4`
> aplicada, `agent_products` semeado). Para o **estado atual**, veja `CLAUDE.md` → "Estado do agente".
> Este documento permanece como o snapshot da auditoria original.

> ⚠️ **`PLANO_AGENTE.md` NÃO existe** — não está na raiz do repo nem em qualquer lugar
> do servidor (`find / -iname "*plano*agente*"` → vazio). Esta auditoria foi conduzida
> contra as premissas descritas no briefing da tarefa (agente OpenAI, `operation_mode="ai"`,
> `OPENAI_API_KEY`, `DOITY_TOKEN`, congressos Doity). **O plano precisa ser fornecido/commitado
> antes da Fase 0.**

---

## 1. INFRA

| Item | Valor |
|------|-------|
| SO | Ubuntu 22.04.5 LTS (Jammy) |
| Kernel | Linux 6.8.0-1052-aws |
| CPU | 2 vCPU |
| RAM | 1.9 GiB total — **304 MiB livres**, 830 MiB disponíveis, 16 MiB shared |
| Swap | 2.0 GiB (1.4 GiB em uso) |
| Disco `/` | 58 GB total, 18 GB usados, **41 GB livres (30%)** |
| Timezone | America/Sao_Paulo (-03) |
| Uptime | 98 dias |

**Containers Docker (2 rodando):**
- `evolution-api` — `evoapicloud/evolution-api:v2.3.7` — porta `8080` (up 3 meses)
- `postgres` — `postgres:15-alpine` — `127.0.0.1:5432` (up 3 meses)

Imagens auxiliares presentes (build manual): `docconv:1`, `audioconv:1` (usadas por /documentos e áudio do inbox), `linuxserver/ffmpeg`.

**Serviços systemd relevantes (todos `active/running`):**
- `mensageria.service` — backend FastAPI (uvicorn `app.main:app` em `127.0.0.1:3020`)
- `mensageria-frontend.service` — Next.js (`pnpm start` em `:3030`), WD `/home/ubuntu/mensageria-frontend`
- `nginx.service` — reverse proxy
- `fastapi-webhook.service` / `webhook.service` — apps **legadas** (portas 3010 e 5000, projetos antigos)

**Nginx — site ativo `cenat` (`server_name cenat.whatsflow.cloud`):**
| Rota | Proxy |
|------|-------|
| `/api/` | `http://127.0.0.1:3020/api/` (mensageria backend) |
| `/` | `http://127.0.0.1:3030` (frontend) |
| `/webhook/` | `http://localhost:3010/` (app legada) |
| `/legacy/` | (legado) |

Segundo site `whatsflow` (por IP `13.221.209.242`) proxeia para o Evolution (8080) e app legada (5000) — não faz parte do fluxo mensageria.

**Portas em escuta:** 3020 (backend, só loopback), 3030 (frontend), 3010/5000 (legado), 8080 (Evolution), 5432 (Postgres, só loopback), 80/443 (nginx), 22 (ssh).

**SSL:** `cenat.whatsflow.cloud` via Let's Encrypt/Certbot — **válido até 2026-10-23** (~85 dias). Renovação automática via `cron.d/certbot`.

---

## 2. CÓDIGO vs. DEPLOY

- **Path do código:** `/home/ubuntu/mensageria` (é o WorkingDirectory do systemd — **o que roda É o repo git**, sem divergência de path).
- **Como é servido:** `mensageria.service` → `/home/ubuntu/mensageria/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 3020 --workers 1`. **1 worker** (importante: workers de background rodam no lifespan desse único processo).
- **Python:** 3.12.13 (venv em `.venv`, gerenciado por `uv`).
- **Branch atual:** `documentos-conversao-20260710` @ commit `c7deade` ("feat(inbox): CRM na conversa, tags, não lidas, mídia e áudio").
- **Working tree:** **limpo** — 0 arquivos modificados/não commitados.
- **Processo em execução** confirmado no PID 857789, iniciado 2026-07-10 11:21 — coerente com o commit da branch. Sem divergência entre git e deploy.
- ⚠️ **Não roda na branch `main`.** O deploy vive numa feature branch. Ver memória `git-deploy-vs-monorepo`: este repo é deploy local **sem remote**; sync manual.

---

## 3. BANCO

- **Postgres:** 15.15 (Alpine), container `postgres`, banco `evolution`, **schema `mensageria`**.
- **Tamanho do banco `evolution`:** 260 MB (schema mensageria é subconjunto).
- **Alembic:** `current` = `b7e41c9d2a10` **==** `heads` = `b7e41c9d2a10`. **EM SINCRONIA** (single head, sem migração pendente). Coincide com `mensageria.alembic_version`.
- **Tabelas (schema mensageria) vs `models.py`:** consistente. `models.py` define 22 `__tablename__`; todas existem no banco. Extras no banco: `alembic_version` (sistema) e `contact_tag_links` (tabela de associação M2M, definida via `Table()` sem classe). **Nenhuma tabela de modelo faltando no banco.**

**Contagens:**
| Tabela | Linhas |
|--------|--------|
| contacts | 568 |
| messages | 4.217 |
| channels | 3 |
| chatbot_flows | 9 |
| chatbot_sessions | 0 |
| conversion_events | 0 |

Mensagens por canal: canal 6 → 86 in / 1.884 out; canal 9 → 0 in / 1.846 out; canal 11 (IG) → 1 in; sem canal → 400 out (legado).

- **Backup:** ❌ **Não há rotina de backup do banco.** `/var/backups` só tem `alternatives.tar` do sistema; nenhum `pg_dump`/cron de dump; nenhum `.sql.gz`/`.dump` em `/home`, `/opt`, `/var/backups`. **Risco operacional real.**

---

## 4. CANAIS

| id | name | type | provider | phone_number | operation_mode | connected | active | flow | ig/page |
|----|------|------|----------|--------------|----------------|-----------|--------|------|---------|
| 6 | Cenat - disparos | whatsapp | **official** (Meta Cloud) | **+5511936235780** | **ai** | ✔ | ✔ | — | — |
| 9 | comunicados | whatsapp | **evolution** | — | **ai** | ✔ | ✔ | — | — |
| 11 | cenatsaudemental | instagram | instagram | — | none | ✔ | ✔ | — | page 709368575823331 / ig 17841405925471370 |

- **Canal oficial Meta:** é o **canal 6** (único `provider=official`). É o canal conversacional real: 86 mensagens inbound.
- ⚠️ **O número não bate com o briefing.** O briefing diz oficial = **+55 81 99534-5775** (DDD 81, PE). O banco registra `phone_number = +5511936235780` (DDD 11, SP). **Divergência a confirmar** — pode ser label desatualizado (o que importa na API Meta é o `phone_number_id`, não visível aqui por conter/estar junto de token). Validar qual canal/phone_number_id é o número pretendido antes de plugar a IA.
- **`operation_mode` do canal oficial hoje:** `ai` ⚠️ (ver Riscos — modo "ai" já está setado em produção nos dois canais WhatsApp).
- **Evolution ativo:** sim, canal 9 (`comunicados`), usado só para disparo (0 inbound).
- **Instagram:** canal 11, modo `none`, conectado (recebimento historicamente bloqueado — ver memória `ig-subscription-blocker`).

---

## 5. WEBHOOKS

- **URL pública que a Meta chama:** `https://cenat.whatsflow.cloud/api/meta/webhook`
  (nginx `/api/` → `127.0.0.1:3020`; rota no código: `webhook_router` prefix `/api/meta`, `GET`+`POST /webhook`).
  - `GET /api/meta/webhook` (sem params) → **422** (endpoint vivo, validando verify token).
  - `POST /api/meta/webhook` → **200 OK**, com origem em IPs `173.252.x` (Meta/Facebook). **51 POSTs** registrados após o último restart. **Inbounds ESTÃO chegando.**
- **`/health`:** responde `200 {"status":"ok","db":"connected"}` **localmente** (`127.0.0.1:3020/health`). **Não** é exposto publicamente (nginx só proxeia `/api/`, `/`, `/webhook/`, `/legacy/`) → `https://.../health` = 404 (esperado; health mora na raiz do backend, não sob `/api`).
- **Relay para o Customer (`CUSTOMER_RELAY_URL=https://cenatdata.online`):**
  - ⚠️ Nos logs, as chamadas `/api/whatsapp/relay/inbound`, `/status` e `/broadcast-progress` retornaram **HTTP 404** (best-effort → segue sem falhar). Nenhum 2xx de relay registrado.
  - Essas ocorrências de 404 são **antigas** (anteriores ao restart de 2026-07-10). **Não há evidência de relay bem-sucedido.** A ponte Mensage→Customer aparenta estar **quebrada/desalinhada de rota no lado do cenatdata.online**. Fora do escopo do agente de IA, mas registrar.
- Último inbound persistido no banco: **2026-07-16 17:50** (naive UTC-3). Volume conversacional baixo/esporádico.

---

## 6. VARIÁVEIS DE AMBIENTE

`.env` presente (`/home/ubuntu/mensageria/.env`, perm 600, `APP_ENV=production`). Presença por chave (**valores nunca impressos**):

| Variável | Status |
|----------|--------|
| SECRET_KEY | ✅ presente |
| DATABASE_URL | ✅ presente |
| DB_SCHEMA (`mensageria`) | ✅ presente |
| EVOLUTION_API_URL / EVOLUTION_API_KEY | ✅ presente |
| EDUFLOW_WEBHOOK_URL | ✅ presente (`http://localhost:3020/api/evolution/webhook`) |
| CORS_ORIGINS | ✅ presente |
| MEDIA_DIR / MEDIA_ROOT / MEDIA_MAX_BYTES | ✅ presente |
| WEBHOOK_SECRET | ✅ presente |
| APP_HOST / APP_PORT / APP_ENV | ✅ presente (`production`) |
| META_APP_SECRET / META_WEBHOOK_VERIFY_TOKEN / META_ACCESS_TOKEN | ✅ presente |
| API_KEY | ✅ presente (não está no `.env.example`) |
| SERVICE_TOKEN | ✅ presente |
| CUSTOMER_RELAY_URL | ✅ presente (`https://cenatdata.online`) |
| IG_APP_SECRET / IG_WEBHOOK_VERIFY_TOKEN | ✅ presente |
| CRM_WON_STAGE_KEYS / CRM_QUALIFIED_STAGE_KEYS | ✅ presente (`convertido` / `qualificado`) |
| **GRAPH_API_VERSION** | ⚠️ **não está no `.env`** (só no `.env.example` = `v21.0`; código usa default) |
| **OPENAI_API_KEY** | ❌ **AUSENTE** (exigida pelo plano) |
| **DOITY_TOKEN** | ❌ **AUSENTE** (exigida pelo plano) |
| **DOITY_EVENTO_IDS / DOITY_BASE_URL** | ❌ ausentes |

Observação: `.env.example` lista `GRAPH_API_VERSION` mas o `.env` de produção **não** — confirmar se o código tem default seguro (`v21.0`) ou se depende do env.

---

## 7. DOITY

- **`DOITY_TOKEN` não está persistido** em lugar nenhum: ausente no `.env`, ausente no environ do processo (PID 857789), ausente no `bash_history`. Os scripts `testar_doity.py` e `backfill_doity.py` leem `DOITY_TOKEN` e `DOITY_EVENTO_IDS` **do ambiente no momento da execução manual** (`os.getenv`), então foram rodados com o token exportado ad-hoc e nada ficou gravado.
- **Não foi possível testar a API Doity** (sem token, teste GET não realizado — nenhum valor de secret exposto/inventado).
- **IDs de evento Doity encontrados: NENHUM.** Não há `doity_event_id` em `.env`, scripts, histórico, cron ou colunas do banco. **Não foi possível descobrir os IDs de "Gênero e Sexualidades 2026" nem "Ouvidores de Vozes 2026".**
- `testar_doity.py` referencia: `BASE_URL = https://api.doity.com.br/public/v1`, endpoints `/eventos/{id}` e `/eventos/{id}/participantes`, auth `Bearer {DOITY_TOKEN}`. `backfill_doity.py` usa os mesmos.
- **Ação necessária:** o usuário precisa fornecer `DOITY_TOKEN` e os dois `doity_event_id`. Com o token, `python testar_doity.py` (com `DOITY_EVENTO_IDS` setado) lista nome do evento e situações — mas os IDs precisam vir de fora (painel Doity).

---

## 8. WORKERS (lifespan)

`app/main.py` lifespan cria 4 tasks. **Todos confirmados rodando após o restart de 2026-07-10** (linhas de boot pós-restart no log):

| Worker | Evidência no log | Status |
|--------|------------------|--------|
| Chatbot scheduler | `⏰ Chatbot scheduler loop started (poll 30s)` | ✅ ativo |
| Broadcast cleanup | `🧹 Broadcast cleanup task scheduled (first run 600s, interval 86400s)` | ✅ ativo |
| Campaign worker | `📡 Campaign worker started (poll=5s)` | ✅ ativo |
| Broadcast worker | `📡 Broadcast worker started (poll=10s)` — jobs recentes (`job=98 bloco 0-2: 2 ok`) | ✅ ativo |

⚠️ Rodam todos **dentro do único worker uvicorn** (`--workers 1`). Se o plano da IA aumentar `--workers`, os background tasks **duplicariam** (cada processo roda o lifespan). Manter `--workers 1` ou mover workers para processo separado.

---

## 9. RISCOS PARA O PLANO

1. 🔴 **`PLANO_AGENTE.md` não existe.** Todas as premissas foram inferidas do briefing. Commitar o plano antes da Fase 0.
2. 🔴 **`operation_mode="ai"` JÁ está ativo nos dois canais WhatsApp de produção (6 e 9).** É o **default do model** (`models.py:81 default="ai"`) e valor aceito pelo regex `^(ai|chatbot|none)$`. **Hoje é no-op**: o caminho Meta inbound (`_process_inbound`) só persiste + relaya ao Customer; o engine de chatbot só age em `operation_mode=="chatbot"`. **Assim que o código da IA shipar e passar a reagir ao modo "ai", ele começa a responder mensagens reais dos canais 6 e 9 imediatamente, sem ativação explícita.** Blindar: usar flag/coluna nova ou modo dedicado, não reaproveitar "ai" silenciosamente; e/ou zerar os canais para `none` antes do deploy.
3. 🟠 **Número oficial não bate:** briefing diz +55 81 99534-5775; banco (canal 6) diz +55 11 93623-5780. Confirmar o `phone_number_id`/número correto antes de plugar a IA.
4. 🔴 **`OPENAI_API_KEY` e `DOITY_TOKEN` ausentes** + **SDK `openai` não instalado** no venv. `httpx 0.28.1` está presente (dá pra falar com a OpenAI via httpx sem SDK, se preferir).
5. 🔴 **IDs Doity dos dois congressos desconhecidos** e sem token para descobri-los — bloqueio para a lógica de vendas por evento.
6. 🟠 **RAM apertada:** 1.9 GiB total, ~300 MiB livres, swap já em 1.4 GiB. Um novo cliente OpenAI/carga extra no mesmo processo pode pressionar memória. Monitorar.
7. 🟠 **Sem backup de banco.** Antes de qualquer migração/gravação nova (o agente vai gravar conversas/estado), estabelecer `pg_dump` agendado.
8. 🟠 **Deploy roda em feature branch sem remote** (`documentos-conversao-20260710`, não `main`). Definir estratégia de branch/merge para o código do agente.
9. 🟡 **Relay ao Customer (cenatdata.online) retorna 404** historicamente — a ponte pode estar quebrada. Se o agente depender de dados/eventos do Customer, revisar.
10. 🟡 **`GRAPH_API_VERSION` ausente do `.env`** de produção (usa default do código). Confirmar versão efetiva antes de mexer em envio Meta.
11. 🟡 **`--workers 1`**: não escalar sem separar os background workers (duplicação de scheduler/worker).

---

## Divergências e ajustes necessários no plano

- **Fornecer/commitar `PLANO_AGENTE.md`.** A auditoria não pôde validar linha a linha do plano — só as premissas do briefing.
- **Não reutilizar `operation_mode="ai"` como gatilho implícito.** Está ligado em produção e é o default. Introduzir ativação explícita (nova coluna/flag `ai_enabled` por canal, ou migração que rebaixe os canais para `none` no deploy) para evitar a IA responder clientes reais sem querer.
- **Confirmar o canal/número alvo da IA** (canal 6 official; resolver a discrepância 81 vs 11).
- **Adicionar segredos ao `.env`:** `OPENAI_API_KEY`, `DOITY_TOKEN`, `DOITY_EVENTO_IDS` (e talvez `GRAPH_API_VERSION`). Instalar `openai` no venv (`uv add openai`) — ou usar `httpx` já presente.
- **Obter os `doity_event_id`** de "Gênero e Sexualidades 2026" e "Ouvidores de Vozes 2026" no painel Doity (não são deriváveis do servidor).
- **Estabelecer backup de banco** antes de o agente começar a gravar estado.
- **Manter `--workers 1`** (ou externalizar os workers) para não duplicar background tasks.
- **Migração Alembic:** base está limpa e em sincronia (single head `b7e41c9d2a10`) — novas migrações partem de cabeça única, sem conflito de heads.

## IDs Doity encontrados

**Nenhum.** Não há `doity_event_id` persistido no servidor (env, scripts, histórico, cron, banco). Necessário o usuário fornecer:
- `doity_event_id` de **Gênero e Sexualidades 2026** → _pendente_
- `doity_event_id` de **Ouvidores de Vozes 2026** → _pendente_
- `DOITY_TOKEN` → _pendente_ (sem ele, nem `testar_doity.py` roda)

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

# Alembic (do dir de deploy, hoje na branch `feature/agente-atendimento`):
.venv/bin/python -m alembic current   # d4a1e7b3c920 — head do código é e7c4b1a60d38 (Nat), NÃO aplicada
.venv/bin/python -m alembic heads
```
⚠️ **Mantenha `--workers 1`.** Os 4 background tasks (chatbot scheduler, broadcast worker,
broadcast cleanup, campaign worker) rodam no lifespan do processo uvicorn; múltiplos workers
os **duplicariam**.

## Frontend — como é servido em produção
**systemd, não pm2.** Unit `mensageria-frontend.service` (`/etc/systemd/system/`, `enabled` no
boot), rodando como `ubuntu` em `WorkingDirectory=/home/ubuntu/mensageria-frontend`:

| Item | Valor |
|---|---|
| Comando | `pnpm start --port 3030` → `next start` (servidor Node, **não** export estático) |
| Node | v20.20.2 **do nvm** — `Environment=PATH=/home/ubuntu/.nvm/versions/node/v20.20.2/bin:...` |
| Porta | `Environment=PORT=3030`, escuta em `:3030` |
| Nginx | `location /` → `proxy_pass http://127.0.0.1:3030` (site `cenat`) |
| Log | `/var/log/mensageria-frontend.log` (`StandardOutput=append:`) — **não** journalctl |
| Restart | `Restart=always`, `RestartSec=5` |
| Stack | Next.js 14.2.35 (App Router), React 18, pnpm 10.33.0 |
| API base | `.env.local`: `NEXT_PUBLIC_API_URL=/api` → o browser chama o mesmo host, o nginx roteia |

⚠️ **`next start` serve o `.next` já buildado.** Mudou código do front, só reiniciar **não
adianta** — precisa `pnpm build` antes. O caminho do PATH importa: `pnpm` não está no PATH
padrão do root, então use o binário do nvm ou exporte o PATH.

⚠️ **Typecheck vale no build; ESLint não.** Desde a Etapa 0A dos funis (03/11/2026)
`typescript.ignoreBuildErrors` é `false` e o `tsc --noEmit` dá **0 erros** — erro de tipo
novo **quebra o `pnpm build`**. `eslint.ignoreDuringBuilds` segue `true` (código portado,
cheio de `any`). Para validar:
```bash
cd /home/ubuntu/mensageria-frontend
export PATH=/home/ubuntu/.nvm/versions/node/v20.20.2/bin:$PATH
./node_modules/.bin/tsc --noEmit          # tipos: tem que dar 0
./node_modules/.bin/eslint src/…          # lint por arquivo/dir
```
Os wrappers de `src/components/ui/` são **base-ui, não Radix**. `asChild` é aceito só nos
tipos (`LegacyAsChild`, `@deprecated`) e o base-ui o **ignora** — o filho é renderizado
dentro do trigger. Código novo usa `render={<Filho />}`. O `Select` tipa `onValueChange`
sem o `null` do base-ui (ver comentário em `ui/select.tsx`).

**Validar um build sem derrubar produção:** `next.config.mjs` respeita `NEXT_DIST_DIR`, então
```bash
NEXT_DIST_DIR=.next-verify pnpm build   # compila em .next-verify, o serviço segue no .next
```
Deploy de verdade = `pnpm build` (sem a var) + `sudo systemctl restart mensageria-frontend.service`.

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
Postgres 15, ~260 MB. Migrações Alembic (dir `alembic/`). **PROD está em `d4a1e7b3c920`**; o head do
código é `e7c4b1a60d38` (`channels.agent_profile`, da Nat) e **ainda não foi aplicado** — o
agente de IA foi implantado 29/07/2026; `feature/agente-ia` já foi mergeada e o dir de deploy está em `main`.
Tabelas principais: `channels`, `contacts`, `messages`, `chatbot_flows/sessions`,
`broadcast_jobs/logs`, `campaign_runs`, `pipelines`, `contact_lists`, `conversion_events`,
`meta_templates`, `instagram_automations`, `automation_flows/steps/executions`.
- `models.py` está consistente com o banco (`contact_tag_links` é tabela de associação sem classe).
- **Backup: existe, sim.** `scripts/backup_db.sh` roda por **cron diária às 03:00**
  (`0 3 * * * … >> /home/ubuntu/backups/backup.log`), dumpa só o schema `mensageria` e
  aplica retenção de 7 dias em `/home/ubuntu/backups/mensageria/`. **Ainda assim rode
  `bash scripts/backup_db.sh` à mão antes de migração** — a diária pode ser de até 24h atrás.

## Canais (estado atual)
- **6 — "Cenat - disparos"** — WhatsApp **official** (Meta Cloud), `operation_mode=ai`, ativo.
  🔴 **`agent_enabled=true` — o agente de IA atende cliente real por aqui desde 30/07/2026.** **Canal conversacional principal** (tem inbound). Nº no banco: +5511936235780 (⚠️ diverge do +5581995345775 citado externamente — confirmar `phone_number_id`).
- **9 — "comunicados"** — WhatsApp **evolution**, `operation_mode=ai`, ativo. Só disparo (0 inbound).
- **11 — "cenatsaudemental"** — Instagram, `operation_mode=none`. Recebimento de DM historicamente bloqueado (token de System User, precisa Page token).

## Convenções / avisos de produção
- **Timezone São Paulo (-03).** `Message.timestamp` é **UTC-3 naive**. Misturar com `timestamptz`
  **não erra 3h em silêncio — estoura**: o SQLAlchemy devolve datetime *aware* de coluna
  `timestamptz`, e usar esse valor para filtrar uma coluna naive faz o asyncpg lançar
  `DataError: can't subtract offset-naive and offset-aware datetimes`, matando a request inteira.
  Foi o bug que deixou o agente mudo a partir do 2º turno (migração `d4a1e7b3c920`).
  **Coluna que vai ser comparada com `messages.timestamp` tem que ser `DateTime` sem timezone.**
- **`wa_id`**: `contacts.wa_id`/`messages.contact_wa_id` = VARCHAR(100). Instagram usa prefixo `ig:`.
- **Instagram é um app Meta SEPARADO** do WhatsApp: `IG_APP_SECRET` ≠ `META_APP_SECRET`.
- Segredos vivem em `/home/ubuntu/mensageria/.env` (perm 600, `APP_ENV=production`). **Nunca imprimir valores.**
- `docconv:1` e `audioconv:1` são imagens docker build-à-mão (conversão de documento/áudio). Não some com elas.
- **Este repo NÃO tem git remote** — é deploy local. Hoje na branch `feature/agente-atendimento`
  (a Nat; ver seção própria). O GitHub é
  `git@github.com:linsalefe/cenat-mensage.git`, num **monorepo separado** em `~/evolution-api`,
  onde este dir corresponde ao subdir `mensageria/`. Os dois repos têm SHAs diferentes: o sync é
  por cópia de arquivos + commit local, não por histórico compartilhado.
  ```bash
  # publicar no GitHub (revise o dry-run antes; --delete apaga no destino)
  rsync -a --delete --dry-run --itemize-changes \
    --exclude=.git/ --exclude=.venv/ --exclude=.env --exclude=.env.* --exclude=__pycache__/ \
    --exclude=*.pyc --exclude=logs/ --exclude=uploads/ --exclude=node_modules/ \
    --exclude=.pytest_cache/ --exclude=*.log --exclude=.claude/ \
    /home/ubuntu/mensageria/ /home/ubuntu/evolution-api/mensageria/
  # ⚠️ --exclude=.env.* também exclui .env.example — copie ele à parte se mudou:
  cp /home/ubuntu/mensageria/.env.example /home/ubuntu/evolution-api/mensageria/.env.example
  cd /home/ubuntu/evolution-api && git add -A mensageria/ && git commit && git push origin main
  ```
  **Sempre** rode o dry-run e uma varredura de segredo no `git diff --cached` antes do push.
- Ponte Mensage→Customer (`CUSTOMER_RELAY_URL=https://cenatdata.online`): endpoints de relay
  retornaram **404** historicamente — best-effort, não derruba o fluxo, mas pode estar quebrada.

## Scripts úteis
- `scripts/create_admin.py` — cria usuário admin.
- `testar_doity.py` / `backfill_doity.py` — diagnóstico/backfill da API Doity.
  Leem `DOITY_TOKEN` e `DOITY_EVENTO_IDS` **do ambiente** (exportar ad-hoc). Base:
  `https://api.doity.com.br/public/v1`, endpoints `/eventos/{id}` e `/eventos/{id}/participantes`.
- `scripts/extrair_pos.py` → `scripts/seed_pos.py` — pipeline das pós (ver seção abaixo).
  Atualizar a base de pós = rodar os dois na ordem. **Não** edite preço à mão.
- `scripts/checar_promo_pos.py` — auditoria do catálogo do agente (pós **e** congressos).
  Pós: confere que tool e filtro de vigência concordam e que promo vencida não deixa rastro no
  investimento nem na allowlist do guardrail. Congressos: alerta lote com `active=true` cujo
  `lot_deadline` já passou (dessincronia com a Doity — o preço anunciado fica errado), lote ativo
  sem prazo, congresso sem lote ativo e sync parado (>6h).
  Flags: `--data YYYY-MM-DD` simula uma data sem esperar o relógio · `--esperar-zero` exige 0 promo
  visível · `--so pos|congresso|tudo`. Exit 0 = consistente, 1 = achou problema.
  ⚠️ O nome do arquivo ficou estreito (cobre congresso também) — mantido para não quebrar a unit.

## Auditoria diária do catálogo (systemd timer)
`mensageria-promo-check.timer` → `.service` roda `scripts/run_promo_check.sh` **todo dia às 00:20**
(TZ do host = America/Sao_Paulo), com `Persistent=true` (se a máquina estiver desligada, roda no
próximo boot). Log persistente e com exit code em **`/home/ubuntu/mensageria/logs/promo_check.log`**
(rotação simples: últimas 5000 linhas; `*.log` está no `.gitignore`).

**Exit 1 marca a unit como `failed` de propósito** — é o canal de alerta:
```bash
systemctl list-units --failed | grep promo-check     # achou problema no catálogo?
systemctl list-timers mensageria-promo-check.timer   # próximo disparo
tail -60 /home/ubuntu/mensageria/logs/promo_check.log
bash scripts/run_promo_check.sh                      # rodar à mão agora
```
Units em `/etc/systemd/system/mensageria-promo-check.{service,timer}`. Rodam como `ubuntu` com
`WorkingDirectory=/home/ubuntu/mensageria` — obrigatório, porque `app/config.py` usa
`env_file=".env"` (caminho relativo).

## 🧭 Hub de Funis — roadmap e regras
Objetivo: transformar o Mensage no **hub operacional dos funis de vendas** do CENAT (Low ticket,
Curso livre, Comunidade, Congressos, Pós com seminário pago como front end), **sem mudar
comportamento em produção** a cada etapa. Tudo em **[`docs/funis/`](docs/funis/)**: plano,
[ADR-001 (federada)](docs/funis/ADR-001-arquitetura-federada.md), glossário e relatórios.
Mensage = pessoa + jornada + automações · Dash = BI/mídia · Cenat Hub = Pós no Exact.

**Regras de execução** — ⚠️ as 7 do §7 do plano ainda não foram copiadas (o
`PLANO_IMPLEMENTACAO_FUNIS.md` está marcado PENDENTE). Até lá, as que regeram a 0A:
1. Cada etapa numa branch `feature/funis-<etapa>`, um commit por fase, mensagens em português.
2. Fase 0 é raio-x somente leitura; reportar antes de editar.
3. Nada de tocar `app/agent/`, `app/meta/`, `app/evolution/` ou `alembic/` fora de etapa que peça.
4. Migração e restart do `mensageria.service` só quando a etapa prevê — com backup antes.
5. Front: `tsc --noEmit` = 0 e build em `.next-verify` antes do build/restart reais.
6. Testes: escrever se fizer sentido, **não executar** pytest/npm test.
7. Push ao GitHub só depois do dry-run do rsync revisado e aprovado pelo Álefe.

| Etapa | Escopo | Status |
|---|---|---|
| 0A | typecheck verde, marca em `brand.ts`/`APP_NAME`, docs | ✅ 03/11/2026 (push pendente) |
| 0B | tabelas de funil/produto/touchpoint, `contacts.email/cpf`, `users.role`, seed dos 5 funis | ⏳ |
| 0C | nova sidebar e páginas `/funis`, `/funis/[slug]` | ⏳ |

## 🔴 Agente de IA — **ATIVO EM PRODUÇÃO desde 30/07/2026 16:31**
> **O agente responde CLIENTE REAL no canal 6 (WhatsApp oficial), sem sandbox.**
> `AGENT_TEST_WA_ALLOWLIST` está **vazia** (modo `🟢 AGENT PRODUÇÃO`) e
> `channels.agent_enabled=true` **apenas no canal 6**. Canais 9 e 11 seguem `false`.
> Antes de mexer em prompt, tools, guardrail, router ou seed, lembre que cada
> mudança vale para conversa real no próximo inbound — não há deploy a fazer.
> **Desligar na hora:** ver "Interruptores de EMERGÊNCIA" abaixo.
> **Acompanhar:** `bash scripts/turnos_agente.sh` (ver seção de monitoramento).

### Histórico — Fases 0–4 implantadas em 29/07/2026
Agente de vendas de congressos conforme `PLANO_AGENTE.md`. **Deploy em produção concluído**: o dir de
deploy está em `main` (feature/agente-ia mergeada), banco no head `d4a1e7b3c920`, serviço reiniciado (PID novo,
saudável). Naquele momento `agent_enabled=false` em todos os canais — **estado já superado: o
agente foi ativado no canal 6 em 30/07/2026, ver o bloco vermelho acima.**

**Módulo `app/agent/`:** `handler` (debounce 8s, gating de 5 condições, watermark de idempotência,
envio) · `loop` (OpenAI Responses + tool loop + guardrails + log de turnos) · `tools`/`tools_write`
(leitura + escrita sobre agent_products/Contact) · `prompt` · `router` · `doity` · `guardrails`
(entrada nano + saída determinística) · `workers` (sync 30min, conversão 5min, follow-up 60s).
Integração: `app/meta/routes.py::_process_inbound` (após commit, background, relay intacto).
### Evals (`tests/agent/eval_agent.py`) — 15 personas
```bash
.venv/bin/python tests/agent/eval_agent.py                 # suíte completa
.venv/bin/python tests/agent/eval_agent.py --only pos_tea  # uma persona
```
Roda contra a OpenAI real e o banco. **Não envia WhatsApp e não grava**: cada persona roda em
transação própria com rollback (o contato de teste é gravado com `flush` porque as tools de escrita
re-consultam pelo banco). Última medição (30/07/2026, com o 3º congresso): **3 rodadas completas 15/15, 14/15, 15/15**;
**portão determinístico 45/45 — alucinação de preço/link 0/15 em todas as rodadas.** A única
reprovação foi juiz DIVIDIDO (✔✘✘) numa persona de pós que passa nas outras duas rodadas.

Dois julgamentos independentes, com pesos diferentes:
- **Portão determinístico** (binário, sem voto, avaliado UMA vez): alucinação de preço/link via
  `check_output`, e as checagens de estado das personas de pós ([LEAD PÓS] na nota,
  `lead_status='interessado'`, `ai_active` intacto, sessão ainda `active`, link/landing exatos).
  Reprovam sozinhos, independentemente do juiz. **É a métrica que importa** — nunca afrouxe.
- **Juiz LLM** (subjetivo): roda 3x sobre a MESMA resposta e decide por maioria (`JUDGE_VOTOS=3`,
  ímpar para não empatar). Voto que falhar por exceção não conta como reprovação.

#### Taxonomia de falha — leia os votos ANTES de mexer em qualquer coisa
O padrão dos votos (`[✔✔✘]` no relatório) diz onde está o problema. Diagnosticar errado aqui custa
caro: leva a "consertar" o critério quando o defeito é do agente, o que esconde bug de produção.

| Padrão | Diagnóstico | O que fazer |
|---|---|---|
| **Unânime** `✘✘✘` | **Defeito de comportamento.** Sem oscilação do juiz, a resposta é claramente ruim. | Corrigir o **prompt/código**. Nunca o critério. |
| **Dividida, motivo CONSTANTE** `✘✘✔` sempre com a mesma queixa | **Defeito sutil** — real, mas em cima da linha. | Corrigir o **prompt**. Foi o caso de `estudante_sem_comprovante` (omitia o valor do lote perguntado → regra 8). |
| **Dividida, motivos VARIADOS** (ora "faltou X", ora "citou demais") | **Critério ambíguo** — o juiz não sabe o que você quer. | Corrigir a **redação do critério**. Foi o caso de `profissional_desconto`. |

Ler o campo `motivo_juiz` das reprovações é o atalho: **motivo repetido aponta o agente; motivo que
muda aponta o critério.** Uma persona que oscila de forma persistente tem como primeiro suspeito o
critério dela, **não** o número de votos — aumentar `JUDGE_VOTOS` mascara critério ambíguo em vez de
consertar, e por isso ficamos em 3.

Mudar critério de eval para fazer a suíte passar é o caminho mais curto para uma suíte inútil.
Só é legítimo quando a ambiguidade está mesmo na redação (e aí o comportamento exigido do agente
não muda) — e vale commit separado, dizendo por quê.

### Congressos (`agent_products.kind='congresso'`) — 3, sendo 1 PRESENCIAL
| slug | modalidade | datas | event_id | lote atual |
|---|---|---|---|---|
| `genero-2026` | online | 13 e 14/11/2026 | 296038 | 1º, até **31/07/2026** — 90/110/167 |
| `ouvidores-2026` | online | 04 e 05/12/2026 | 296665 | 1º, até 31/08/2026 — 90/110/197 |
| `curitiba-dh-2026` | **presencial** | 27, 28 e 29/08/2026 | 287503 | 3º, até **31/07/2026** — 220/250/347 |

Semear/atualizar: `.venv/bin/python scripts/seed_agent_products.py` (idempotente, upsert por slug).

⚠️ **`active` do ticket é do SEED, não da Doity.** O campo `ativo` da API significa "não
desabilitado", não "à venda hoje": em Curitiba as **três gerações de lote voltam `ativo=true`
juntas** (1º R$170, 2º R$200, 3º R$220). Cada produto declara `lotes_ativos` (conjunto de
`doity_lote_id`) e o sync preserva por id — igual já se fazia com `lot_deadline`, que a API manda
`null`. **Se isso quebrar, R$170 entra na base e, por tabela, na allowlist de preços do guardrail:
o agente cota preço de lote encerrado e o guardrail aprova.** Lote novo desconhecido entra
**inativo** e loga. Lote de valor **zero** é descartado (em Curitiba são 12 — 11 oficinas gratuitas
e o lote privado de organizadores).

- **MODALIDADE** vive em `policies.modalidade` e sobe ao topo do payload da tool. Presencial ganha
  `local` e `aviso_presencial`. A regra 9 do prompt obriga o agente a declarar sempre.
- **CENAT26** é desconto do **HOTEL** parceiro (Slaviero/Slim), nunca da inscrição — regra 11 do
  prompt e allowlist de cupons do guardrail. `slavierohoteis.com.br` **não** está na allowlist de
  links, de propósito: a base não guarda URL do hotel, e liberar o domínio deixaria o modelo
  inventar uma URL sob ele com o guardrail aprovando.
- **Submissão de trabalhos de Curitiba ENCERROU em 22/07/2026** — regra 12: informa a data, não
  promete exceção, emenda com a inscrição de participante, que segue aberta.
- ⚠️ **Programação e palestrantes de Curitiba NÃO estão semeados.** A landing é renderizada por JS e
  o conteúdo não existe no HTML servido; nada foi inferido. `get_event_schedule` degrada com aviso.
  Para semear, alguém precisa fornecer o conteúdo ou renderizar a página.

### Pós-graduações (`agent_products.kind='pos'`) — 13 cursos semeados 30/07/2026
Papel do agente na pós é **outro**: INFORMAR e DIRECIONAR ao comercial. Não vende, não gera link de
pagamento, não promete vaga. Ingresso é por **processo seletivo** (pré-aplicação → entrevista) e exige
**graduação concluída** (MEC). Fonte de verdade e pendências: `BASE_CONHECIMENTO_POS.md`.

- **Pipeline de dados:** `scripts/extrair_pos.py` baixa as 13 landings `pos*.cenatsaudemental.com` e
  grava `scripts/data/pos_extraido.json`; `scripts/seed_pos.py` (idempotente, upsert por slug) semeia
  a partir **só** desse JSON. Campo que a extração não confirma sai `null` + aviso — nada é inferido.
- **Colunas novas** (migração `c3f8d2a94b61`): `kind` (`congresso`|`pos`, default `congresso`),
  `promo` JSONB nullable, `info` JSONB. `checkout_url` virou **nullable** (pós não tem checkout).
- Pós entra com `checkout_url=NULL`, `doity_event_id=NULL` e `tickets=[]` **de propósito** — o preço
  vive em `info.investimento`, e o sync/polling da Doity filtram `kind='congresso'`.
- **Vigência de promo é determinística** (`app/agent/tools.py::_promo_vigente`): promo com
  `valido_ate` no passado é **invisível para o modelo**. As 13 promos vencem **31/07/2026** — a partir
  de 01/08 o agente passa a informar só o valor cheio. Renovar = atualizar `promo` (re-rodar o seed).
  ⚠️ Vencer a promo **também** tira `valor_promocional_a_vista` e `parcelamento` do investimento e
  esses valores saem da allowlist do guardrail — porque `preco_promo_avista_cents`/`parcela_cents`
  guardam o preço COM desconto (é assim que as landings anunciam). Só `preco_cheio_cents` e
  `parcela_cheia_cents` valem sempre. Auditar com `scripts/checar_promo_pos.py`.
- **Campos "em confirmação" não são devolvidos** ao modelo, só o motivo: início das 4 turmas com data
  vencida, a certificadora (não semeada) e o público-alvo da RAPS. Ver pendências abaixo.
- **Tool `encaminhar_comercial_pos`** ≠ `handoff_to_human`: é direcionamento ativo, **não desliga o
  agente** (`ai_active` e status da sessão intactos). Grava nota `[LEAD PÓS] {curso}: {resumo}` e
  `lead_status='interessado'`; devolve `wa.me/5511952137432`, o número por extenso, o e-mail
  `processoseletivo@cenatsaudemental.com` e a landing do curso. Achar leads de pós:
  `select * from mensageria.contacts where notes like '%[LEAD PÓS]%';`
- **Guardrail:** as 13 landings são cobertas por `cenatsaudemental.com` (regra de subdomínio);
  `https://wa.me/5511952137432` é liberado como link **exato** — o domínio `wa.me` segue bloqueado.

⚠️ **Pendências de conteúdo que travam funções específicas** (registradas com ⚠️ no MD):
1. **Certificadora não semeada.** As 13 landings dizem *Faculdade de São Marcos* (Portaria MEC
   1.371/2012); o briefing falava de CENSUPEG, que nas páginas só aparece em bio de docente. Decisão:
   não semear até confirmar → o agente diz "reconhecida pelo MEC / título de especialista" mas **não**
   cita a faculdade nem a portaria.
2. **4 turmas com início já vencido** (`suicidio-t3` 11/06, `psicologia-clinica-t2` 20/05,
   `alcool-drogas-t4` 23/05, `psicologia-hospitalar` 27/05). `inicio_confirmado=false` → o agente não
   informa data de início desses cursos.
3. **`gestao-t5` e `psicologia-hospitalar` sem valor total.** As páginas anunciam só a parcela
   (20x R$ 255; cheia R$ 340). Decisão: manter só a parcela — **não** multiplicar parcela por prazo.
4. **Landing da RAPS tem conteúdo da Psicologia Escolar** (público-alvo, FAQ "quem pode fazer" e CTA).
   Bug da página. Público não semeado e a FAQ contaminada foi removida no seed.
5. **Bônus vencido em Mulheridades** ("matrícula em junho → 6 supervisões, R$ 2.100") — não semeado.
6. **`pos-sm-trabalho-t3` com duração divergente** na própria página (13 vs 14 meses) →
   `duracao_confirmada=false`.

**Workers no lifespan:** sync (sempre; atualiza preços via Doity `/lotes`), conversão e follow-up
(**GATED por agent_enabled** — dormentes enquanto nenhum canal estiver ligado; zero efeito externo).

### MODO SANDBOX (`AGENT_TEST_WA_ALLOWLIST`) — testar no canal real sem risco
Allowlist de números de teste no `.env`, separados por vírgula, só dígitos com DDI.
**Vazia = produção** (gating normal). **Não-vazia = sandbox**: o agente atende SOMENTE esses
números; para qualquer outro contato o comportamento é idêntico a agente desligado (sem resposta,
sem sessão, sem log de turno). É o que permite ligar `agent_enabled=true` no **canal real (id 6)**
sem nenhum cliente ver o agente.

```bash
# 1) allowlist ANTES de ligar o canal
echo 'AGENT_TEST_WA_ALLOWLIST=5583999999999' >> .env
sudo systemctl restart mensageria.service
grep -a "AGENT SANDBOX\|AGENT PRODUÇÃO" /var/log/mensageria.log | tail -1   # confirmar o modo
# 2) só então ligar o canal
docker exec postgres psql -U evolution -d evolution \
  -c "update mensageria.channels set agent_enabled=true where id=6;"
```
⚠️ **A ordem importa:** allowlist + restart primeiro, canal depois. Invertido, existe uma janela
em que o agente atende cliente real. Para sair do sandbox: esvazie a variável e reinicie.

- O modo aparece no boot: `🧪 AGENT SANDBOX: N contato(s)` ou `🟢 AGENT PRODUÇÃO`. Cada inbound
  ignorado loga uma linha com o wa_id mascarado.
- Vale para o inbound **e** para o envio de follow-up/boas-vindas. Fora da allowlist o follow-up
  fica `pending` (não `skipped`) — sai quando a allowlist for esvaziada, não se perde.
- A **conversão por polling não é filtrada**: segue marcando `lead_status=ganho` e disparando CAPI
  (é passiva, não envia mensagem). Só o envio da boas-vindas é retido. Ou seja, em sandbox um
  comprador real ainda é registrado corretamente — ele só não recebe a mensagem.
- Comparação de número tolera a variação do 9º dígito BR e DDI implícito
  (`app/agent/phone.py`); `ig:` nunca casa com allowlist de telefone.
- Testes: `.venv/bin/python tests/agent/test_sandbox.py` (59 checagens, sem pytest).

### Teste de regressão de sessão (`tests/agent/test_dois_turnos.py`) — 16 checagens
```bash
.venv/bin/python tests/agent/test_dois_turnos.py
```
Roda **dois turnos seguidos na mesma sessão persistida** — o cenário que quebrou em produção no
primeiro teste real (30/07/2026) e que **nenhum eval pegava**. A cegueira é estrutural e vale
lembrar ao escrever teste novo: `eval_agent.py` chama `run_turn` direto, mas o watermark mora no
`handler._process`. Teste que não passa pelo `_process` não vê essa classe de bug.

**Toca o banco de propósito** (o defeito era de tipo de coluna, só aparece num round-trip real pelo
Postgres) e limpa as próprias linhas num `finally`, com `wa_id` dedicado `test:dois-turnos`. Não
chama OpenAI e não envia WhatsApp: `run_turn` e `_send` são substituídos por dublês.

### Como ATIVAR (ato deliberado — decisão humana)
1. **Confirmar o canal/número.** O agente atende o canal WhatsApp **official** (id 6). O nº no banco
   (+5511936235780) diverge do +5581995345775 das landings — confirme o `phone_number_id` antes.
2. **Sandbox primeiro** (rollout §7): use `AGENT_TEST_WA_ALLOWLIST` (seção acima) — é o mecanismo
   que torna esse passo seguro no canal real. Para ligar num canal:
   `UPDATE mensageria.channels SET agent_enabled=true WHERE id=<canal>;` (efeito imediato, sem deploy).
   Por contato: o gatilho exige `Contact.ai_active=true` (novos inbounds já nascem assim) e
   `not opted_out and not is_group`.
3. Monitore pelo painel (mensagens do agente têm `sent_by_ai=true`) e por `mensageria.agent_turn_logs`
   (tokens/latência/guardrail/custo por turno).

### 🚨 Interruptores de EMERGÊNCIA (desligam na hora, sem deploy e sem restart)
O handler relê esses flags **a cada inbound** — o efeito é imediato, não precisa reiniciar o
serviço nem esperar ciclo de worker. Em ordem do menos ao mais drástico:

```sql
-- 1. UM contato (a IA para de responder só ele; o resto segue)
UPDATE mensageria.contacts SET ai_active=false WHERE wa_id='55…';

-- 2. TUDO (mata o agente em produção inteira — é o botão vermelho)
UPDATE mensageria.channels SET agent_enabled=false WHERE id=6;
```
```bash
# 3. Voltar ao SANDBOX sem desligar (só números de teste são atendidos).
#    A ORDEM IMPORTA: allowlist primeiro, restart depois.
sed -i 's/^AGENT_TEST_WA_ALLOWLIST=.*/AGENT_TEST_WA_ALLOWLIST=5583999999999/' .env
sudo systemctl restart mensageria.service
grep -a "AGENT SANDBOX\|AGENT PRODUÇÃO" /var/log/mensageria.log | tail -1   # confirmar
```
Conferir o estado atual a qualquer momento:
```sql
SELECT id, name, agent_enabled FROM mensageria.channels ORDER BY id;
```
⚠️ Desligar o canal **não** encerra sessões abertas nem cancela follow-up já agendado — só
impede novos turnos. Para silenciar follow-up pendente:
`UPDATE mensageria.agent_followups SET status='skipped' WHERE status='pending';`

### Monitoramento dos turnos — `scripts/turnos_agente.sh`
```bash
bash scripts/turnos_agente.sh            # últimos 20 turnos (hora já em São Paulo)
bash scripts/turnos_agente.sh 50         # últimos 50
bash scripts/turnos_agente.sh 20 --erros # só turnos que estouraram, com traceback
bash scripts/turnos_agente.sh --resumo   # por hora nas últimas 24h: volume, erros,
                                         # guardrail barrado, tokens, latência média
bash scripts/turnos_agente.sh --seguir   # ao vivo, poll de 5s
```
Somente leitura. A coluna `guard` resume o turno: `ok` · `BARRADO` (guardrail vetou preço/link/
cupom e caiu no fallback) · `ERRO` (turno estourou — o traceback fica em `guardrail->>'traceback'`).

⚠️ **`agent_turn_logs.created_at` é naive UTC**, enquanto `messages.timestamp` é naive UTC-3.
O script já converte; se for consultar na mão, subtraia 3 horas ou os dois não batem.

### Pendências externas (não bloqueiam o deploy; bloqueiam FUNÇÕES específicas ao ativar)
- **Templates WABA dos follow-ups — APROVADOS, mas 2 na categoria ERRADA** (conferido 30/07/2026).
  São usados **só** quando o follow-up cai FORA da janela de 24h; dentro da janela o worker manda
  texto livre e não toca em template.

  | Template | Kind | Vars | Categoria | Aridade bate? |
  |---|---|---|---|---|
  | `lembrete_lote` | `lot_deadline` | 2 | ⚠️ **MARKETING** | ✅ |
  | `retomada_conversa` | *(fallback: `no_reply`, `abandoned_checkout`, `custom`)* | 1 | ⚠️ **MARKETING** | ✅ |
  | `boas_vindas_inscricao` | `welcome` | 1 | ✅ UTILITY | ✅ |

  A aridade confere com `TEMPLATE_BY_KIND`/`TEMPLATE_FALLBACK` em `app/agent/workers.py`, então não
  há risco do erro 132000 (a Meta rejeita quando o número de variáveis diverge).

  💸 **A categoria é onde está o dinheiro.** MARKETING é a faixa mais cara e a mais restrita em
  limite por usuário e em qualidade. E a distribuição é o inverso do desejável: o único UTILITY é o
  `welcome`, disparado só após **compra confirmada**; os dois MARKETING são justamente os que o
  **agente agenda por julgamento próprio**. Recategorizar os dois para UTILITY é a maior economia
  disponível — e é pedido na Meta, não mudança de código.

  🚫 **Nada está sendo entregue hoje:** a WABA segue com **pagamento restrito** (`131042 — Business
  eligibility payment issue`, visível em `/var/log/mensageria.log`). Enquanto isso durar, todo envio
  de template falha e o follow-up vira `skipped`. Aproveite a janela para arrumar a categoria: no dia
  em que o pagamento for regularizado, os dois MARKETING começam a sair e a cobrar sem aviso.

  ⚠️ `boas_vindas_inscricao` cobre um caso real: a conversão vem do **polling da Doity**, então a
  pessoa pode ter comprado pela landing sem falar no WhatsApp nas últimas 24h — e nesse caso não
  recebe a confirmação (`skipped`, visível no log `🤖📩 template '...' indisponível`). Nenhum kind
  fura a janela de 24h.

  ✅ **Opt-out do `retomada_conversa` agora funciona.** O corpo aprovado promete "responda SAIR", e
  até 30/07/2026 nada tratava isso no caminho do agente — `opt_out_keywords` só era lido pelo motor
  do CHATBOT (`operation_mode='chatbot'`), e o canal 6 está em `'ai'`. Hoje `handler.eh_opt_out`
  roda **antes do debounce**, marca `opted_out`, desliga `ai_active`, **cancela os follow-ups
  pendentes**, fecha a sessão e confirma. O casamento exige a mensagem INTEIRA ser a palavra — mais
  estrito que o do chatbot de propósito, que descadastraria quem escreveu "vou sair de casa".
  Testes: `.venv/bin/python tests/agent/test_opt_out.py` (30 checagens).
- **CAPI de conversão**: `META_DATASET_ID` e `META_CAPI_TOKEN` estão vazios → `fire_conversion` no-op
  (a conversão ainda marca `lead_status=ganho` e cancela follow-ups; só não envia o evento à Meta).
- Confirmar `doity_event_id` se novos congressos entrarem (descobrir via HTML da landing: `evento_id`).

## 🟡 Agente de ATENDIMENTO ("Nat") — código em `main`, **DESLIGADA** (19/10/2026)
> Segundo **perfil** do mesmo agente (`app/agent/`), não um app separado. Atende **só** o canal
> Evolution do atendimento. O agente de vendas do canal 6 segue exatamente como estava.
> Estado hoje: `AGENT_ATENDIMENTO_CHANNEL_ID` **vazio** → Nat desligada em qualquer canal.
> Branch `feature/agente-atendimento`, commit `73f8aff`. Migração `e7c4b1a60d38` **pendente**.

| Peça | Onde |
|---|---|
| Perfis | `app/agent/profiles.py` (`PERFIL_VENDAS`/`PERFIL_ATENDIMENTO`, `channel_profile`) |
| Coluna | `channels.agent_profile` `VARCHAR(20) NOT NULL default 'vendas'` (migração `e7c4b1a60d38`) |
| Prompt | `app/agent/prompt_atendimento.py` (persona da Nat; **não** é o `prompt.py` de vendas) |
| Base de conhecimento | `app/agent/kb/atendimento/*.md` + loader `app/agent/kb.py` |
| Gating | `handler.canal_bate_com_perfil` (trava dupla) + `handler.sandbox_allows(wa, perfil)` |
| Entrada | `app/evolution/routes.py::webhook` (MESSAGES_UPSERT → `agent_jobs` → pós-commit) |
| Testes | `tests/agent/test_atendimento.py` (~180 checagens, sem pytest) |

### Settings (`.env`)
```bash
AGENT_ATENDIMENTO_CHANNEL_ID=            # VAZIO = Nat desligada. id do canal Evolution dela.
AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST=     # sandbox PRÓPRIO; vazio = produção
AGENT_ATENDIMENTO_PAUSE_ON_HUMAN=true    # humano responde → ai_active=false naquele contato
AGENT_KB_INLINE_MAX_CHARS=15000          # acima disso a KB vira índice + tool buscar_base
```
⚠️ **Sandbox é por perfil e os dois são independentes.** Ligar o sandbox do atendimento **não**
coloca o canal 6 em sandbox. O boot imprime uma linha para cada perfil:
`🟢 AGENT PRODUÇÃO [vendas]` / `🧪 AGENT SANDBOX [atendimento]` / `⚪ AGENT ATENDIMENTO: ... desligada`.

### Trava dupla de canal (o que impede a Nat de responder onde não deve)
Além das 5 condições de sempre, `agent_should_handle` exige:
- perfil `atendimento` → `provider == 'evolution'` **E** `channel.id == AGENT_ATENDIMENTO_CHANNEL_ID`;
- perfil `vendas` → `provider == 'official'` (é o que o canal 6 já é);
- perfil desconhecido → **False** (fail-closed: typo na coluna cala o canal, não roda outro perfil).

Ou seja: ligar `agent_enabled=true` no canal 9 ("comunicados", 4.4 mil contatos que nunca falaram)
**não** faz a Nat responder — ele é barrado por id *e* por provider.

### Base de conhecimento — editar `.md` vale no próximo turno, sem restart
Loader com cache por assinatura (nome + mtime + tamanho), relido a cada turno. `_legado/` **não** é
carregado. Linha com `{{` sobrando é descartada com log (placeholder nunca chega ao modelo).
- **≤ `AGENT_KB_INLINE_MAX_CHARS`** → base INTEIRA no system prompt (hoje: 4089 chars, 10 chunks).
- **Acima** → só o índice (arquivos + seções) e a Nat ganha a tool `buscar_base`: BM25 léxico em
  Python puro (sem dependência nova), com stopwords PT-BR, plural encostado e sinônimos fixos
  (`certificado~certificação`, `reembolso~estorno~cancelamento`, `senha~acesso~login`, …).
  Sem resultado → `{"resultados": [], "aviso": "nada na base"}` → regra 4 do prompt manda handoff.
- O modo vai no `guardrail->>'kb_mode'` do `agent_turn_logs` (medir busca que volta vazia).

🚨 **A KB não tem preço, data, lote nem link de produto** — isso vive em `agent_products` e só sai
por tool, porque é a tool que alimenta a allowlist do guardrail de saída (regra de ouro §7.2). KB é
para política, procedimento e FAQ. A KB atual também **não cita a certificadora** (pendência 1).

### Tools da Nat (subconjunto)
Todas as de **leitura** do catálogo + escrita só `handoff_to_human`, `check_enrollment`,
`encaminhar_comercial_pos`, `save_lead_memory`. **Fora:** `schedule_followup` e
`update_lead_status` — e o executor **recusa** a chamada se o modelo chutar o nome. Sem esse portão,
um `schedule_followup` alucinado numa dúvida de certificado agendaria follow-up de **venda**, que
sairia por template pela WABA do canal 6.

### Comportamento no canal do atendimento
- **1º inbound ativa a IA.** Contato criado por disparo nasce `ai_active=False`; quem **nunca** falou
  (`last_inbound_at IS NULL`) passa a `True` ao escrever. Quem **já** falou e está `False` é decisão
  humana — respeitada.
- **Humano assumiu → IA pausa.** `fromMe` que não é eco da IA (painel ou celular do número) faz
  `ai_active=False` + log `👤 humano assumiu`. O botão do inbox devolve para a IA.
- **Anti-eco:** `handler.registrar_eco_ia` grava `(wa_id, texto normalizado)` com TTL 120s **antes**
  do envio. Sem isso a IA se auto-pausaria e — pior — o INSERT do webhook violaria a UNIQUE de
  `wa_message_id` quando o commit do handler chegasse, derrubando o lote inteiro daquele webhook.
  O registro **não** é consumido no match (o Evolution reentrega eventos).
- **Canal da conversa = último canal de ENTRADA** (nos dois webhooks). Contato é global por `wa_id`;
  assim o inbox responde pelo número em que a pessoa escreveu por último.
- **`@lid`:** `remoteJid` terminando em `@lid` resolve o telefone por `remoteJidAlt`/`senderPn`. Não
  resolveu → persiste normalmente mas **não** acorda o agente (log `⚠️ lid sem telefone`).
- **Sessão e watermark são por CANAL.** A mesma pessoa falando com vendas e com atendimento não
  mistura histórico nem dispara resposta duplicada.
- **Follow-up/boas-vindas nunca saem pelo atendimento:** `process_followups_once` só envia se o canal
  resolvido tiver `agent_profile='vendas'`; senão marca `skipped` com `🤖⏭️ follow-up retido`.

### Webhook do Evolution — ⚠️ nunca funcionou até aqui
O canal 9 tem **0 inbound** desde sempre, por **duas** barreiras independentes:
1. `EDUFLOW_WEBHOOK_URL=http://localhost:3020/...` — dentro do container, `localhost` é o próprio
   container. E o uvicorn escuta **só** em `127.0.0.1:3020`, então nem o gateway da bridge
   (`172.18.0.1`) alcança. A rota que funciona é a pública:
   `https://cenat.whatsflow.cloud/api/evolution/webhook` (testada do container: 405 = rota viva).
2. `WEBHOOK_SECRET` está setado e **nenhuma** das 14 instâncias manda o header → 403 em tudo.
   `create_instance` agora envia `X-Webhook-Secret` quando a var está preenchida.

⚠️ O container `evolution-api` é **compartilhado** com outros projetos (Cabide/`modasoft.online`,
EduFlow/`portal.eduflowia.com`, `Farmer`, `teste`). Trocar `EDUFLOW_WEBHOOK_URL` só afeta instância
**nova**; nenhuma existente é reconfigurada. E `create_instance` passou a **abortar** se o
`/instance/create` falhar (inclusive por nome duplicado), para um nome colidindo nunca sobrescrever
o `webhook/set` de outro projeto.

### Ativar (ordem obrigatória: allowlist → restart → canal)
```bash
# 0. ANTES de conectar o número: desligar a Nat antiga (Mega API + whatsapp-agent.service no EC2
#    antigo). Com os dois ligados em multi-device, a pessoa recebe DUAS respostas.
# 1. criar a instância pela tela Canais (QR com o celular do atendimento) → anotar o channel_id
echo 'AGENT_ATENDIMENTO_CHANNEL_ID=<ID>' >> .env
echo 'AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST=<NUM_TESTE>' >> .env
sudo systemctl restart mensageria.service
grep -a "AGENT SANDBOX\|AGENT PRODUÇÃO\|ATENDIMENTO" /var/log/mensageria.log | tail -3
# confirmar: vendas em PRODUÇÃO, atendimento em SANDBOX. SÓ então:
docker exec postgres psql -U evolution -d evolution \
  -c "update mensageria.channels set agent_profile='atendimento', agent_enabled=true where id=<ID>;"
```
Produção da Nat = esvaziar `AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST` + restart.

### Desligar a Nat (imediato, sem deploy)
```sql
-- um contato só
UPDATE mensageria.contacts SET ai_active=false WHERE wa_id='55…';
-- a Nat inteira (não toca no canal 6)
UPDATE mensageria.channels SET agent_enabled=false WHERE id=<ID>;
```
Ou esvaziar `AGENT_ATENDIMENTO_CHANNEL_ID` + restart (desliga a Nat em qualquer canal). ⚠️ A var
**vazia** é estado válido e tratada como `None` — um `field_validator` existe só para isso, porque
`int | None` com string vazia levantava `ValidationError` e **não subia o processo**.

### Pendências / sabidamente fora
- KB é a da Nat antiga, limpa — **revisar com a equipe de atendimento** é a próxima etapa.
- Sem frontend novo: o inbox já lista canal Evolution, roteia envio por `contact.channel_id`, tem
  toggle de IA e badge `sent_by_ai`. O banner de sandbox do inbox só conhece o de **vendas**.
- `ai_active` é **global por contato**: pausar no atendimento pausa vendas para a mesma pessoa.
  Separar exigiria `contact_channel_state`.
- Áudio da Nat não é transcrito (mídia vira "[a pessoa enviou um arquivo de mídia]").
- `turnos_agente.sh` não tem coluna de canal/perfil; `eval_agent.py` não tem persona de atendimento.
- Usuário do atendimento vê todos os canais no inbox (falta restrição por canal/role).

**Rollback do deploy** (se necessário): `git -C /home/ubuntu/mensageria checkout <commit-anterior>`
+ `sudo systemctl restart mensageria.service`. Pontos de retorno úteis: `705fa4d` (antes da Nat),
`0c28a32` (antes da expansão
de pós/sandbox) e `documentos-conversao-20260710` (antes do agente). O banco fica onde está
(`d4a1e7b3c920` hoje; `e7c4b1a60d38` depois que a migração da Nat for aplicada)
— as migrações do agente são **aditivas** (a única exceção relaxa `checkout_url` para nullable), então
o código antigo ignora as colunas e tabelas novas — inclusive `channels.agent_profile`, que o código
anterior à Nat simplesmente não lê. Backups em `/home/ubuntu/backups/mensageria/`.
⚠️ Voltar para antes de `c3f8d2a94b61` com as 13 pós semeadas exigiria removê-las primeiro: o
downgrade recoloca o `NOT NULL` em `checkout_url` e falha enquanto houver linha com valor nulo.

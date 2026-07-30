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
.venv/bin/python -m alembic current   # c3f8d2a94b61 (head)
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
Postgres 15, ~260 MB. Migrações Alembic (dir `alembic/`). **PROD está em `c3f8d2a94b61` (head)** — o
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

## Agente de IA (OpenAI) — Fases 0–4 IMPLANTADAS e DESATIVADAS (29/07/2026)
Agente de vendas de congressos conforme `PLANO_AGENTE.md`. **Deploy em produção concluído**: o dir de
deploy está na branch `feature/agente-ia`, banco no head `b2e5c9a1f7d0`, serviço reiniciado (PID novo,
saudável). **`channels.agent_enabled=false` em TODOS os canais → o agente NÃO responde ninguém ainda.**

**Módulo `app/agent/`:** `handler` (debounce 8s, gating de 5 condições, watermark de idempotência,
envio) · `loop` (OpenAI Responses + tool loop + guardrails + log de turnos) · `tools`/`tools_write`
(leitura + escrita sobre agent_products/Contact) · `prompt` · `router` · `doity` · `guardrails`
(entrada nano + saída determinística) · `workers` (sync 30min, conversão 5min, follow-up 60s).
Integração: `app/meta/routes.py::_process_inbound` (após commit, background, relay intacto).
### Evals (`tests/agent/eval_agent.py`) — 12 personas
```bash
.venv/bin/python tests/agent/eval_agent.py                 # suíte completa
.venv/bin/python tests/agent/eval_agent.py --only pos_tea  # uma persona
```
Roda contra a OpenAI real e o banco. **Não envia WhatsApp e não grava**: cada persona roda em
transação própria com rollback (o contato de teste é gravado com `flush` porque as tools de escrita
re-consultam pelo banco). Última medição: **3 rodadas completas 12/12, alucinação de preço/link 0/12,
108/108 votos do juiz concordantes.**

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

### Interruptores de EMERGÊNCIA (desligam na hora, sem deploy)
- Por canal: `UPDATE mensageria.channels SET agent_enabled=false WHERE id=...;`
- Por contato: `UPDATE mensageria.contacts SET ai_active=false WHERE wa_id=...;`

### Pendências externas (não bloqueiam o deploy; bloqueiam FUNÇÕES específicas ao ativar)
- **Templates WABA (3, categoria `utility`, idioma `pt_BR`)** — pendentes de criação **e** aprovação
  na Meta. São usados **só** quando o follow-up cai FORA da janela de 24h; dentro da janela o worker
  manda texto livre (grátis) e não toca em template. Enquanto não existirem/aprovarem, esses envios
  falham e o follow-up é marcado `skipped`. WABA está com pagamento restrito (ver memória
  `broadcast-template-state`), o que **também** bloqueia a entrega mesmo depois de aprovado.

  A **aridade tem que bater** com `TEMPLATE_BY_KIND`/`TEMPLATE_FALLBACK` em `app/agent/workers.py` —
  se o template aprovado tiver número diferente de variáveis, a Meta rejeita o envio (132000).

  | Template | Kind | Vars | Corpo sugerido |
  |---|---|---|---|
  | `lembrete_lote` | `lot_deadline` | 2 | `Oi! Passando pra lembrar que o lote atual do {{1}} vai até {{2}}. Se quiser garantir a sua vaga com o valor de agora, é só me chamar por aqui que eu te ajudo.` |
  | `retomada_conversa` | *(fallback: `no_reply`, `abandoned_checkout`, `custom`)* | 1 | `Oi! Ficamos de falar sobre o {{1}} e não quis deixar você sem resposta. Se ainda tiver interesse ou qualquer dúvida, é só responder por aqui.` |
  | `boas_vindas_inscricao` | `welcome` | 1 | `Olá! Sua inscrição no {{1}} está confirmada. Em breve você recebe por e-mail as orientações de acesso. Qualquer dúvida, é só responder por aqui.` |

  ⚠️ `boas_vindas_inscricao` cobre um caso real: a conversão vem do **polling da Doity**, então a
  pessoa pode ter comprado pela landing sem falar no WhatsApp nas últimas 24h. Sem esse template
  aprovado, **quem compra fora da janela não recebe a confirmação** (fica `skipped` — visível no log
  `🤖📩 template '...' indisponível`). Nenhum kind fura a janela de 24h.
- **CAPI de conversão**: `META_DATASET_ID` e `META_CAPI_TOKEN` estão vazios → `fire_conversion` no-op
  (a conversão ainda marca `lead_status=ganho` e cancela follow-ups; só não envia o evento à Meta).
- Confirmar `doity_event_id` se novos congressos entrarem (descobrir via HTML da landing: `evento_id`).

**Rollback do deploy** (se necessário): `git -C /home/ubuntu/mensageria checkout documentos-conversao-20260710`
+ `sudo systemctl restart mensageria.service`. O banco fica em `b2e5c9a1f7d0` (aditivo, o código antigo
ignora as colunas/tabelas novas). Backups em `/home/ubuntu/backups/mensageria/`.

# Relatório — Etapa E4a · E-mail transacional e disparos via Amazon SES (fundação)

**Data:** 22/11/2026 · **Branch:** `feature/funis-e4a-email-ses` (backend e frontend) ·
**Estado final:** deploy feito, módulo **inerte** (`EMAIL_ENABLED=false`). Push ao GitHub pendente.

## 1. Raio-x (Fase 0) e estado depois

| Item | Antes | Depois |
|---|---|---|
| `alembic current` | `f1b9d3e52a74 (head)` | `7c6e3d2e8fbc (head)` |
| Tasks no lifespan (`create_task`) | 7 | 8 (+ worker de e-mail) |
| `boto3` | ausente | 1.44.9 |
| `tsc --noEmit` (frontend) | 0 erros | 0 erros |
| `src/config/brand.ts` | existe | — (não alterado) |
| Serviços | ambos `active` | ambos `active` (PID backend 1814844 → 1962127) |

## 2. Migração e backup

- Backup antes da migração: `/home/ubuntu/backups/mensageria/mensageria-20261122-120800.sql.gz`
  (1,9 MB, `gzip -t` ok, 28 blocos `COPY mensageria.*`).
- `alembic upgrade head` aplicou **exatamente uma** revisão:
  `Running upgrade f1b9d3e52a74 -> 7c6e3d2e8fbc, E4a: canal de e-mail via Amazon SES …`.
- Antes de aplicar, o SQL foi revisado em modo offline (`--sql`): tudo aditivo. A única alteração em
  coluna existente é `contact_list_members.wa_id DROP NOT NULL`, protegida pelo
  `CHECK (wa_id IS NOT NULL OR email IS NOT NULL)`.
- Depois da migração: os 7.334 membros de lista estão intactos e 0 deles ficaram com `wa_id` nulo.

## 3. Arquivos por commit

**Backend** (`git log main..HEAD`):

| Commit | Arquivos |
|---|---|
| `ebc4a70` feat(email): settings, modelos e migração aditiva | `alembic/versions/7c6e3d2e8fbc_e4a_email_ses.py`, `app/config.py`, `app/models.py`, `app/broadcast/audience_resolver.py` (1 linha), `app/campaign/worker.py` (1 linha), `app/contact_lists/{csv_parser,routes}.py`, `app/payments/routes.py`, `pyproject.toml`, `uv.lock` |
| `9059c9d` feat(email): módulo SES | `app/email/{__init__,ses,unsubscribe,render,service,audience,worker,sns,routes,routes_public}.py`, `app/main.py`, `.env.example`, `tests/email/*` |
| `c6c2979` docs(email): runbook e CLAUDE.md | `docs/funis/EMAIL_SES.md`, `CLAUDE.md` |
| `5cca9f0` fix(deps): trava idna/jiter/tqdm | `uv.lock` |
| *(este)* docs: relatório e CLAUDE.md pós-deploy | `docs/funis/RELATORIO_ETAPA_E4A.md`, `CLAUDE.md` |

**Frontend:** `f6401d2` feat(email): página /email: `src/app/(app)/email/page.tsx`,
`src/lib/api-email.ts`, `src/components/app-sidebar.tsx`, `src/types/api.ts`, `src/app/(app)/listas/[id]/page.tsx`.

**Diretórios intocados:**
- `git diff --stat main -- app/agent app/meta app/evolution` → **vazio**.
- Em `alembic/` só entrou o arquivo novo.
- Em `app/broadcast/` só entrou a linha do filtro `wa_id IS NOT NULL`.

## 4. Deploy e smoke test

| Verificação | Esperado | Resultado |
|---|---|---|
| `GET 127.0.0.1:3020/health` | 200 | ✅ 200 `{"status":"ok","db":"connected"}` |
| log `📧` no boot | desligado | ✅ `📧 E-mail desligado (EMAIL_ENABLED=false)` |
| `POST /api/email/sns -d '{}'` | 403 | ✅ 403 (+ log `📧 SNS: assinatura inválida`) |
| `GET /api/email/unsubscribe?t=xxx` | 400 | ✅ 400 (também pelo domínio público, via nginx) |
| `POST /api/email/unsubscribe?t=xxx` | 400 | ✅ 400 |
| `GET /api/email/status` sem token | 401 | ✅ 401 |
| `import app.agent` (+ handler, loop) | ok | ✅ |
| Traceback nos ~2 min após o restart | 0 | ✅ 0 em 32 linhas novas |
| Agente canal 6 (`turnos_agente.sh`) | normal | ✅ 34 turnos / 7 dias, 0 erro; não houve inbound desde o restart (o último foi em 20/11), então ainda nenhum turno real pós-restart |
| Frontend `pnpm build` real + restart | 200 | ✅ `/email`, `/login` e `/` respondem 200 local; `/email` responde 200 também público |

Antes do build real rodei `tsc --noEmit` (0 erros) e o build em `.next-verify`, que passou e foi
removido em seguida. O ESLint ficou limpo nos arquivos novos.

## 5. Incidente: `uv add` alterou a venv de produção

**O que aconteceu.** Ao rodar `uv add boto3 cryptography` na Fase 2, o `uv.lock` commitado estava
desatualizado: o `openai` estava no `pyproject.toml` (`>=2.0`) mas **não constava do lock**, porque
tinha sido instalado à mão. O uv então resolveu de novo e, como a `.venv` do repo **é a venv de
produção**, instalou:

| Pacote | Produção antes | Depois do `uv add` | Hoje (travado) | Fonte do "antes" |
|---|---|---|---|---|
| `openai` | 2.50.0 | **3.57.0** (major) | 2.50.0 | saída do `uv sync` (`- openai==2.50.0`) |
| `idna` | 3.12 | 3.20 | 3.12 | lock da `main` |
| `jiter` | 0.16.0 | 0.19.0 | 0.16.0 | **inferida** pelo cache do uv (instalação de 29/07); **não** confirmada pelo lock, que não listava o pacote |
| `tqdm` | 4.70.0 | 4.70.1 | 4.70.0 | saída do `uv sync` |

**Impacto.** Nenhum em produção. Não houve restart enquanto a venv tinha as versões novas, e o
processo em execução seguia com os módulos já carregados. O `openai` 3.x ficou na venv por cerca de
1 minuto, e `idna`/`jiter`/`tqdm` até o commit `5cca9f0`, sempre antes do restart da Fase 6.

**Correção.** Rodei `uv lock --upgrade-package openai==2.50.0` (dentro do `ebc4a70`) e depois
`uv lock --upgrade-package idna==3.12 --upgrade-package jiter==0.16.0 --upgrade-package tqdm==4.70.0`
(no `5cca9f0`), seguidos de `uv sync`. A verificação final deu:
- `openai 2.50.0 · fastapi 0.136.0 · sqlalchemy 2.0.49 · httpx 0.28.1 · pydantic 2.13.3 · asyncpg 0.31.0`;
- `uv sync --locked --dry-run` → `Would make no changes`;
- diff de versões do lock da `main` contra o atual → **só adições**. Os pacotes novos são boto3,
  botocore, jmespath, s3transfer, python-dateutil e urllib3, mais openai, jiter, tqdm, distro e
  sniffio, que já estavam instalados mas faltavam no lock.

**Regra nova (registrada no `CLAUDE.md`, seção Python):** antes de qualquer `uv add`, rodar `uv lock`
com o lock atual e confirmar que `uv sync --locked --dry-run` não muda nada. Depois do add, comparar
as versões dos pacotes existentes: só pode haver adições. Se algum pacote existente mudou,
travá-lo com `--upgrade-package pkg==versão_antiga`.

## 6. O que o Álefe precisa fazer agora (em ordem)

1. **Console AWS** (Fase A do prompt / runbook §2): usuário IAM `mensage-ses` com política mínima,
   verificar remetente e 2–3 e-mails de teste, configuration set `mensage-prod` com destino SNS
   `mensage-ses-events`.
2. **Preencher o `.env`** à mão: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `SES_FROM_EMAIL`, `SES_FROM_NAME`, `SES_REPLY_TO`, `SES_CONFIGURATION_SET`, `SES_SNS_TOPIC_ARN`,
   `EMAIL_UNSUBSCRIBE_SECRET`, `EMAIL_TEST_ALLOWLIST`. Manter `EMAIL_ENABLED=false` por enquanto.
3. **Ligar:** `EMAIL_ENABLED=true` → `sudo systemctl restart mensageria.service` → conferir o log
   `📧 Email worker started — SANDBOX (…)`.
4. **Testar** na página E-mail: "Enviar teste" para um endereço da allowlist deve dar `sent`; para
   um fora dela, `skipped/sandbox`.
5. **Criar a assinatura HTTPS do SNS** para `https://cenat.whatsflow.cloud/api/email/sns`. Conferir
   no log `📧 SNS: assinatura do tópico confirmada` e o status do teste virando `delivered`. Os
   endereços `*@simulator.amazonses.com` testam bounce e complaint.
6. **Entregar ao Pablo os 6 registros DNS** (3 DKIM, MX e TXT do MAIL FROM, DMARC `p=none`); a
   tabela está no runbook §3.
7. **Pedir production access.** Depois de aprovado: subir `EMAIL_DAILY_LIMIT` e
   `EMAIL_RATE_PER_SECOND` pelos valores do card, e só então esvaziar `EMAIL_TEST_ALLOWLIST` + restart.

## 7. Desvios das decisões (listados, não corrigidos)

1. **Filtro `wa_id IS NOT NULL` também em `app/campaign/worker.py`.** O campaign worker também lê
   `contact_list_members`; sem o filtro, uma campanha de WhatsApp tentaria enviar para um membro só-e-mail.
2. **A cota conta `sent, delivered, bounced, complained`** em vez de só `sent, delivered`. O SES
   conta o envio, não a entrega; contar menos deixaria o worker ultrapassar a cota real.
3. **O GET de descadastro já descadastra** (critério 6). Risco: scanners de link de e-mails
   corporativos fazem prefetch e podem descadastrar sem a pessoa clicar. Alternativa para avaliar:
   o GET mostra um botão "confirmar" e só o POST grava.
4. **Notificação de tópico ≠ `SES_SNS_TOPIC_ARN` também é ignorada**, não só a confirmação de assinatura.
5. **`send_one` recusa (`failed`) sem credencial AWS, sem `SES_FROM_EMAIL` ou sem
   `EMAIL_UNSUBSCRIBE_SECRET`**, nunca enviando sem link de descadastro. O boto3 **não** usa a cadeia
   padrão de credenciais da máquina, só o `.env`.
6. **Índice extra `ix_email_messages_sent_at`**, usado pela consulta de cota.
7. **`cryptography` declarada explicitamente** no `pyproject.toml` (aprovado na Fase 0).
8. **Testes seguem a convenção do repo** (scripts com `check()` e exit code, sem pytest).
   Foram escritos e não executados.
9. **Frontend:** além do previsto, `types/api.ts` e `listas/[id]/page.tsx` mudaram porque `wa_id`
   agora é nullable.

## 8. Achado fora do escopo: a Nat está LIGADA no canal 12

O boot (este e os dois anteriores) imprime
`🟢 AGENT PRODUÇÃO [atendimento]: allowlist vazia … Canal do atendimento: 12`, e no banco o canal 12
"Atendimento" (evolution) tem `agent_profile='atendimento'` e `agent_enabled=true`. O `.env` não
muda desde 19/10/2026. Ou seja, **a Nat atende cliente real no canal 12**, enquanto o `CLAUDE.md`
diz "DESLIGADA" e `AGENT_ATENDIMENTO_CHANNEL_ID` "vazio". Esta etapa **não** alterou esse estado
nem essa seção do `CLAUDE.md`; fica a decisão de qual dos dois está certo.

## 9. Pendências para a E4b

- Tabelas `email_sequences`, `email_sequence_steps`, `email_sequence_enrollments` e o worker que as
  avança, chamando `service.send_one` (a única porta de saída).
- Gatilhos:
  - compra de congresso: o sync da Doity vive em `app/agent/workers.py` e exige permissão explícita
    para tocar `app/agent/` ou extrair o sync;
  - cadastro de pós: ponte Cenat Hub → Mensage;
  - compra Hotmart: o webhook já grava `buyer.email` em `contacts.email`.
- Templates reutilizáveis e editor na UI.
- Decidir o item 3 da seção 7 (GET vs POST no descadastro).
- `turnos_agente.sh` sem coluna de canal (já listado na seção da Nat).
- 0C: mover "E-mail" para dentro de **Disparos** na sidebar nova.
- Frontend ainda fora do GitHub (pendência da 0A).

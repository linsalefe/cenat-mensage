# Runbook — E-mail via Amazon SES (Etapa E4a)

> Canal de e-mail próprio do Mensage. Código em `app/email/`, página `/email` no frontend.
> **Estado padrão: desligado** (`EMAIL_ENABLED=false`). Ligar, sair do sandbox e esvaziar a
> allowlist são **atos deliberados do Álefe**, nesta ordem.

## 1. Como funciona

```
página /email ─┐                                   ┌─► SES (us-east-1) ──► destinatário
               ├─► email_jobs ─► worker (8ª task) ─┤
POST /test ────┘                     │             └─► email_messages (status)
                                     ▼
                       service.send_one()  ← ÚNICA porta de saída
                       0. EMAIL_ENABLED?        não → 409 / job pausado
                       1. suprimido?            sim → skipped (suppressed)
                       2. fora da allowlist?    sim → skipped (sandbox)
                       3. cota 24h estourou?    sim → job paused_quota (retenta a cada 10 min)
                       4. config faltando?      sim → failed (nomes das vars no error)
                       5. SES SendEmail (Raw)   → sent + ses_message_id | failed

SES ─► SNS (tópico mensage-ses-events) ─► POST /api/email/sns
       Bounce permanente → email_suppressions(bounce)  + message=bounced
       Complaint         → email_suppressions(complaint) + message=complained
       Delivery          → message=delivered
       Reject            → message=failed

rodapé / List-Unsubscribe ─► GET|POST /api/email/unsubscribe?t=…
       → email_suppressions(unsubscribe) + contacts.email_opted_out=true
```

- Todo e-mail sai com `List-Unsubscribe: <URL>` e `List-Unsubscribe-Post: List-Unsubscribe=One-Click`
  (RFC 8058, exigido por Gmail/Yahoo para remetente em volume), `ConfigurationSetName` e a tag `job_id`.
- Se o HTML não tiver `{descadastro}`, o rodapé padrão é anexado. Placeholders: `{nome}`, `{email}`,
  `{descadastro}`. `text_body` vazio → gerado do HTML.
- Token de descadastro = `b64url(email).b64url(HMAC-SHA256(EMAIL_UNSUBSCRIBE_SECRET, email))`, **sem
  expiração**. ⚠️ Trocar o segredo invalida todos os links já enviados.
- O worker lê taxa e cota **do `.env`**, nunca do SES. A cota conta `email_messages` com
  `status IN (sent, delivered, bounced, complained)` nas últimas 24h (janela móvel).
- `Settings` é cacheado: **toda mudança no `.env` exige** `sudo systemctl restart mensageria.service`.

## 2. Pré-requisitos no console AWS (Álefe)

1. **IAM** — usuário `mensage-ses`, só com: `ses:SendEmail`, `ses:SendRawEmail`, `ses:GetAccount`,
   `ses:GetEmailIdentity`, `ses:ListEmailIdentities`.
2. **SES › Identities** — verificar por e-mail o remetente temporário e 2–3 endereços de teste
   (no sandbox o SES só entrega para endereços verificados).
3. **SES › Identities** — identidade do **domínio** de envio (sugestão `mail.<domínio>`), Easy DKIM
   2048 e Custom MAIL FROM `bounce.mail.<domínio>`. Gera os registros DNS da seção 3.
4. **SES › Configuration sets** — `mensage-prod`, event destination **SNS** → tópico novo
   `mensage-ses-events`, eventos `Send, Delivery, Bounce, Complaint, Reject`. Anotar o ARN.

## 3. Registros DNS (entregar ao Pablo)

| # | Tipo | Host | Valor | Origem |
|---|---|---|---|---|
| 1 | CNAME | `____________._domainkey.mail.<domínio>` | `____________.dkim.amazonses.com` | Easy DKIM |
| 2 | CNAME | `____________._domainkey.mail.<domínio>` | `____________.dkim.amazonses.com` | Easy DKIM |
| 3 | CNAME | `____________._domainkey.mail.<domínio>` | `____________.dkim.amazonses.com` | Easy DKIM |
| 4 | MX | `bounce.mail.<domínio>` | `10 feedback-smtp.us-east-1.amazonses.com` | MAIL FROM |
| 5 | TXT | `bounce.mail.<domínio>` | `"v=spf1 include:amazonses.com ~all"` | MAIL FROM |
| 6 | TXT | `_dmarc.mail.<domínio>` | `"v=DMARC1; p=none; rua=mailto:dmarc@<domínio>"` | DMARC |

Copie os valores exatos do console (os de 1–3 são únicos por identidade). Até o DNS publicar e o
DKIM ficar `SUCCESS`, o sandbox usa o remetente verificado por e-mail — o código não depende do DNS.
DMARC: começar em `p=none`; passar a `p=quarantine` depois de 2–4 semanas de relatórios limpos.

## 4. Preencher o `.env` (à mão, nunca colar valores em chat/log)

```
AWS_REGION  AWS_ACCESS_KEY_ID  AWS_SECRET_ACCESS_KEY
SES_FROM_EMAIL  SES_FROM_NAME  SES_REPLY_TO
SES_CONFIGURATION_SET=mensage-prod   SES_SNS_TOPIC_ARN
EMAIL_UNSUBSCRIBE_SECRET             # openssl rand -hex 32
EMAIL_TEST_ALLOWLIST=<e-mails de teste, separados por vírgula>
EMAIL_ENABLED=false                  # só vira true no passo 5
```

## 5. Smoke test (sandbox)

```bash
cd /home/ubuntu/mensageria
sed -i 's/^EMAIL_ENABLED=.*/EMAIL_ENABLED=true/' .env     # ou editar à mão
sudo systemctl restart mensageria.service
grep -a "📧" /var/log/mensageria.log | tail -3
# esperado: "📧 Email worker started — SANDBOX (N endereço(s) na allowlist), rate=1.0/s, limite=200/24h"
```
1. Página **E-mail** → card de status: identidade verificada, "Sandbox", cota. Se o card disser
   `ok=false`, o erro vem escrito (credencial, região, identidade).
2. **Enviar teste** para um endereço da allowlist → linha `sent` com `ses_message_id`.
3. Enviar teste para um endereço **fora** da allowlist → `skipped` / `sandbox` (prova o portão).

```sql
SELECT id, to_email, status, error, ses_message_id, sent_at, event_at
FROM mensageria.email_messages ORDER BY id DESC LIMIT 20;
```

## 6. Assinatura HTTPS do SNS (depois do deploy, com a rota no ar)

SNS › Topics › `mensage-ses-events` › **Create subscription**: protocolo **HTTPS**, endpoint
`https://cenat.whatsflow.cloud/api/email/sns`. Deixe "raw message delivery" **desligado** (a rota
espera o envelope SNS assinado).

A confirmação é automática **só** se o `TopicArn` for igual a `SES_SNS_TOPIC_ARN` — confira no log
`📧 SNS: assinatura do tópico confirmada`. Se aparecer `confirmação de tópico DESCONHECIDO ignorada`,
o ARN no `.env` não bate (corrigir + restart + "Request confirmation" no console).

Validar: reenviar um teste e ver o status virar `delivered` em ~1 min. Para testar bounce/complaint
sem queimar reputação, use o simulador do SES como destinatário (precisa estar na allowlist):
`bounce@simulator.amazonses.com` → `bounced` + supressão; `complaint@simulator.amazonses.com` →
`complained` + supressão; `success@simulator.amazonses.com` → `delivered`.

```sql
SELECT * FROM mensageria.email_suppressions ORDER BY created_at DESC LIMIT 20;
```

## 7. Sair do sandbox → produção (ato deliberado)

1. **SES › Account dashboard › Request production access** (texto sugerido no prompt da etapa;
   a AWS costuma responder em até 24h). Pré-requisito prático: DKIM `SUCCESS` e SNS funcionando.
2. Aprovado: o card de status mostra `Produção (SES)` e as cotas novas
   (`Max24HourSend`, `MaxSendRate`). Ajustar no `.env`, **com folga abaixo** dos valores do SES:
   `EMAIL_DAILY_LIMIT` e `EMAIL_RATE_PER_SECOND`. Restart.
3. Só então **esvaziar `EMAIL_TEST_ALLOWLIST`** + restart. O log passa a dizer `PRODUÇÃO (allowlist vazia)`.
4. Primeiro disparo real: lista pequena e conhecida; acompanhar bounce/complaint no card antes de
   crescer o volume. Bounce > 5% ou complaint > 0,1% colocam a conta do SES em revisão.

## 8. Interruptores

| Situação | Ação | Efeito |
|---|---|---|
| Parar **um** disparo | botão Cancelar em `/email` (`POST /api/email/jobs/{id}/cancel`) | imediato (checado a cada 20 destinatários) |
| Parar **tudo** | `EMAIL_ENABLED=false` + restart | worker dorme; teste/novo disparo → 409; jobs `running` voltam a `pending` no próximo boot ligado |
| Voltar ao sandbox | preencher `EMAIL_TEST_ALLOWLIST` + restart | só a allowlist recebe; resto vira `skipped/sandbox` |
| Bloquear um endereço | Supressões → adicionar (`manual`) | nunca mais recebe, em nenhum caminho |

Supressões por `bounce`/`complaint` **não** saem pela UI (só `manual`/`unsubscribe`) — reenviar
para elas é o que derruba a reputação do remetente. Remover na mão, se for mesmo preciso:
`DELETE FROM mensageria.email_suppressions WHERE email='…';`

## 9. Consultas úteis

```sql
-- disparos recentes
SELECT id, name, status, total_targets, sent_count, skipped_count, error_count, error_message
FROM mensageria.email_jobs ORDER BY id DESC LIMIT 10;
-- por que um disparo pulou gente
SELECT error, count(*) FROM mensageria.email_messages WHERE job_id = :id GROUP BY error;
-- cota consumida (a mesma conta que o worker faz)
SELECT count(*) FROM mensageria.email_messages
WHERE status IN ('sent','delivered','bounced','complained') AND sent_at >= now() - interval '24 hours';
-- contatos com e-mail (Hotmart grava buyer.email; CSV de lista aceita coluna email)
SELECT count(*) FILTER (WHERE email IS NOT NULL), count(*) FILTER (WHERE email_opted_out)
FROM mensageria.contacts;
```

## 10. Testes (escritos, não executados na E4a)

```bash
.venv/bin/python tests/email/test_unsubscribe.py
.venv/bin/python tests/email/test_render.py
.venv/bin/python tests/email/test_sns_signature.py     # certificado autoassinado, sem rede
.venv/bin/python tests/email/test_service_gating.py    # fakes, sem banco e sem SES
```

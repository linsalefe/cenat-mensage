# Relatório — Etapa 0A · Fundação técnica do Hub de Funis

Executada em 03/11/2026. Branch `feature/funis-0a-fundacao` nos dois diretórios
(backend e frontend), criada a partir de `main`.

## 1. Raio-x (Fase 0)

| Item | Valor |
|---|---|
| Host / IP | `ip-172-26-10-190` / `172.26.10.190` |
| Backend | `main` limpo, último commit `d667a55` |
| Frontend | `main` limpo, último commit `e8810db` |
| Alembic | `f1b9d3e52a74 (head)` — **banco no head do código** |
| Serviços | `mensageria.service` active · `mensageria-frontend.service` active |

⚠️ O `CLAUDE.md` estava desatualizado no alembic: dizia produção em `d4a1e7b3c920` e a
migração da Nat (`e7c4b1a60d38`) pendente. Na verdade ela já está aplicada, e também
a seguinte (`f1b9d3e52a74`, `messages_transcript`). Esta etapa **não** corrigiu esse
trecho (fora do escopo); fica para quem for mexer no banco na 0B.

## 2. Erros de tipo: 30 → 0

| Arquivo | Antes | Depois |
|---|---|---|
| `components/inbox/crm-panel.tsx` | 3 | 0 |
| `components/app-header.tsx` | 3 | 0 |
| `app/(app)/canais/page.tsx` | 3 | 0 |
| `components/chatbot/broadcast-inspector.tsx` | 2 | 0 |
| `components/campaign/start-campaign-dialog.tsx` | 2 | 0 |
| `app/(app)/usuarios/page.tsx` | 2 | 0 |
| outros 15 arquivos | 1 cada | 0 |

Os pontos de chamada **não foram editados**: toda a correção ficou nos wrappers,
no `tsconfig` e em duas declarações de tipo.

Diferente do que dizia o `CLAUDE.md` ("duas classes só"), eram **quatro** classes:

| Classe | Qtde | Correção | Runtime |
|---|---|---|---|
| `asChild` não existe nos Props do base-ui | 14 | tipo `LegacyAsChild` (`ui/legacy-props.ts`, `@deprecated`) em `Button`, `DropdownMenuTrigger`, `DropdownMenuItem`, `TooltipTrigger` | idêntico — o prop segue repassado e ignorado |
| `Select.onValueChange` recebe `string \| null` | 12 | `Select` virou wrapper fino que tipa o valor sem `null` | idêntico |
| TS2802 (iterar `Uint8Array` / `matchAll`) | 2 | `"target": "es2017"` no `tsconfig.json` (só typecheck; o build é SWC) | idêntico |
| Tipos divergentes | 2 | `SOURCE_COLOR` vira `Partial<Record<…>>`; `FlowKind` de `lib/workflow-validation` inclui `"campaign"` | idêntico — ver §5 |

`next.config.mjs`: `typescript.ignoreBuildErrors: false`. ESLint segue ignorado.

## 3. Arquivos alterados

**Frontend** (2 commits: `fix(types)` e `feat(brand)`):
`next.config.mjs`, `tsconfig.json`, `src/components/ui/{button,dropdown-menu,select,tooltip}.tsx`,
`src/components/ui/legacy-props.ts` (novo), `src/components/chatbot/edge-components.tsx`,
`src/lib/workflow-validation.ts`, `src/config/brand.ts` (novo), `src/app/layout.tsx`,
`src/components/brand/logo.tsx`, `src/app/login/page.tsx`, `src/app/(app)/usuarios/page.tsx`.

**Backend** (2 commits: `feat(brand)` e `docs(funis)`):
`app/config.py`, `app/main.py`, `CLAUDE.md`, `docs/funis/*`.

`git diff --stat main -- app/agent app/meta app/evolution alembic` → **vazio** (intocados).
Nenhuma migração e nenhum restart do `mensageria.service`.

`grep -rn "WhatsFlow" src/` → só `src/config/brand.ts:5`.

## 4. Build e publicação

- `tsc --noEmit` → 0 erros.
- `NEXT_DIST_DIR=.next-verify pnpm build` → ok (rodado nas Fases 2, 3 e 5); `.next-verify` removido.
- `pnpm build` + `sudo systemctl restart mensageria-frontend.service` → `active`, `Ready in 467ms`.
- HTTP 200 em `127.0.0.1:3030/login`, `/`, `/conversations`, `/canais` e em
  `https://cenat.whatsflow.cloud/login`.
- `<title>WhatsFlow</title>` e o `<h1>` do login (`Whats<span class="text-emerald-500">Flow</span>`) iguais ao anterior.

⚠️ **Backend:** `APP_NAME` só entra em vigor no **próximo restart** do `mensageria.service`,
que não fazia parte desta etapa. Efeito visível quando entrar: o título do OpenAPI
(`/docs`) muda de `mensageria` para `WhatsFlow`. Nenhuma rota muda.

## 5. Tipos que escondiam divergência de lógica (NÃO corrigida, só registrada)

Nenhum erro exigiu mudar lógica para passar. Três correções de tipo, porém, deixam
à vista uma divergência que já existia:

1. **`asChild` não funciona desde a migração para o base-ui.** Em 15 pontos o filho é
   renderizado *dentro* do trigger: `<button>` dentro de `<button>` nos `DropdownMenuTrigger`
   e `<a>` dentro de `<button>` no `Button asChild` e nos `DropdownMenuItem asChild` com `Link`.
   É HTML inválido e pode causar aviso de hidratação. Migrar para `render={<Filho />}`
   muda o DOM, então precisa de conferência visual. Sugestão: fazer na 0C, junto da sidebar nova.
2. **Edges de 7 tipos de nó novos** (`wait_for_reply`, `template_send`, `audience_trigger`,
   `trigger_schedule`, `audience`, `message_media`, `broadcast_send`) não têm cor própria e
   usam o fallback cinza `#94a3b8`. Escolher as cores é decisão visual.
3. **Fluxo `campaign` é validado como `chatbot`** em `validateFlow`. Hoje o editor só carrega
   `chatbot` ou `broadcast` (`workflows/[id]/page.tsx:138`), então não há efeito, mas uma
   validação própria de campanha não existe.

## 6. Pendências

- **`PLANO_IMPLEMENTACAO_FUNIS.md` é um placeholder.** O original não estava no servidor.
  Copiar o original por cima, e trocar as regras provisórias da seção do `CLAUDE.md`
  pelas 7 do §7.
- ADR-001: as opções A e C foram reconstruídas (a decisão B veio pronta). Validar contra o plano.
- Glossário: `MQL`, `cn_aid` (não existe no código) e cota diária marcados como pendentes.
- **Push para o GitHub não feito.** O dry-run do rsync ficou para revisão do Álefe.
- `CLAUDE.md`: corrigir o trecho do alembic (§1).
- Para a 0B: tabelas `products`, `funnels`, `funnel_stages`, `funnel_actions`,
  `funnel_events`, `contact_touchpoints`; `contacts.email`/`cpf`; `users.role`;
  seed dos 5 funis. Backup manual (`bash scripts/backup_db.sh`) antes da migração.
- Fora do escopo: ESLint no build; nginx `/webhook/` (legado 3010);
  README do Cenat Hub expondo segredos de produção (outro repositório — avisar).

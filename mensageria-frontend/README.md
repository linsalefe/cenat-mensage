# mensageria-frontend

Frontend Next.js do backend CENAT de mensageria.

## Stack

- Next.js 14 App Router + TypeScript
- Tailwind v3 + shadcn/ui
- React Flow (`@xyflow/react`) para o editor de workflows
- axios + sonner
- Node.js 20 via `nvm` (userspace, sem sudo)

## Setup local

```bash
nvm use 20
pnpm install
# ajuste .env.local (ver NEXT_PUBLIC_API_URL)
pnpm dev --port 3030
```

## Variáveis de ambiente

- `NEXT_PUBLIC_API_URL` — base da API (dev: `http://localhost:3020/api`; prod via nginx: `/api`)

## Build de produção

```bash
pnpm build
pnpm start --port 3030
```

## systemd (produção)

```bash
sudo systemctl status mensageria-frontend
sudo systemctl restart mensageria-frontend
tail -f /var/log/mensageria-frontend.log
```

## URLs finais

- `https://cenat.whatsflow.cloud/` — este frontend
- `https://cenat.whatsflow.cloud/api/` → mensageria (FastAPI, 127.0.0.1:3020)
- `https://cenat.whatsflow.cloud/legacy/` → painel antigo HTML (read-only)
- `http://13.221.209.242/` → painel antigo **intocado** (Evolution :8080 em `/api/`)

## Telas

| Rota | Descrição |
|---|---|
| `/login` | Autenticação JWT |
| `/canais` | Lista/cria/deleta instâncias Evolution, modo operacional (ai/chatbot/none) |
| `/workflows` | Lista de flows (CRUD) — badge Chatbot/Broadcast |
| `/workflows/[id]` | Editor React Flow com toggle Chatbot/Broadcast, catálogo filtrado por tipo, inspector dedicado para nós de broadcast |
| `/broadcasts` | Monitoramento de jobs (tabs pendentes/executando/concluídos/cancelados/falhos, drawer com logs + CSV) |
| `/conversations` | Inbox com polling 10s na thread aberta |
| `/contatos` | Lista + busca + drawer com últimas mensagens |

## Editor de broadcast (Fase 5.2)

1. Em `/workflows`, crie um fluxo novo.
2. No editor, clique no toggle "Broadcast" (topo da toolbar).
3. Arraste os 4 nós da paleta na ordem: `trigger_schedule → audience → message_media → broadcast_send`.
4. Configure cada nó no inspector à direita:
   - **Agendamento**: "executar imediatamente" ou data/hora (fuso `America/Sao_Paulo`).
   - **Audiência**: escolha o canal, tipo (`Todos os grupos` ou `Grupos selecionados`). Para selecionados, clique "Buscar grupos" e use "Selecionar todos" se quiser.
   - **Mensagem + Mídia**: texto + upload de imagem/áudio/vídeo/PDF (max 16 MB). Aceita `{nome}` e `{grupo_nome}` como variáveis.
   - **Disparar**: nome do job + intervalo anti-ban (1–300s) + "Criar job ao publicar".
5. Clique "Criar disparo" no topo direito. O job aparece em `/broadcasts` na aba "Pendentes".

**Limitações atuais:**
- A **execução dos jobs** ainda não está implementada no backend — jobs ficam em `pending` até a Fase 5.3 entregar o worker.
- Recorrência (envios repetidos) não está disponível — só envio único.
- Tipos de audiência `contacts_tag` e `csv` estão desabilitados na UI (planejados).

## Débito técnico conhecido

- `typescript.ignoreBuildErrors=true` e `eslint.ignoreDuringBuilds=true` em `next.config.mjs`.
  O editor foi portado de um projeto externo com muitos `any` — builda, mas não passa no strict typecheck.
- `node-inspector.tsx` referencia conceitos do EduFlow (Pipeline/User opts) que não existem neste backend; os selects correspondentes ficarão vazios até a Fase 4.

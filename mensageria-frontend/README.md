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
| `/workflows` | Lista de chatbot flows (CRUD) |
| `/workflows/[id]` | Editor React Flow com catálogo + inspector + simulador |
| `/conversations` | Inbox com polling 10s na thread aberta |
| `/contatos` | Lista + busca + drawer com últimas mensagens |

## Débito técnico conhecido

- `typescript.ignoreBuildErrors=true` e `eslint.ignoreDuringBuilds=true` em `next.config.mjs`.
  O editor foi portado de um projeto externo com muitos `any` — builda, mas não passa no strict typecheck.
- `node-inspector.tsx` referencia conceitos do EduFlow (Pipeline/User opts) que não existem neste backend; os selects correspondentes ficarão vazios até a Fase 4.

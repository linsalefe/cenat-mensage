# ⚡ WhatsFlow - Premium Messaging Platform

Sistema completo de gerenciamento de WhatsApp com Evolution API, painel administrativo, webhook para integração com agentes de IA e **disparo em massa**.

---

## 🚀 Instalação Rápida (Novo Servidor)
```bash
# 1. Baixar o projeto
git clone https://github.com/linsalefe/evolution-painel.git
cd evolution-painel

# 2. Executar instalação automatizada
chmod +x install.sh
./install.sh
```

O script vai:
- Instalar Docker, Python, Nginx
- Configurar Evolution API + PostgreSQL
- Criar webhook FastAPI com disparo em massa
- Configurar SSL (opcional)
- Gerar credenciais seguras

---

## 📋 Funcionalidades

| Recurso | Descrição |
|---------|-----------|
| ✅ Multi-instâncias | Gerencie múltiplos WhatsApp |
| ✅ QR Code | Conexão fácil via QR |
| ✅ Chat em tempo real | Envie e receba mensagens |
| ✅ Disparo em massa | CSV + mensagens personalizadas |
| ✅ Webhook | Integre com N8N, FastAPI, etc |
| ✅ Logs em tempo real | Acompanhe tudo |

---

## 🏗️ Arquitetura
```
┌─────────────────────────────────────────────────────────────────┐
│                         SERVIDOR                                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │    NGINX     │  │  Evolution   │  │   Webhook FastAPI     │ │
│  │    :80/443   │  │  API :8080   │  │   :5000               │ │
│  │              │  │              │  │                       │ │
│  │  • Painel    │  │  • WhatsApp  │  │  • Recebe mensagens   │ │
│  │  • Proxy     │  │  • Multi-dev │  │  • Disparo em massa   │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
│         │                 │                    │                │
│         └─────────────────┼────────────────────┘                │
│                           │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     PostgreSQL :5432                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📤 Disparo em Massa

### Formato do CSV
```csv
nome,numero
João Silva,5511999999999
Maria Santos,5511888888888
Pedro Costa,5511777777777
```

**Regras:**
- Header obrigatório: `nome,numero`
- Número com DDI (55 para Brasil)
- Sem espaços, parênteses ou hífens

### Variáveis disponíveis

| Variável | Descrição |
|----------|-----------|
| `{nome}` | Nome do contato |

**Exemplo de mensagem:**
```
Olá {nome}, tudo bem?

Estamos com uma promoção especial para você!
```

---

## 📡 API Endpoints

### Webhook

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/webhook` | Recebe eventos do WhatsApp |
| GET | `/messages` | Lista todas as mensagens |
| GET | `/messages/{numero}` | Mensagens de um número |
| GET | `/health` | Status do serviço |

### Disparo em Massa

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/disparo/start` | Inicia disparo |
| GET | `/disparo/status` | Status atual |
| POST | `/disparo/stop` | Para o disparo |

#### POST /disparo/start
```json
{
  "instance": "minha-instancia",
  "contacts": [
    {"nome": "João", "numero": "5511999999999"},
    {"nome": "Maria", "numero": "5511888888888"}
  ],
  "message": "Olá {nome}, tudo bem?",
  "interval": 3,
  "api_url": "http://localhost:8080",
  "api_key": "sua-api-key"
}
```

#### GET /disparo/status
```json
{
  "running": true,
  "total": 100,
  "sent": 45,
  "errors": 2,
  "progress": 47,
  "current_contact": "João (5511999999999)",
  "logs": [...]
}
```

---

## 🔧 Estrutura de Arquivos
```
evolution-api/
├── docker-compose.yml      # Evolution API + PostgreSQL
├── install.sh              # Script de instalação
├── CREDENCIAIS.txt         # Credenciais (gerado)
├── README.md               # Esta documentação
├── DEPLOY_GUIDE.md         # Guia detalhado
├── painel/
│   ├── index.html          # Interface web completa
│   └── login.html          # Tela de login
└── webhook/
    ├── main.py             # FastAPI + Disparo em massa
    └── messages.json       # Mensagens armazenadas
```

---

## 🛠️ Comandos Úteis
```bash
# Ver status de tudo
docker ps && sudo systemctl status webhook nginx

# Reiniciar todos os serviços
cd ~/evolution-api && docker-compose restart && sudo systemctl restart webhook nginx

# Ver logs do webhook
sudo journalctl -u webhook -f

# Ver logs da Evolution API
docker logs -f evolution-api

# Testar webhook
curl http://localhost:5000/health

# Testar Evolution API
curl http://localhost:8080/instance/fetchInstances -H "apikey: SUA_KEY"
```

---

## 📦 Requisitos do Servidor

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 2 GB | 4 GB |
| Disco | 20 GB SSD | 40 GB SSD |
| OS | Ubuntu 22.04 | Ubuntu 24.04 |

### Portas necessárias

| Porta | Uso |
|-------|-----|
| 22 | SSH |
| 80 | HTTP |
| 443 | HTTPS |
| 5000 | Webhook |
| 8080 | Evolution API |

---

## ☁️ Provedores Compatíveis

- ✅ AWS EC2 / Lightsail
- ✅ Google Cloud Platform
- ✅ DigitalOcean
- ✅ Vultr
- ✅ Linode
- ✅ Azure
- ✅ Oracle Cloud (Free Tier)
- ✅ Contabo
- ✅ Hostinger VPS

---

## 🔒 Segurança

1. **Troque a API Key** após instalação
2. **Configure firewall** (UFW)
3. **Use HTTPS** em produção
4. **Backup regular** do banco de dados

---

## 🆘 Troubleshooting

### Webhook não inicia
```bash
sudo journalctl -u webhook -n 50 --no-pager
```

### Evolution API erro
```bash
docker logs evolution-api --tail 50
```

### Nginx erro
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

### Permissão negada no Docker
```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

## 📄 Licença

Projeto privado - Todos os direitos reservados.

---

## 👨‍💻 Desenvolvido por

**Álefe** - WhatsFlow Platform

---

*Última atualização: Janeiro 2026*

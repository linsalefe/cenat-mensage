# �� WhatsFlow - Premium Messaging Platform

Sistema completo de gerenciamento de WhatsApp com Evolution API, painel administrativo e webhook para integração com agentes de IA.

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Requisitos](#requisitos)
4. [Instalação](#instalação)
5. [Configuração](#configuração)
6. [Uso do Painel](#uso-do-painel)
7. [API Reference](#api-reference)
8. [Webhook para Agentes](#webhook-para-agentes)
9. [Variáveis de Ambiente](#variáveis-de-ambiente)
10. [Comandos Úteis](#comandos-úteis)
11. [Troubleshooting](#troubleshooting)

---

## 🎯 Visão Geral

**WhatsFlow** é uma plataforma premium para gerenciamento de múltiplas instâncias de WhatsApp, permitindo:

- ✅ Criar e gerenciar múltiplas instâncias
- ✅ Conectar via QR Code
- ✅ Enviar e receber mensagens em tempo real
- ✅ Espelhar conversas no painel
- ✅ Configurar webhooks para agentes de IA (FastAPI, N8N, etc.)
- ✅ Credenciais por instância (estilo Z-API)

---

## 🏗️ Arquitetura
```
┌─────────────────────────────────────────────────────────────┐
│                        SERVIDOR                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   NGINX     │  │  Evolution  │  │  Webhook FastAPI    │ │
│  │   :80       │  │  API :8080  │  │  :5000              │ │
│  │             │  │             │  │                     │ │
│  │  /painel/   │  │  WhatsApp   │  │  Recebe mensagens   │ │
│  │  /webhook/  │  │  Multi-device│ │  Armazena JSON     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         │                │                   │              │
│         └────────────────┼───────────────────┘              │
│                          │                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   PostgreSQL                         │   │
│  │                   :5432                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Requisitos

- Ubuntu 22.04/24.04 LTS
- Docker e Docker Compose
- Python 3.10+
- Nginx
- 2GB RAM mínimo
- Portas: 80, 5000, 5432, 8080

---

## ��️ Instalação

### 1. Clone/Crie a estrutura
```bash
mkdir -p ~/evolution-api/{painel,webhook}
cd ~/evolution-api
```

### 2. Docker Compose (Evolution API + PostgreSQL)

Crie o arquivo `docker-compose.yml`:
```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: postgres
    restart: always
    environment:
      POSTGRES_USER: evolution
      POSTGRES_PASSWORD: evolution_pass_2024
      POSTGRES_DB: evolution
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  evolution-api:
    image: evoapicloud/evolution-api:v2.3.7
    container_name: evolution-api
    restart: always
    ports:
      - "8080:8080"
    environment:
      - SERVER_URL=http://SEU_IP:8080
      - DATABASE_ENABLED=true
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://evolution:evolution_pass_2024@postgres:5432/evolution
      - DATABASE_SAVE_DATA_INSTANCE=true
      - DATABASE_SAVE_DATA_NEW_MESSAGE=true
      - DATABASE_SAVE_MESSAGE_UPDATE=true
      - DATABASE_SAVE_DATA_CONTACTS=true
      - DATABASE_SAVE_DATA_CHATS=true
      - AUTHENTICATION_API_KEY=sua-chave-secreta
      - CACHE_REDIS_ENABLED=false
      - CACHE_LOCAL_ENABLED=true
      - CORS_ORIGIN=*
      - CORS_METHODS=GET,POST,PUT,DELETE
      - CORS_CREDENTIALS=true
    depends_on:
      - postgres

volumes:
  postgres_data:
```

Inicie os containers:
```bash
docker-compose up -d
```

### 3. Webhook FastAPI

Crie o arquivo `webhook/main.py`:
```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import os

app = FastAPI(title="WhatsFlow Webhook")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "messages.json"

def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_messages(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    event = payload.get("event", "")
    
    if event == "messages.upsert":
        data = payload.get("data", {})
        key = data.get("key", {})
        remote_jid = key.get("remoteJid", "")
        from_me = key.get("fromMe", False)
        message_content = data.get("message", {})
        
        text = message_content.get("conversation") or message_content.get("extendedTextMessage", {}).get("text", "")
        
        if text and remote_jid:
            number = remote_jid.replace("@s.whatsapp.net", "")
            messages = load_messages()
            
            if number not in messages:
                messages[number] = []
            
            messages[number].append({
                "text": text,
                "fromMe": from_me,
                "timestamp": datetime.now().isoformat()
            })
            
            save_messages(messages)
            print(f"[{'SENT' if from_me else 'RECEIVED'}] {number}: {text}")
    
    return {"status": "ok"}

@app.get("/messages")
async def get_messages():
    return load_messages()

@app.get("/messages/{number}")
async def get_messages_by_number(number: str):
    messages = load_messages()
    return messages.get(number, [])

@app.get("/health")
async def health():
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
```

Instale dependências:
```bash
pip3 install fastapi uvicorn
```

### 4. Serviço Systemd (24/7)
```bash
sudo tee /etc/systemd/system/webhook.service << 'EOF'
[Unit]
Description=WhatsFlow Webhook FastAPI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/evolution-api/webhook
ExecStart=/usr/bin/python3 /home/ubuntu/evolution-api/webhook/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

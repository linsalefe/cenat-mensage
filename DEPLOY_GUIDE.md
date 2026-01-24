# 🚀 WhatsFlow - Guia Completo de Deploy

## Tutorial Profissional para Implantação em Novos Servidores

---

## 📋 Sumário

1. [Pré-requisitos](#1-pré-requisitos)
2. [Preparação do Servidor](#2-preparação-do-servidor)
3. [Instalação do Docker](#3-instalação-do-docker)
4. [Deploy da Evolution API](#4-deploy-da-evolution-api)
5. [Configuração do Webhook](#5-configuração-do-webhook)
6. [Instalação do Painel](#6-instalação-do-painel)
7. [Configuração do Nginx](#7-configuração-do-nginx)
8. [Configuração de Segurança](#8-configuração-de-segurança)
9. [Testes e Validação](#9-testes-e-validação)
10. [Configuração de Domínio (Opcional)](#10-configuração-de-domínio-opcional)
11. [SSL/HTTPS com Let's Encrypt](#11-sslhttps-com-lets-encrypt)
12. [Backup e Manutenção](#12-backup-e-manutenção)
13. [Checklist Final](#13-checklist-final)

---

## 1. Pré-requisitos

### 1.1 Requisitos do Servidor

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 2 GB | 4 GB |
| Armazenamento | 20 GB SSD | 40 GB SSD |
| Sistema Operacional | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

### 1.2 Portas Necessárias

Libere as seguintes portas no firewall/security group:

| Porta | Protocolo | Uso |
|-------|-----------|-----|
| 22 | TCP | SSH |
| 80 | TCP | HTTP (Nginx) |
| 443 | TCP | HTTPS (SSL) |
| 5000 | TCP | Webhook API |
| 8080 | TCP | Evolution API |

### 1.3 Provedores Compatíveis

- ✅ AWS EC2
- ✅ Google Cloud Platform
- ✅ DigitalOcean
- ✅ Vultr
- ✅ Linode
- ✅ Azure
- ✅ Oracle Cloud (Free Tier)
- ✅ Contabo
- ✅ Hostinger VPS

---

## 2. Preparação do Servidor

### 2.1 Conectar via SSH
```bash
ssh -i sua-chave.pem ubuntu@IP_DO_SERVIDOR
```

### 2.2 Atualizar o Sistema
```bash
sudo apt update && sudo apt upgrade -y
```

### 2.3 Instalar Dependências Básicas
```bash
sudo apt install -y curl wget git nano htop unzip software-properties-common
```

### 2.4 Configurar Timezone (Brasil)
```bash
sudo timedatectl set-timezone America/Sao_Paulo
```

### 2.5 Criar Estrutura de Diretórios
```bash
mkdir -p ~/evolution-api/{painel,webhook}
cd ~/evolution-api
```

---

## 3. Instalação do Docker

### 3.1 Instalar Docker
```bash
curl -fsSL https://get.docker.com | sudo sh
```

### 3.2 Adicionar Usuário ao Grupo Docker
```bash
sudo usermod -aG docker $USER
```

### 3.3 Aplicar Permissões (Relogar ou executar)
```bash
newgrp docker
```

### 3.4 Instalar Docker Compose
```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 3.5 Verificar Instalação
```bash
docker --version
docker-compose --version
```

---

## 4. Deploy da Evolution API

### 4.1 Criar docker-compose.yml
```bash
cat > ~/evolution-api/docker-compose.yml << 'COMPOSE'
services:
  postgres:
    image: postgres:15-alpine
    container_name: postgres
    restart: always
    environment:
      POSTGRES_USER: evolution
      POSTGRES_PASSWORD: SUA_SENHA_POSTGRES_AQUI
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
      - SERVER_URL=http://IP_DO_SERVIDOR:8080
      - DATABASE_ENABLED=true
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://evolution:SUA_SENHA_POSTGRES_AQUI@postgres:5432/evolution
      - DATABASE_SAVE_DATA_INSTANCE=true
      - DATABASE_SAVE_DATA_NEW_MESSAGE=true
      - DATABASE_SAVE_MESSAGE_UPDATE=true
      - DATABASE_SAVE_DATA_CONTACTS=true
      - DATABASE_SAVE_DATA_CHATS=true
      - AUTHENTICATION_API_KEY=SUA_API_KEY_AQUI
      - CACHE_REDIS_ENABLED=false
      - CACHE_LOCAL_ENABLED=true
      - CORS_ORIGIN=*
      - CORS_METHODS=GET,POST,PUT,DELETE
      - CORS_CREDENTIALS=true
    depends_on:
      - postgres

volumes:
  postgres_data:
COMPOSE
```

### 4.2 ⚠️ IMPORTANTE: Personalizar Configurações

Edite o arquivo e substitua:
```bash
nano ~/evolution-api/docker-compose.yml
```

| Variável | Substituir por |
|----------|----------------|
| `IP_DO_SERVIDOR` | IP público do seu servidor |
| `SUA_SENHA_POSTGRES_AQUI` | Senha forte para o banco |
| `SUA_API_KEY_AQUI` | Chave de API segura |

**Dica para gerar senhas seguras:**
```bash
# Gerar senha para PostgreSQL
openssl rand -base64 24

# Gerar API Key
openssl rand -hex 32
```

### 4.3 Iniciar Containers
```bash
cd ~/evolution-api
docker-compose up -d
```

### 4.4 Verificar Status
```bash
docker ps
```

Saída esperada:
```
CONTAINER ID   IMAGE                              STATUS          PORTS
xxxx           evoapicloud/evolution-api:v2.3.7   Up X minutes    0.0.0.0:8080->8080/tcp
xxxx           postgres:15-alpine                 Up X minutes    0.0.0.0:5432->5432/tcp
```

### 4.5 Verificar Logs
```bash
docker logs -f evolution-api
```

Aguarde até ver: `HTTP Server listening on port 8080`

---

## 5. Configuração do Webhook

### 5.1 Instalar Python e Dependências
```bash
sudo apt install python3 python3-pip -y
pip3 install fastapi uvicorn
```

### 5.2 Criar Arquivo do Webhook
```bash
cat > ~/evolution-api/webhook/main.py << 'PYTHON'
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
PYTHON
```

### 5.3 Criar Serviço Systemd
```bash
sudo tee /etc/systemd/system/webhook.service << 'SERVICE'
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
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE
```

### 5.4 Ativar e Iniciar Serviço
```bash
sudo systemctl daemon-reload
sudo systemctl enable webhook
sudo systemctl start webhook
```

### 5.5 Verificar Status
```bash
sudo systemctl status webhook
```

---

## 6. Instalação do Painel

### 6.1 Criar Arquivo HTML
```bash
cat > ~/evolution-api/painel/index.html << 'HTML'
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsFlow — Premium Messaging Platform</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
</head>
<body>
    <!-- Cole aqui o conteúdo completo do index.html -->
    <h1>WhatsFlow</h1>
    <p>Substitua este arquivo pelo index.html completo do projeto.</p>
</body>
</html>
HTML
```

### 6.2 Copiar Painel Completo

**Opção A - Via SCP (do seu computador):**
```bash
scp -i sua-chave.pem index.html ubuntu@IP_DO_SERVIDOR:~/evolution-api/painel/
```

**Opção B - Via wget (se hospedado em algum lugar):**
```bash
wget -O ~/evolution-api/painel/index.html URL_DO_ARQUIVO
```

**Opção C - Copiar manualmente:**
```bash
nano ~/evolution-api/painel/index.html
# Cole o conteúdo completo e salve (Ctrl+O, Enter, Ctrl+X)
```

### 6.3 Ajustar Configurações no HTML

Edite o arquivo e altere os valores padrão:
```bash
nano ~/evolution-api/painel/index.html
```

Procure e substitua:
- `http://100.26.100.8:8080` → `http://IP_DO_SERVIDOR:8080`
- `http://100.26.100.8:5000` → `http://IP_DO_SERVIDOR:5000`
- `minha-chave-secreta-123` → `SUA_API_KEY_AQUI`

---

## 7. Configuração do Nginx

### 7.1 Instalar Nginx
```bash
sudo apt install nginx -y
```

### 7.2 Instalar Apache Utils (para autenticação)
```bash
sudo apt install apache2-utils -y
```

### 7.3 Criar Usuário de Acesso
```bash
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

Digite a senha quando solicitado.

### 7.4 Criar Configuração do Site
```bash
sudo tee /etc/nginx/sites-available/whatsflow << 'NGINX'
server {
    listen 80;
    server_name _;

    # Painel Web
    location /painel/ {
        alias /home/ubuntu/evolution-api/painel/;
        index index.html;
        auth_basic "WhatsFlow - Acesso Restrito";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }

    # Webhook API
    location /webhook/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health Check
    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }
}
NGINX
```

### 7.5 Ativar Site
```bash
sudo ln -sf /etc/nginx/sites-available/whatsflow /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

### 7.6 Ajustar Permissões
```bash
sudo chmod 755 /home/ubuntu
sudo chmod 755 /home/ubuntu/evolution-api
sudo chmod 755 /home/ubuntu/evolution-api/painel
sudo chmod 644 /home/ubuntu/evolution-api/painel/index.html
```

### 7.7 Testar e Reiniciar
```bash
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 8. Configuração de Segurança

### 8.1 Configurar Firewall (UFW)
```bash
sudo apt install ufw -y
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5000/tcp
sudo ufw allow 8080/tcp
sudo ufw --force enable
sudo ufw status
```

### 8.2 Criar Arquivo .gitignore
```bash
cat > ~/evolution-api/.gitignore << 'GITIGNORE'
# Dados sensíveis
.env
*.env

# Banco de dados local
*.json
messages.json

# Logs
*.log

# Sistema
.DS_Store
node_modules/

# Python
__pycache__/
*.pyc
venv/
GITIGNORE
```

### 8.3 Adicionar Mais Usuários ao Painel (Opcional)
```bash
# Adicionar novo usuário
sudo htpasswd /etc/nginx/.htpasswd novo_usuario

# Remover usuário
sudo htpasswd -D /etc/nginx/.htpasswd usuario_a_remover

# Listar usuários
cat /etc/nginx/.htpasswd
```

---

## 9. Testes e Validação

### 9.1 Verificar Todos os Serviços
```bash
echo "=== Docker Containers ===" && docker ps
echo ""
echo "=== Webhook Service ===" && sudo systemctl status webhook --no-pager
echo ""
echo "=== Nginx Service ===" && sudo systemctl status nginx --no-pager
```

### 9.2 Testar Evolution API
```bash
curl http://localhost:8080/instance/fetchInstances \
  -H "apikey: SUA_API_KEY_AQUI"
```

Resposta esperada: `[]` (array vazio) ou lista de instâncias.

### 9.3 Testar Webhook
```bash
curl http://localhost:5000/health
```

Resposta esperada: `{"status":"running"}`

### 9.4 Testar Painel Web

Acesse no navegador:
```
http://IP_DO_SERVIDOR/painel/
```

Faça login com usuário `admin` e a senha definida.

### 9.5 Teste Completo - Criar Instância

1. Acesse o painel
2. Digite um nome e clique em "+ Nova Instância"
3. Clique em "📷 QR Code"
4. Escaneie com WhatsApp
5. Verifique se status mudou para "Conectado"

---

## 10. Configuração de Domínio (Opcional)

### 10.1 Apontar DNS

No seu provedor de domínio, crie um registro A:

| Tipo | Nome | Valor |
|------|------|-------|
| A | @ | IP_DO_SERVIDOR |
| A | www | IP_DO_SERVIDOR |
| A | api | IP_DO_SERVIDOR |

### 10.2 Atualizar Nginx para Domínio
```bash
sudo tee /etc/nginx/sites-available/whatsflow << 'NGINX'
server {
    listen 80;
    server_name seudominio.com.br www.seudominio.com.br;

    location /painel/ {
        alias /home/ubuntu/evolution-api/painel/;
        index index.html;
        auth_basic "WhatsFlow - Acesso Restrito";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }

    location /webhook/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }
}
NGINX

sudo nginx -t && sudo systemctl restart nginx
```

### 10.3 Atualizar Evolution API
```bash
nano ~/evolution-api/docker-compose.yml
```

Altere `SERVER_URL` para:
```
- SERVER_URL=http://seudominio.com.br:8080
```

Reinicie:
```bash
cd ~/evolution-api && docker-compose down && docker-compose up -d
```

---

## 11. SSL/HTTPS com Let's Encrypt

### 11.1 Instalar Certbot
```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 11.2 Gerar Certificado
```bash
sudo certbot --nginx -d seudominio.com.br -d www.seudominio.com.br
```

Siga as instruções:
1. Digite seu email
2. Aceite os termos (A)
3. Escolha redirecionar HTTP para HTTPS (2)

### 11.3 Renovação Automática

O Certbot já configura renovação automática. Teste com:
```bash
sudo certbot renew --dry-run
```

### 11.4 Atualizar URLs para HTTPS

Atualize o painel HTML:
- `http://` → `https://`

Atualize o docker-compose.yml:
- `SERVER_URL=https://seudominio.com.br:8080`

---

## 12. Backup e Manutenção

### 12.1 Script de Backup
```bash
cat > ~/evolution-api/backup.sh << 'BACKUP'
#!/bin/bash

# Configurações
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/home/ubuntu/evolution-api"

# Criar diretório de backup
mkdir -p $BACKUP_DIR

# Backup dos arquivos
tar -czf $BACKUP_DIR/whatsflow_$DATE.tar.gz \
    -C $PROJECT_DIR \
    docker-compose.yml \
    painel/ \
    webhook/

# Backup do banco PostgreSQL
docker exec postgres pg_dump -U evolution evolution > $BACKUP_DIR/database_$DATE.sql

# Compactar banco
gzip $BACKUP_DIR/database_$DATE.sql

# Remover backups antigos (mais de 7 dias)
find $BACKUP_DIR -type f -mtime +7 -delete

echo "Backup concluído: $DATE"
BACKUP

chmod +x ~/evolution-api/backup.sh
```

### 12.2 Agendar Backup Diário
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * /home/ubuntu/evolution-api/backup.sh >> /home/ubuntu/evolution-api/backup.log 2>&1") | crontab -
```

### 12.3 Comandos de Manutenção
```bash
# Ver logs em tempo real
sudo journalctl -u webhook -f
docker logs -f evolution-api

# Reiniciar tudo
cd ~/evolution-api && docker-compose restart && sudo systemctl restart webhook nginx

# Verificar uso de disco
df -h

# Verificar uso de memória
free -h

# Limpar Docker
docker system prune -f
```

---

## 13. Checklist Final

### ✅ Servidor

- [ ] Ubuntu 22.04/24.04 instalado
- [ ] Sistema atualizado
- [ ] Timezone configurado

### ✅ Docker

- [ ] Docker instalado
- [ ] Docker Compose instalado
- [ ] Usuário no grupo docker

### ✅ Evolution API

- [ ] docker-compose.yml configurado
- [ ] Containers rodando
- [ ] API respondendo na porta 8080

### ✅ Webhook

- [ ] main.py criado
- [ ] Serviço systemd configurado
- [ ] Webhook rodando na porta 5000

### ✅ Painel

- [ ] index.html instalado
- [ ] Permissões corretas
- [ ] URLs configuradas

### ✅ Nginx

- [ ] Nginx instalado
- [ ] Site configurado
- [ ] Autenticação habilitada
- [ ] Serviço rodando

### ✅ Segurança

- [ ] Firewall configurado
- [ ] Portas corretas liberadas
- [ ] Senhas fortes definidas

### ✅ Testes

- [ ] Painel acessível
- [ ] Login funcionando
- [ ] Criar instância OK
- [ ] QR Code aparece
- [ ] Conexão WhatsApp OK
- [ ] Mensagens espelhadas

---

## 📞 Suporte

Em caso de problemas:

1. Verifique os logs:
```bash
docker logs evolution-api
sudo journalctl -u webhook -n 50
sudo tail -f /var/log/nginx/error.log
```

2. Reinicie os serviços:
```bash
cd ~/evolution-api
docker-compose restart
sudo systemctl restart webhook nginx
```

3. Verifique conectividade:
```bash
curl http://localhost:8080/health
curl http://localhost:5000/health
```

---

## 🎉 Conclusão

Parabéns! Seu WhatsFlow está configurado e pronto para uso.

**URLs de Acesso:**
- Painel: `http://IP_DO_SERVIDOR/painel/`
- API Evolution: `http://IP_DO_SERVIDOR:8080`
- Webhook: `http://IP_DO_SERVIDOR:5000`

**Credenciais Padrão:**
- Usuário: `admin`
- Senha: (definida durante instalação)

---

*Documento gerado em $(date +%Y-%m-%d)*
*WhatsFlow - Premium Messaging Platform*

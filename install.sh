#!/bin/bash

#===============================================================================
# WhatsFlow - Script de Instalação Automatizada
# Versão: 1.0.0
# Compatível com: Ubuntu 22.04/24.04 LTS
#===============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_banner() {
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║   ⚡ WhatsFlow - Premium Messaging Platform                   ║"
    echo "║   Instalação Automatizada                                     ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error() { echo -e "${RED}[ERRO]${NC} $1"; }

# Verificar se é root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        log_error "Não execute como root. Use um usuário normal com sudo."
        exit 1
    fi
}

# Coletar informações
collect_info() {
    echo ""
    log_info "Configuração inicial"
    echo "────────────────────────────────────────"
    
    # IP do servidor
    SERVER_IP=$(curl -s ifconfig.me)
    echo -e "IP detectado: ${GREEN}$SERVER_IP${NC}"
    read -p "Confirma este IP? (s/n): " confirm_ip
    if [ "$confirm_ip" != "s" ]; then
        read -p "Digite o IP do servidor: " SERVER_IP
    fi
    
    # Domínio (opcional)
    read -p "Usar domínio? (deixe vazio para usar IP): " DOMAIN
    if [ -z "$DOMAIN" ]; then
        DOMAIN=$SERVER_IP
        USE_SSL="n"
    else
        read -p "Configurar SSL com Let's Encrypt? (s/n): " USE_SSL
    fi
    
    # Gerar senhas
    POSTGRES_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
    API_KEY=$(openssl rand -hex 24)
    
    echo ""
    log_info "Configurações definidas:"
    echo "  • IP/Domínio: $DOMAIN"
    echo "  • SSL: $USE_SSL"
    echo "  • API Key: $API_KEY"
    echo ""
    read -p "Continuar com a instalação? (s/n): " confirm
    if [ "$confirm" != "s" ]; then
        log_warning "Instalação cancelada"
        exit 0
    fi
}

# Atualizar sistema
update_system() {
    log_info "Atualizando sistema..."
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y curl wget git nano htop unzip software-properties-common
    sudo timedatectl set-timezone America/Sao_Paulo
    log_success "Sistema atualizado"
}

# Instalar Docker
install_docker() {
    if command -v docker &> /dev/null; then
        log_success "Docker já instalado"
        return
    fi
    
    log_info "Instalando Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    log_success "Docker instalado"
}

# Criar estrutura
create_structure() {
    log_info "Criando estrutura de diretórios..."
    mkdir -p ~/evolution-api/{painel,webhook}
    cd ~/evolution-api
    log_success "Estrutura criada"
}

# Criar docker-compose
create_docker_compose() {
    log_info "Criando docker-compose.yml..."
    
    if [ "$USE_SSL" = "s" ]; then
        SERVER_URL="https://$DOMAIN:8080"
    else
        SERVER_URL="http://$DOMAIN:8080"
    fi
    
    cat > ~/evolution-api/docker-compose.yml << COMPOSE
services:
  postgres:
    image: postgres:15-alpine
    container_name: postgres
    restart: always
    environment:
      POSTGRES_USER: evolution
      POSTGRES_PASSWORD: $POSTGRES_PASS
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
      - SERVER_URL=$SERVER_URL
      - DATABASE_ENABLED=true
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://evolution:$POSTGRES_PASS@postgres:5432/evolution
      - DATABASE_SAVE_DATA_INSTANCE=true
      - DATABASE_SAVE_DATA_NEW_MESSAGE=true
      - DATABASE_SAVE_MESSAGE_UPDATE=true
      - DATABASE_SAVE_DATA_CONTACTS=true
      - DATABASE_SAVE_DATA_CHATS=true
      - AUTHENTICATION_API_KEY=$API_KEY
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
    
    log_success "docker-compose.yml criado"
}

# Instalar Python e dependências
install_python() {
    log_info "Instalando Python e dependências..."
    sudo apt install -y python3 python3-pip
    sudo /usr/bin/python3 -m pip install fastapi uvicorn httpx
    log_success "Python configurado"
}

# Criar webhook
# Baixar painel do GitHub
download_painel() {
    log_info "Baixando painel..."
    curl -sL "https://raw.githubusercontent.com/linsalefe/evolution-painel/main/painel/index.html" -o ~/evolution-api/painel/index.html
    
    # Atualizar URLs no painel
    sed -i "s|https://api.whatsflow.cloud:8080|http://$DOMAIN:8080|g" ~/evolution-api/painel/index.html
    sed -i "s|https://whatsflow.cloud/webhook|http://$DOMAIN/webhook|g" ~/evolution-api/painel/index.html
    sed -i "s|minha-chave-secreta-123|$API_KEY|g" ~/evolution-api/painel/index.html
    
    log_success "Painel configurado"
}

create_webhook() {
    log_info "Criando webhook FastAPI..."
    
    cat > ~/evolution-api/webhook/main.py << 'PYTHON'
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import os
import asyncio
import httpx
from typing import Optional
import uuid

app = FastAPI(title="Evolution Webhook")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "messages.json"

# ===== DISPARO EM MASSA - Estado Global =====
disparo_state = {
    "running": False,
    "total": 0,
    "sent": 0,
    "errors": 0,
    "logs": [],
    "current_contact": None,
    "job_id": None,
    "should_stop": False
}

def reset_disparo_state():
    global disparo_state
    disparo_state = {
        "running": False,
        "total": 0,
        "sent": 0,
        "errors": 0,
        "logs": [],
        "current_contact": None,
        "job_id": None,
        "should_stop": False
    }

def add_log(log_type: str, message: str):
    disparo_state["logs"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": log_type,
        "message": message
    })
    if len(disparo_state["logs"]) > 100:
        disparo_state["logs"] = disparo_state["logs"][-100:]

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

@app.post("/disparo/start")
async def start_disparo(request: Request):
    global disparo_state
    
    if disparo_state["running"]:
        return {"status": "error", "message": "Já existe um disparo em andamento"}
    
    data = await request.json()
    instance = data.get("instance")
    contacts = data.get("contacts", [])
    message = data.get("message", "")
    interval = data.get("interval", 3)
    api_url = data.get("api_url", "")
    api_key = data.get("api_key", "")
    
    if not instance:
        return {"status": "error", "message": "Instância não informada"}
    if not contacts:
        return {"status": "error", "message": "Nenhum contato informado"}
    if not message:
        return {"status": "error", "message": "Mensagem não informada"}
    if not api_url:
        return {"status": "error", "message": "URL da API não informada"}
    if not api_key:
        return {"status": "error", "message": "API Key não informada"}
    
    reset_disparo_state()
    job_id = f"disp_{uuid.uuid4().hex[:8]}"
    
    disparo_state["running"] = True
    disparo_state["total"] = len(contacts)
    disparo_state["job_id"] = job_id
    
    add_log("info", f"Disparo iniciado - {len(contacts)} contatos")
    
    asyncio.create_task(disparo_worker(instance, contacts, message, interval, api_url, api_key))
    
    return {
        "status": "started",
        "job_id": job_id,
        "total_contacts": len(contacts)
    }

@app.get("/disparo/status")
async def get_disparo_status():
    progress = 0
    if disparo_state["total"] > 0:
        progress = round((disparo_state["sent"] + disparo_state["errors"]) / disparo_state["total"] * 100)
    
    return {
        "running": disparo_state["running"],
        "total": disparo_state["total"],
        "sent": disparo_state["sent"],
        "errors": disparo_state["errors"],
        "progress": progress,
        "current_contact": disparo_state["current_contact"],
        "job_id": disparo_state["job_id"],
        "logs": disparo_state["logs"][-50:]
    }

@app.post("/disparo/stop")
async def stop_disparo():
    global disparo_state
    
    if not disparo_state["running"]:
        return {"status": "error", "message": "Nenhum disparo em andamento"}
    
    disparo_state["should_stop"] = True
    add_log("warning", "Solicitação de parada recebida...")
    
    return {
        "status": "stopping",
        "sent": disparo_state["sent"],
        "errors": disparo_state["errors"]
    }

async def disparo_worker(instance: str, contacts: list, message: str, interval: int, api_url: str, api_key: str):
    global disparo_state
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, contact in enumerate(contacts):
            if disparo_state["should_stop"]:
                add_log("warning", "Disparo interrompido pelo usuário")
                break
            
            nome = contact.get("nome", "")
            numero = contact.get("numero", "")
            
            disparo_state["current_contact"] = f"{nome} ({numero})"
            add_log("info", f"Enviando para {nome} ({numero})...")
            
            msg_personalizada = message.replace("{nome}", nome)
            
            try:
                url = f"{api_url}/message/sendText/{instance}"
                headers = {
                    "apikey": api_key,
                    "Content-Type": "application/json"
                }
                payload = {
                    "number": numero,
                    "text": msg_personalizada
                }
                
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 200 or response.status_code == 201:
                    disparo_state["sent"] += 1
                    add_log("success", f"✓ {nome} ({numero}) - Enviado")
                else:
                    disparo_state["errors"] += 1
                    add_log("error", f"✗ {nome} ({numero}) - Erro: {response.status_code}")
                    
            except Exception as e:
                disparo_state["errors"] += 1
                add_log("error", f"✗ {nome} ({numero}) - Erro: {str(e)}")
            
            if i < len(contacts) - 1 and not disparo_state["should_stop"]:
                add_log("info", f"Aguardando {interval}s...")
                await asyncio.sleep(interval)
    
    disparo_state["running"] = False
    disparo_state["current_contact"] = None
    
    total_enviados = disparo_state["sent"]
    total_erros = disparo_state["errors"]
    add_log("info", f"Disparo finalizado - Enviados: {total_enviados}, Erros: {total_erros}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
PYTHON
    
    log_success "Webhook criado"
}

# Criar serviço systemd
create_service() {
    log_info "Criando serviço systemd..."
    
    sudo tee /etc/systemd/system/webhook.service > /dev/null << SERVICE
[Unit]
Description=WhatsFlow Webhook FastAPI
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/evolution-api/webhook
ExecStart=/usr/bin/python3 /home/$USER/evolution-api/webhook/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

    sudo systemctl daemon-reload
    sudo systemctl enable webhook
    
    log_success "Serviço criado"
}

# Instalar Nginx
install_nginx() {
    log_info "Instalando Nginx..."
    sudo apt install -y nginx
    
    if [ "$USE_SSL" = "s" ]; then
        NGINX_CONFIG="
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    location / {
        root /home/$USER/evolution-api/painel;
        index index.html;
    }

    location /webhook/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}"
    else
        NGINX_CONFIG="
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        root /home/$USER/evolution-api/painel;
        index index.html;
    }

    location /webhook/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}"
    fi
    
    echo "$NGINX_CONFIG" | sudo tee /etc/nginx/sites-available/whatsflow > /dev/null
    sudo ln -sf /etc/nginx/sites-available/whatsflow /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    sudo chmod 755 /home/$USER
    sudo chmod 755 /home/$USER/evolution-api
    sudo chmod 755 /home/$USER/evolution-api/painel
    
    log_success "Nginx configurado"
}

# Configurar SSL
configure_ssl() {
    if [ "$USE_SSL" = "s" ]; then
        log_info "Configurando SSL..."
        sudo apt install -y certbot python3-certbot-nginx
        sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN
        log_success "SSL configurado"
    fi
}

# Configurar firewall
configure_firewall() {
    log_info "Configurando firewall..."
    sudo apt install -y ufw
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw allow 5000/tcp
    sudo ufw allow 8080/tcp
    sudo ufw --force enable
    log_success "Firewall configurado"
}

# Salvar credenciais
save_credentials() {
    log_info "Salvando credenciais..."
    
    cat > ~/evolution-api/CREDENCIAIS.txt << CREDS
╔═══════════════════════════════════════════════════════════════╗
║           WhatsFlow - Credenciais de Acesso                   ║
╚═══════════════════════════════════════════════════════════════╝

📅 Instalado em: $(date)

🌐 URLs de Acesso:
   • Painel: http://$DOMAIN/
   • API Evolution: http://$DOMAIN:8080
   • Webhook: http://$DOMAIN/webhook/

�� Credenciais:
   • API Key: $API_KEY
   • PostgreSQL User: evolution
   • PostgreSQL Pass: $POSTGRES_PASS

📋 Comandos Úteis:
   • Ver status: docker ps && sudo systemctl status webhook
   • Reiniciar tudo: cd ~/evolution-api && docker-compose restart && sudo systemctl restart webhook nginx
   • Ver logs webhook: sudo journalctl -u webhook -f
   • Ver logs evolution: docker logs -f evolution-api

⚠️  GUARDE ESTAS INFORMAÇÕES EM LOCAL SEGURO!
CREDS
    
    chmod 600 ~/evolution-api/CREDENCIAIS.txt
    log_success "Credenciais salvas em ~/evolution-api/CREDENCIAIS.txt"
}

# Iniciar serviços
start_services() {
    log_info "Iniciando serviços..."
    
    cd ~/evolution-api
    sg docker -c "docker-compose up -d"
    
    sudo systemctl start webhook
    sudo nginx -t && sudo systemctl restart nginx
    
    log_success "Serviços iniciados"
}

# Mostrar resultado final
show_result() {
    echo ""
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║   ✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!                        ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "📌 ${YELLOW}Acesse o painel:${NC} http://$DOMAIN/"
    echo -e "🔑 ${YELLOW}API Key:${NC} $API_KEY"
    echo ""
    echo -e "📄 Credenciais salvas em: ${GREEN}~/evolution-api/CREDENCIAIS.txt${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANTE: Faça logout e login novamente para usar Docker sem sudo${NC}"
    echo ""
}

# Executar instalação
main() {
    print_banner
    check_root
    collect_info
    update_system
    install_docker
    create_structure
    create_docker_compose
    install_python
    download_painel
    create_webhook
    create_service
    install_nginx
    configure_ssl
    configure_firewall
    save_credentials
    start_services
    show_result
}

main

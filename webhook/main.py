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
    """Reseta o estado do disparo para valores iniciais"""
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
    """Adiciona log com timestamp"""
    disparo_state["logs"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": log_type,
        "message": message
    })
    if len(disparo_state["logs"]) > 100:
        disparo_state["logs"] = disparo_state["logs"][-100:]

# ===== FUNÇÕES DE MENSAGENS =====
def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_messages(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== ENDPOINTS WEBHOOK =====
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

# ===== ENDPOINTS DISPARO EM MASSA =====
@app.post("/disparo/start")
async def start_disparo(request: Request):
    """Inicia o disparo em massa"""
    global disparo_state
    
    # Verificar se já existe um disparo em andamento
    if disparo_state["running"]:
        return {"status": "error", "message": "Já existe um disparo em andamento"}
    
    # Receber dados
    data = await request.json()
    instance = data.get("instance")
    contacts = data.get("contacts", [])
    message = data.get("message", "")
    interval = data.get("interval", 3)
    api_url = data.get("api_url", "")
    api_key = data.get("api_key", "")
    
    # Validar dados
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
    
    # Resetar estado e configurar
    reset_disparo_state()
    job_id = f"disp_{uuid.uuid4().hex[:8]}"
    
    disparo_state["running"] = True
    disparo_state["total"] = len(contacts)
    disparo_state["job_id"] = job_id
    
    add_log("info", f"Disparo iniciado - {len(contacts)} contatos")
    
    # Iniciar worker em background
    asyncio.create_task(disparo_worker(instance, contacts, message, interval, api_url, api_key))
    
    return {
        "status": "started",
        "job_id": job_id,
        "total_contacts": len(contacts)
    }

@app.get("/disparo/status")
async def get_disparo_status():
    """Retorna o status atual do disparo"""
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
        "logs": disparo_state["logs"][-50:]  # Últimos 50 logs
    }

@app.post("/disparo/stop")
async def stop_disparo():
    """Para o disparo em andamento"""
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

# ===== WORKER DE DISPARO =====
async def disparo_worker(instance: str, contacts: list, message: str, interval: int, api_url: str, api_key: str):
    """Worker que processa o disparo em background"""
    global disparo_state
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, contact in enumerate(contacts):
            # Verificar se deve parar
            if disparo_state["should_stop"]:
                add_log("warning", "Disparo interrompido pelo usuário")
                break
            
            nome = contact.get("nome", "")
            numero = contact.get("numero", "")
            
            disparo_state["current_contact"] = f"{nome} ({numero})"
            add_log("info", f"Enviando para {nome} ({numero})...")
            
            # Personalizar mensagem
            msg_personalizada = message.replace("{nome}", nome)
            
            # Enviar mensagem via Evolution API
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
            
            # Aguardar intervalo (exceto no último)
            if i < len(contacts) - 1 and not disparo_state["should_stop"]:
                add_log("info", f"Aguardando {interval}s...")
                await asyncio.sleep(interval)
    
    # Finalizar
    disparo_state["running"] = False
    disparo_state["current_contact"] = None
    
    total_enviados = disparo_state["sent"]
    total_erros = disparo_state["errors"]
    add_log("info", f"Disparo finalizado - Enviados: {total_enviados}, Erros: {total_erros}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

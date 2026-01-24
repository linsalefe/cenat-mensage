from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import os

app = FastAPI(title="Evolution Webhook")

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
        
        # Extrair texto da mensagem
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

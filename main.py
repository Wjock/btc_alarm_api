import os
import requests
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="BTC Alarm API")

# ---------------------------------------------------------
# Inicialização do Firebase Admin SDK
# ---------------------------------------------------------
FIREBASE_KEY_PATH = "firebase-key.json"
RENDER_KEY_PATH = "/etc/secrets/serviceAccountKey.json"

# Procura o arquivo localmente ou no caminho de segredos do Render
if os.path.exists(FIREBASE_KEY_PATH):
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK inicializado localmente.")
elif os.path.exists(RENDER_KEY_PATH):
    cred = credentials.Certificate(RENDER_KEY_PATH)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK inicializado no Render.")
else:
    print("AVISO: Credenciais do Firebase não encontradas. Notificações desativadas.")

# ---------------------------------------------------------
# Modelos de Dados (Pydantic)
# ---------------------------------------------------------
class TokenSchema(BaseModel):
    token: str

class AlarmSchema(BaseModel):
    target_price: float
    active: bool


# ---------------------------------------------------------
# Rotas da API
# ---------------------------------------------------------
@app.get("/")
def read_root():
    return {"status": "online", "message": "API BTC Alarm funcionando!"}


@app.post("/register-token")
def register_token(data: TokenSchema):
    """Registra o token FCM enviado pelo app Android"""
    device_tokens.add(data.token)
    return {"status": "sucesso", "registered_tokens": len(device_tokens)}


@app.post("/set-alarm")
def set_alarm(data: AlarmSchema):
    """Configura o valor de disparo do alarme"""
    alarm_settings["target_price"] = data.target_price
    alarm_settings["active"] = data.active
    return {"status": "sucesso", "config": alarm_settings}


@app.get("/check-price")
def check_price():
    """Consulta o preço do BTC/USD via Coinbase com backup na Kraken"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    current_price = None

    # Fonte 1: Coinbase
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", headers=headers, timeout=5)
        if r.status_code == 200:
            current_price = float(r.json()["data"]["amount"])
    except Exception:
        pass

    # Fonte 2: Kraken (Backup)
    if current_price is None:
        try:
            r = requests.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                current_price = float(data["result"]["XXBTZUSD"]["c"][0])
        except Exception:
            pass

    if current_price is None:
        raise HTTPException(status_code=500, detail="Erro ao buscar preço nas APIs públicas.")

    triggered = False
    
    if alarm_settings["active"] and current_price >= alarm_settings["target_price"]:
        triggered = True
        send_fcm_notification(current_price)

    return {
        "btc_price_usd": current_price,
        "target_price": alarm_settings["target_price"],
        "alarm_active": alarm_settings["active"],
        "triggered": triggered
    }




def send_fcm_notification(price: float):
    """Envia a notificação Push via Firebase Cloud Messaging"""
    if not device_tokens:
        print("Nenhum token cadastrado para envio.")
        return

    for token in list(device_tokens):
        message = messaging.Message(
            notification=messaging.Notification(
                title="🚨 ALERTA BITCOIN! 🚨",
                body=f"O BTC atingiu a meta! Preço atual: US$ {price:,.2f}"
            ),
            token=token,
        )
        try:
            messaging.send(message)
            print(f"Notificação enviada com sucesso para o token: {token[:10]}...")
        except Exception as e:
            print(f"Erro ao enviar para o token {token[:10]}: {e}")

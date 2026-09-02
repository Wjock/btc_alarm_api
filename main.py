import os
import asyncio
import logging
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, messaging

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("btc_alarm")

app = FastAPI()

# Inicializa o Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK inicializado no Render.")

# Estado do Alarme em Memória
alarm_state = {
    "target_price": 0.0,
    "fcm_token": None,
    "is_active": False
}

class TokenRequest(BaseModel):
    token: String = None  # Aceita token do app

class AlarmRequest(BaseModel):
    target_price: float
    token: str

def get_btc_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        data = response.json()
        return float(data["bitcoin"]["usd"])
    except Exception as e:
        logger.error(f"Erro ao buscar preço do BTC: {e}")
        return None

def send_fcm_notification(token: str, title: str, body: str):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    channel_id='btc_alarm_channel'
                )
            ),
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Notificação enviada com sucesso: {response}")
    except Exception as e:
        logger.error(f"Erro ao enviar notificação FCM: {e}")

async def monitor_btc_loop():
    logger.info(">>> MONITOR AUTÔNOMO EM NUVEM INICIADO COM SUCESSO <<<")
    while True:
        if alarm_state["is_active"] and alarm_state["target_price"] > 0 and alarm_state["fcm_token"]:
            current_price = get_btc_price()
            if current_price:
                target = alarm_state["target_price"]
                logger.info(f"[Monitor Render 30s] Atual: USD {current_price:.2f} | Alvo: USD {target:.2f}")
                
                # Dispara se o preço cruzar a meta
                if current_price >= target:
                    logger.info("🎯 META ATINGIDA! Disparando notificação FCM...")
                    send_fcm_notification(
                        alarm_state["fcm_token"],
                        "🚨 ALERTA BITCOIN! 🚨",
                        f"O BTC atingiu USD {current_price:.2f} (Meta: USD {target:.2f})"
                    )
                    alarm_state["is_active"] = False
        else:
            logger.info("[Monitor Render 30s] Servidor ativo e aguardando alarme ser definido no app...")
        
        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor_btc_loop())

# Rota para o UptimeRobot e testes (Aceita GET e HEAD)
@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "ok", "message": "Servidor BTC Alarm Ativo"}

@app.post("/register-token")
def register_token(req: dict):
    token = req.get("token")
    if token:
        alarm_state["fcm_token"] = token
        logger.info(f"Token registrado com sucesso: {token[:10]}...")
        return {"status": "sucesso"}
    return {"status": "erro", "message": "Token ausente"}

@app.post("/set-alarm")
def set_alarm(req: AlarmRequest):
    alarm_state["target_price"] = req.target_price
    alarm_state["fcm_token"] = req.token
    alarm_state["is_active"] = True
    logger.info(f"Alarme definido para USD {req.target_price:.2f}")
    return {"status": "sucesso", "target_price": req.target_price}

@app.post("/stop-alarm")
def stop_alarm():
    alarm_state["is_active"] = False
    alarm_state["target_price"] = 0.0
    logger.info("Alarme cancelado pelo usuário.")
    return {"status": "sucesso"}
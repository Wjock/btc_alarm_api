# main.py
import os
import httpx
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import yfinance as yf

# Configuração de Logs para você ver o que acontece no painel do Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("btc_alarm")

app = FastAPI(title="BTC Alarm API")

# ---------------------------------------------------------
# CORREÇÃO: Inicialização de Variáveis Globais de Memória
# ---------------------------------------------------------
device_tokens = set()
alarm_settings = {"target_price": 0.0, "active": False}

# ---------------------------------------------------------
# Inicialização do Firebase Admin SDK
# ---------------------------------------------------------
FIREBASE_KEY_PATH = "firebase-key.json"
RENDER_KEY_PATH = "/etc/secrets/serviceAccountKey.json"

if os.path.exists(FIREBASE_KEY_PATH):
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK inicializado localmente.")
elif os.path.exists(RENDER_KEY_PATH):
    cred = credentials.Certificate(RENDER_KEY_PATH)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK inicializado no Render.")
else:
    logger.warning("AVISO: Credenciais do Firebase não encontradas. Notificações desativadas.")

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


def send_fcm_notification(price: float):
    """Envia a notificação Push via Firebase Cloud Messaging de forma segura"""
    if not device_tokens:
        logger.info("Nenhum token cadastrado para envio.")
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
            logger.info(f"Notificação enviada com sucesso para o token: {token[:10]}...")
        except Exception as e:
            logger.error(f"Erro ao enviar para o token {token[:10]}: {e}")


@app.get("/check-price")
async def check_price():
    """Consulta o preço do BTC de forma assíncrona, prevenindo Timeouts e Erros 500"""
    current_price = None

    # Fonte Principal: yfinance (Yahoo Finance)
    try:
        btc = yf.Ticker("BTC-USD")
        current_price = float(btc.fast_info["lastPrice"])
        logger.info(f"Preço obtido via Yahoo Finance: {current_price}")
    except Exception as yf_err:
        logger.warning(f"Yahoo Finance falhou ou sofreu Rate Limit: {yf_err}")

    # Backup de emergência: Coinbase (Corrigido com httpx e follow_redirects)
    if current_price is None:
        try:
            # Usando httpx assíncrono para não travar as outras rotas do app
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                r = await client.get(
                    "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                if r.status_code == 200:
                    current_price = float(r.json()["data"]["amount"])
                    logger.info(f"Preço obtido via Backup Coinbase: {current_price}")
        except Exception as cb_err:
            logger.error(f"Backup da Coinbase também falhou: {cb_err}")

    # Se ambas as fontes falharem no IP compartilhado do Render, devolvemos 502 de forma limpa
    if current_price is None:
        raise HTTPException(
            status_code=502,
            detail="Erro: Falha temporária ao obter preço via Yahoo Finance e Coinbase (Rate Limit na Nuvem)."
        )

    triggered = False
    active = alarm_settings.get("active", False)
    target_price = float(alarm_settings.get("target_price", 0.0))

    if active and current_price >= target_price:
        triggered = True
        # Bloco Try/Except isolado para o FCM. Se o Firebase falhar/demorar, a rota ainda responde sucesso.
        try:
            send_fcm_notification(current_price)
        except Exception as fcm_global_err:
            logger.error(fcm_global_err)

    return {
        "btc_price_usd": current_price,
        "target_price": target_price,
        "alarm_active": active,
        "triggered": triggered
    }


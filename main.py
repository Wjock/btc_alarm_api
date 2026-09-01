import os
import httpx
import logging
import asyncio
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configuração de Logs para acompanhamento no painel do Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("btc_alarm")

app = FastAPI(title="BTC Alarm API")

# Variáveis Globais de Memória
device_tokens = set()
alarm_settings = {"target_price": 0.0, "initial_price": 0.0, "active": False}

# Inicialização do Firebase Admin SDK
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

class TokenSchema(BaseModel):
    token: str

class AlarmSchema(BaseModel):
    target_price: float
    active: bool

@app.get("/")
def read_root():
    return {"status": "online", "message": "API BTC Alarm funcionando com Monitor Autônomo!"}

@app.post("/register-token")
def register_token(data: TokenSchema):
    device_tokens.add(data.token)
    logger.info(f"Token registrado. Total de tokens ativos: {len(device_tokens)}")
    return {"status": "sucesso", "registered_tokens": len(device_tokens)}

@app.post("/set-alarm")
async def set_alarm(data: AlarmSchema):
    # Obtém o preço atual para registrar a referência inicial (alta ou baixa)
    current_price = await obter_preco_btc() or data.target_price
    
    alarm_settings["target_price"] = data.target_price
    alarm_settings["initial_price"] = current_price
    alarm_settings["active"] = data.active
    
    logger.info(f"Novo alarme salvo no Render: Alvo={data.target_price} | Inicial={current_price} | Ativo={data.active}")
    return {"status": "sucesso", "config": alarm_settings}

def send_fcm_notification(price: float):
    """Envia notificação Push de Alta Prioridade para acordar o celular e tocar o alarme"""
    if not device_tokens:
        logger.info("Nenhum token cadastrado para envio.")
        return

    for token in list(device_tokens):
        message = messaging.Message(
            notification=messaging.Notification(
                title="🎯 ALVO ATINGIDO! 🎯",
                body=f"O BTC atingiu a meta! Preço atual: US$ {price:,.2f}"
            ),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    channel_id="btc_alarm_channel",
                    priority="high"
                )
            ),
            token=token,
        )
        try:
            messaging.send(message)
            logger.info(f"Notificação enviada com sucesso para o token: {token[:10]}...")
        except Exception as e:
            logger.error(f"Erro ao enviar para o token {token[:10]}: {e}")

async def obter_preco_btc():
    """Consulta a cotação spot na Coinbase pública"""
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(
                "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200:
                return float(r.json()["data"]["amount"])
    except Exception as e:
        logger.warning(f"Falha ao obter preço via Coinbase no Render: {e}")
    return None

async def monitor_loop():
    """Loop autônomo que vigia o preço no Render a cada 30 segundos"""
    logger.info("Iniciando loop autônomo de monitoramento em nuvem...")
    while True:
        try:
            active = alarm_settings.get("active", False)
            target_price = float(alarm_settings.get("target_price", 0.0))
            initial_price = float(alarm_settings.get("initial_price", 0.0))

            if active and target_price > 0.0:
                current_price = await obter_preco_btc()
                if current_price:
                    logger.info(f"[Monitor Nuvem] Atual: USD {current_price} | Alvo: USD {target_price}")
                    
                    # Verificação bidirecional: Alta ou Baixa
                    atingiu_alta = (target_price >= initial_price) and (current_price >= target_price)
                    atingiu_baixa = (target_price < initial_price) and (current_price <= target_price)

                    if atingiu_alta or atingiu_baixa:
                        logger.info("🚨 Alvo atingido! Disparando Push de Alta Prioridade...")
                        send_fcm_notification(current_price)
                        alarm_settings["active"] = False  # Desativa para evitar alertas repetidos
        except Exception as e:
            logger.error(f"Erro no loop de monitoramento: {e}")

        await asyncio.sleep(30)  # Checa a cada 30 segundos sem travar a API

@app.on_event("startup")
async def startup_event():
    """Dispara a tarefa autônoma em background na inicialização do servidor"""
    asyncio.create_task(monitor_loop())

@app.get("/check-price")
async def check_price():
    price = await obter_preco_btc()
    return {
        "btc_price_usd": price,
        "target_price": alarm_settings.get("target_price", 0.0),
        "alarm_active": alarm_settings.get("active", False)
    }
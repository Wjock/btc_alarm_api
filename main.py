import os
import httpx
import logging
import asyncio
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("btc_alarm")

# Variáveis Globais de Memória
device_tokens = set()
alarm_settings = {"target_price": 0.0, "initial_price": 0.0, "active": False}
background_tasks = set()

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
    logger.warning("AVISO: Credenciais do Firebase não encontradas.")

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

def send_fcm_notification(price: float):
    """Envia notificação Push com prioridade máxima e som de alarme"""
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
                    sound="alarm",  # Força o som de alarme do dispositivo
                    channel_id="btc_alarm_channel",
                    priority="high",
                    default_sound=True,
                    default_vibrate_timings=True
                )
            ),
            token=token,
        )
        try:
            messaging.send(message)
            logger.info(f"Notificação enviada com sucesso para: {token[:10]}...")
        except Exception as e:
            logger.error(f"Erro ao enviar para o token {token[:10]}: {e}")
            
            
async def monitor_loop():
    """Loop autônomo que roda permanentemente no servidor Render a cada 30s"""
    logger.info(">>> MONITOR AUTÔNOMO EM NUVEM INICIADO COM SUCESSO <<<")
    while True:
        try:
            active = alarm_settings.get("active", False)
            target_price = float(alarm_settings.get("target_price", 0.0))
            initial_price = float(alarm_settings.get("initial_price", 0.0))

            if active and target_price > 0.0:
                current_price = await obter_preco_btc()
                if current_price:
                    logger.info(f"[Monitor Render 30s] Atual: USD {current_price:.2f} | Alvo: USD {target_price:.2f}")
                    
                    atingiu_alta = (target_price >= initial_price) and (current_price >= target_price)
                    atingiu_baixa = (target_price < initial_price) and (current_price <= target_price)

                    if atingiu_alta or atingiu_baixa:
                        logger.info("🚨 ALVO ATINGIDO NO RENDER! Disparando Push urgente para o Android...")
                        send_fcm_notification(current_price)
                        alarm_settings["active"] = False
            else:
                logger.info("[Monitor Render 30s] Servidor ativo e aguardando alarme ser definido no app...")

        except Exception as e:
            logger.error(f"Erro no loop de monitoramento: {e}")

        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Garante que a tarefa assíncrona seja mantida viva na memória do servidor
    task = asyncio.create_task(monitor_loop())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    yield

app = FastAPI(title="BTC Alarm API", lifespan=lifespan)

class TokenSchema(BaseModel):
    token: str

class AlarmSchema(BaseModel):
    target_price: float
    active: bool

@app.get("/")
def read_root():
    return {"status": "online", "message": "API BTC Alarm com Monitor Ativo em NUVEM!"}

@app.post("/register-token")
def register_token(data: TokenSchema):
    device_tokens.add(data.token)
    logger.info(f"Token registrado. Total de tokens ativos: {len(device_tokens)}")
    return {"status": "sucesso", "registered_tokens": len(device_tokens)}

@app.post("/set-alarm")
async def set_alarm(data: AlarmSchema):
    current_price = await obter_preco_btc() or data.target_price
    alarm_settings["target_price"] = data.target_price
    alarm_settings["initial_price"] = current_price
    alarm_settings["active"] = data.active
    logger.info(f"Alarme ativo recebido do celular: Alvo={data.target_price} | Inicial={current_price}")
    return {"status": "sucesso", "config": alarm_settings}

@app.get("/check-price")
async def check_price():
    price = await obter_preco_btc()
    return {
        "btc_price_usd": price,
        "target_price": alarm_settings.get("target_price", 0.0),
        "alarm_active": alarm_settings.get("active", False)
    }
import os
import httpx
import logging
import asyncio
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Configuração de Logs com Data e Hora
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("btc_alarm")

# Inicialização do Firebase Admin SDK no Render
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK inicializado no Render.")
    except Exception as e:
        logger.error(f"Erro ao inicializar Firebase Admin SDK: {e}")

# Variáveis Globais de Memória
device_tokens = set()
alarm_settings = {"target_price": 0.0, "initial_price": 0.0, "active": False}
background_tasks = set()

# Função para enviar a notificação Push via Firebase FCM
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

# Função para consultar o preço do BTC na Coinbase
async def get_btc_price():
    url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
        return float(data["data"]["amount"])

# Loop de Monitoramento em Background
async def monitor_price():
    while True:
        try:
            if alarm_settings["active"] and alarm_settings["target_price"] > 0:
                current_price = await get_btc_price()
                target_price = alarm_settings["target_price"]
                initial_price = alarm_settings["initial_price"]

                logger.info(f"[Monitor Render 30s] Atual: USD {current_price:.2f} | Alvo: USD {target_price:.2f}")

                # Lógica de disparo: Subiu até o alvo OU caiu até o alvo
                triggered = False
                if initial_price < target_price and current_price >= target_price:
                    triggered = True
                elif initial_price > target_price and current_price <= target_price:
                    triggered = True

                if triggered:
                    logger.info("🚨 ALVO ATINGIDO NO RENDER! Disparando Push urgente para o Android...")
                    
                    # Dispara notificação para todos os tokens registrados
                    for token in list(device_tokens):
                        send_fcm_notification(
                            token,
                            "🚨 ALARME BTC ATINGIDO!",
                            f"O Bitcoin atingiu USD {current_price:.2f} (Alvo: USD {target_price:.2f})"
                        )
                    
                    # Desativa o alarme após o disparo para evitar loop infinito
                    alarm_settings["active"] = False
            else:
                logger.info("[Monitor Render 30s] Servidor ativo e aguardando alarme ser definido no app...")

        except Exception as e:
            logger.error(f"Erro no loop de monitoramento: {e}")

        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(monitor_price())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    logger.info(">>> MONITOR AUTÔNOMO EM NUVEM INICIADO COM SUCESSO <<<")
    yield

app = FastAPI(lifespan=lifespan)

class TokenModel(BaseModel):
    token: str

class AlarmModel(BaseModel):
    target_price: float
    initial_price: float

@app.get("/")
def read_root():
    return {"status": "online", "message": "API BTC Alarm funcionando!"}

@app.post("/register-token")
def register_token(data: TokenModel):
    device_tokens.add(data.token)
    logger.info(f"Token registrado. Total de tokens ativos: {len(device_tokens)}")
    return {"status": "success", "message": "Token registrado com sucesso!"}

@app.post("/set-alarm")
def set_alarm(data: AlarmModel):
    alarm_settings["target_price"] = data.target_price
    alarm_settings["initial_price"] = data.initial_price
    alarm_settings["active"] = data.target_price > 0
    
    logger.info(f"Alarme ativo recebido do celular: Alvo={data.target_price} | Inicial={data.initial_price}")
    return {"status": "success", "message": "Alarme atualizado!"}
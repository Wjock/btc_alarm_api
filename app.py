import os
import json
import httpx
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__)

ARQUIVO_ESTADO = "alarme_estado.json"

# --- FUNÇÕES PARA LER E SALVAR O ESTADO EM ARQUIVO ---
def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "preco_alvo": None,
        "modo_alarme": None,
        "fcm_token": None,
        "ativo": False
    }

def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w") as f:
            json.dump(estado, f)
    except Exception as e:
        print("Erro ao salvar estado:", e)

# 2. INICIALIZAÇÃO DO FIREBASE ADMIN SDK
if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

# -------------------------------------------------------------------
# ROTA RAIZ: Para testar se a API está no ar pelo navegador
# -------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "mensagem": "API Alarme BTC no ar!"}), 200

# -------------------------------------------------------------------
# ENDPOINT 1: O Celular Kotlin envia o Alvo e o Token do Firebase aqui
# -------------------------------------------------------------------
@app.route('/configurar_alarme', methods=['POST'])
def configurar_alarme():
    dados = request.get_json()
    
    alvo = float(dados.get('preco_alvo', 0))
    token = dados.get('fcm_token', '')
    
    if alvo <= 0 or not token:
        return jsonify({"status": "erro", "mensagem": "Dados inválidos"}), 400

    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5.0)
        preco_atual = float(r.json()["price"])
        
        modo = "ACIMA" if alvo > preco_atual else "ABAIXO"
        
        estado = {
            "preco_alvo": alvo,
            "modo_alarme": modo,
            "fcm_token": token,
            "ativo": True
        }
        
        # Salva no arquivo no disco
        salvar_estado(estado)
        
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Alarme {modo} configurado para U$ {alvo:,.2f}",
            "preco_atual": preco_atual
        }), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

# -------------------------------------------------------------------
# ENDPOINT 2: O Cron (cron-job.org) chama esta rota a cada 1 minuto
# -------------------------------------------------------------------
@app.route('/checar_btc', methods=['GET'])
def checar_btc():
    # Carrega do arquivo no disco
    estado = carregar_estado()

    if not estado["ativo"] or estado["preco_alvo"] is None:
        return jsonify({"status": "aguardando", "mensagem": "Nenhum alarme ativo no servidor."}), 200

    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5.0)
        preco_atual = float(r.json()["price"])
        
        alvo = estado["preco_alvo"]
        modo = estado["modo_alarme"]
        
        disparar = False
        if modo == "ACIMA" and preco_atual >= alvo:
            disparar = True
        elif modo == "ABAIXO" and preco_atual <= alvo:
            disparar = True
            
        if disparar:
            enviar_notificacao_push(
                token=estado["fcm_token"],
                titulo="🚨 ALVO ATINGIDO! 🚨",
                corpo=f"O Bitcoin cruzou o Alvo de U$ {alvo:,.2f}! (Preço Atual: U$ {preco_atual:,.2f})"
            )
            
            # Desativa o alarme e salva a alteração no disco
            estado["ativo"] = False
            salvar_estado(estado)
            
            return jsonify({"status": "disparado", "preco": preco_atual, "alvo": alvo}), 200
            
        return jsonify({"status": "monitorando", "preco_atual": preco_atual, "alvo": alvo}), 200

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

def enviar_notificacao_push(token, titulo, corpo):
    mensagem = messaging.Message(
        notification=messaging.Notification(
            title=titulo,
            body=corpo,
        ),
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                channel_id='canal_alarme_btc'
            )
        ),
        token=token,
    )
    resposta = messaging.send(mensagem)
    print("Notificação enviada com sucesso:", resposta)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
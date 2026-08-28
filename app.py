import os
import json
import httpx
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__)

ARQUIVO_ESTADO = "alarme_estado.json"

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

if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "mensagem": "API Alarme BTC no ar!"}), 200

@app.route('/configurar_alarme', methods=['POST'])
def configurar_alarme():
    dados = request.get_json() or {}
    
    alvo = float(dados.get('preco_alvo', 0))
    token = dados.get('fcm_token', '')
    
    if alvo <= 0 or not token:
        return jsonify({"status": "erro", "mensagem": "Dados invalidos"}), 400

    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10.0)
        r.raise_for_status()
        dados_binance = r.json()

        if "price" not in dados_binance:
            return jsonify({"status": "erro", "mensagem": f"Resposta inesperada Binance: {dados_binance}"}), 500

        preco_atual = float(dados_binance["price"])
        modo = "ACIMA" if alvo > preco_atual else "ABAIXO"
        
        estado = {
            "preco_alvo": alvo,
            "modo_alarme": modo,
            "fcm_token": token,
            "ativo": True
        }
        
        salvar_estado(estado)
        
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Alarme {modo} configurado para U$ {alvo:,.2f}",
            "preco_atual": preco_atual
        }), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/checar_btc', methods=['GET'])
def checar_btc():
    estado = carregar_estado()

    if not estado["ativo"] or estado["preco_alvo"] is None:
        return jsonify({"status": "aguardando", "mensagem": "Nenhum alarme ativo no servidor."}), 200

    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10.0)
        r.raise_for_status()
        dados_binance = r.json()

        if "price" not in dados_binance:
            return jsonify({"status": "erro", "mensagem": f"Resposta inesperada Binance: {dados_binance}"}), 500

        preco_atual = float(dados_binance["price"])
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
                corpo=f"O Bitcoin cruzou o Alvo de U$ {alvo:,.2f}! (Preco Atual: U$ {preco_atual:,.2f})"
            )
            
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
    print("Notificacao enviada com sucesso:", resposta)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
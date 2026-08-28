import os
import httpx
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__)

# 1. ESTADO EM MEMÓRIA (Mesma lógica do seu dicionário 'state')
estado_alarme = {
    "preco_alvo": None,
    "modo_alarme": None,
    "fcm_token": None,       # Identificador do seu celular no Firebase
    "ativo": False
}

# 2. INICIALIZAÇÃO DO FIREBASE ADMIN SDK
# O arquivo serviceAccountKey.json será baixado do Firebase Console
if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

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

    # Busca preço atual para definir o modo ACIMA / ABAIXO
    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5.0)
        preco_atual = float(r.json()["price"])
        
        modo = "ACIMA" if alvo > preco_atual else "ABAIXO"
        
        estado_alarme["preco_alvo"] = alvo
        estado_alarme["modo_alarme"] = modo
        estado_alarme["fcm_token"] = token
        estado_alarme["ativo"] = True
        
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
    if not estado_alarme["ativo"] or estado_alarme["preco_alvo"] is None:
        return jsonify({"status": "aguardando", "mensagem": "Nenhum alarme ativo no servidor."}), 200

    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5.0)
        preco_atual = float(r.json()["price"])
        
        alvo = estado_alarme["preco_alvo"]
        modo = estado_alarme["modo_alarme"]
        
        disparar = False
        if modo == "ACIMA" and preco_atual >= alvo:
            disparar = True
        elif modo == "ABAIXO" and preco_atual <= alvo:
            disparar = True
            
        if disparar:
            # DISPARA A NOTIFICAÇÃO PUSH DE ALTA PRIORIDADE VIA FIREBASE
            enviar_notificacao_push(
                token=estado_alarme["fcm_token"],
                titulo="🚨 ALVO ATINGIDO! 🚨",
                corpo=f"O Bitcoin cruzou o Alvo de U$ {alvo:,.2f}! (Preço Atual: U$ {preco_atual:,.2f})"
            )
            
            # Desativa o alarme até a próxima programação (mesmo comportamento da sua rotina)
            estado_alarme["ativo"] = False
            
            return jsonify({"status": "disparado", "preco": preco_atual, "alvo": alvo}), 200
            
        return jsonify({"status": "monitorando", "preco_atual": preco_atual, "alvo": alvo}), 200

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

def enviar_notificacao_push(token, titulo, corpo):
    """Monta o pacote FCM com prioridade HIGH para acordar a CPU do Android."""
    mensagem = messaging.Message(
        notification=messaging.Notification(
            title=titulo,
            body=corpo,
        ),
        android=messaging.AndroidConfig(
            priority='high', # Prioridade maxima do Android
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
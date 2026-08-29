import time
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# Variáveis globais para armazenar o estado do alarme
alvo_atual = None
tipo_alarme = None  # "SUBIDA" ou "QUEDA"
preco_base = None

def checar_preco_btc():
    """Busca o preço do BTC usando rotas oficiais da Binance com fallback"""
    urls = [
        "https://api3.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT",
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    for url in urls:
        try:
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                dados = resposta.json()
                if "price" in dados:
                    return float(dados["price"])
        except Exception as e:
            print(f"[Tentativa falhou para {url}]: {e}")
            continue
            
    print("[Erro] Nenhuma rota da Binance respondeu com sucesso.")
    return None

def monitor_loop():
    """Loop inteligente em segundo plano que roda a cada 60 segundos"""
    global alvo_atual, tipo_alarme
    
    while True:
        if alvo_atual is not None and tipo_alarme is not None:
            preco_atual = checar_preco_btc()
            
            if preco_atual:
                print(f"[Checagem 1min] BTC: USD {preco_atual:.2f} | Alvo ({tipo_alarme}): USD {alvo_atual:.2f}")
                
                disparar = False
                if tipo_alarme == "SUBIDA" and preco_atual >= alvo_atual:
                    disparar = True
                elif tipo_alarme == "QUEDA" and preco_atual <= alvo_atual:
                    disparar = True
                
                if disparar:
                    print(f"🚨 ALARME DISPARADO! BTC atingiu USD {preco_atual:.2f}")
                    # AQUI entra o envio da notificação no celular
                    
                    # Reseta o alarme após disparar
                    alvo_atual = None
                    tipo_alarme = None
        
        time.sleep(60)

# Rota para o celular consultar a cotação atual
@app.route("/preco", methods=["GET"])
def obter_preco():
    preco = checar_preco_btc()
    if preco:
        return jsonify({"btc_usd": preco}), 200
    return jsonify({"erro": "Nao foi possivel buscar o preco"}), 500

# Rota para o celular definir o novo alvo
@app.route("/definir-alvo", methods=["POST"])
def definir_alvo():
    global alvo_atual, tipo_alarme, preco_base
    
    dados = request.get_json()
    if not dados or "alvo" not in dados:
        return jsonify({"erro": "Alvo nao fornecido"}), 400
    
    novo_alvo = float(dados["alvo"])
    preco_atual = checar_preco_btc()
    
    if not preco_atual:
        return jsonify({"erro": "Falha ao obter preco atual do BTC"}), 500
    
    alvo_atual = novo_alvo
    preco_base = preco_atual
    
    if novo_alvo > preco_atual:
        tipo_alarme = "SUBIDA"
    else:
        tipo_alarme = "QUEDA"
        
    print(f"Novo alvo recebido: USD {alvo_atual} | Tipo: {tipo_alarme} | Preço atual: USD {preco_atual}")
    
    return jsonify({
        "status": "sucesso",
        "alvo": alvo_atual,
        "tipo": tipo_alarme,
        "preco_atual": preco_atual
    }), 200

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)

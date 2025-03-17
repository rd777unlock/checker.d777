import requests
import json
import sys
import time
import re
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Configurações da API Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = "TEST-XXXXXXXXXXXXXXXXXXXXXXXXXXXXX-XXXXXX"
API_URL = "https://api.mercadopago.com/v1"


def test_proxy(proxy):
    """Testa se a proxy está funcionando"""
    try:
        response = requests.get("https://api.mercadopago.com/v1/payment_methods",
                                headers={"Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}"},
                                proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"},
                                timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao testar proxy: {e}")
        return False


def test_api():
    """Testa se a API do Mercado Pago está acessível"""
    try:
        response = requests.get(f"{API_URL}/payment_methods",
                                headers={"Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}"},
                                timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao testar API: {e}")
        return False


def validate_luhn(card_number):
    """
    Valida o número do cartão usando o algoritmo de Luhn
    """
    # Remove espaços e caracteres não numéricos
    card_number = re.sub(r'\D', '', card_number)

    if not card_number.isdigit():
        return False

    # Converte para lista de inteiros
    digits = [int(d) for d in card_number]

    # Algoritmo Luhn
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


def check_card(card_data, proxy=None):
    """
    Testa um cartão de crédito na API do Mercado Pago
    """
    # Dados para criar um pagamento teste
    payload = {
        "transaction_amount": 1.00,
        "description": "Teste de Cartão",
        "payment_method_id": card_data["payment_method_id"],
        "token": card_data["token"],
        "installments": 1,
        "payer": {
            "email": "test_user_123456@testuser.com",
            "identification": {
                "type": "CPF",
                "number": "12345678909"
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    proxies = None
    if proxy:
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    try:
        response = requests.post(
            f"{API_URL}/payments",
            headers=headers,
            data=json.dumps(payload),
            proxies=proxies,
            timeout=30
        )

        result = response.json()

        if response.status_code == 201 and result.get("status") == "approved":
            return {"status": "Live", "message": "Pagamento aprovado", "details": result}
        else:
            # Verifica os diferentes tipos de rejeição
            status = result.get("status", "")
            status_detail = result.get("status_detail", "")

            return {
                "status": "Die",
                "message": f"Pagamento rejeitado: {status} - {status_detail}",
                "details": result
            }

    except Exception as e:
        return {"status": "Error", "message": f"Erro ao processar: {str(e)}"}


def create_card_token(card_data, proxy=None):
    """
    Cria um token para o cartão na API do Mercado Pago
    """
    payload = {
        "card_number": card_data["number"],
        "cardholder": {
            "name": card_data["holder_name"]
        },
        "expiration_month": int(card_data["expiry_month"]),
        "expiration_year": int(card_data["expiry_year"]),
        "security_code": card_data["cvv"]
    }

    headers = {
        "Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    proxies = None
    if proxy:
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    try:
        response = requests.post(
            f"{API_URL}/card_tokens",
            headers=headers,
            data=json.dumps(payload),
            proxies=proxies,
            timeout=30
        )

        if response.status_code == 201:
            result = response.json()
            return {"success": True, "token": result.get("id"),
                    "payment_method_id": result.get("payment_method", {}).get("id")}
        else:
            result = response.json()
            return {"success": False, "error": result.get("message", "Erro ao criar token do cartão")}

    except Exception as e:
        return {"success": False, "error": f"Erro: {str(e)}"}


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/check-card', methods=['POST'])
def check_card_route():
    data = request.json
    card_number = data.get('card_number')
    holder_name = data.get('holder_name')
    expiry_month = data.get('expiry_month')
    expiry_year = data.get('expiry_year')
    cvv = data.get('cvv')
    proxy = data.get('proxy')

    # Verifica se o proxy foi fornecido e testa
    if proxy and not test_proxy(proxy):
        return jsonify({"error": "Proxy inválido ou não funcional"})

    # Testa se a API está funcionando
    if not test_api():
        return jsonify({"error": "API do Mercado Pago não está respondendo"})

    # Verifica o algoritmo de Luhn silenciosamente
    if not validate_luhn(card_number):
        return jsonify({"status": "Die", "message": "Cartão rejeitado"})

    # Cria um token para o cartão
    card_data = {
        "number": card_number,
        "holder_name": holder_name,
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "cvv": cvv
    }

    token_result = create_card_token(card_data, proxy)

    if not token_result["success"]:
        return jsonify({"status": "Die", "message": token_result["error"]})

    # Testa o pagamento com o token gerado
    payment_result = check_card({
        "token": token_result["token"],
        "payment_method_id": token_result["payment_method_id"]
    }, proxy)

    return jsonify(payment_result)


if __name__ == '__main__':
    print("Iniciando o Checker de Cartões do Mercado Pago...")
    print("Testando API do Mercado Pago...")

    if not test_api():
        print("Erro: API do Mercado Pago não está respondendo. Verifique seu token de acesso.")
        sys.exit(1)

    print("API conectada com sucesso!")
    app.run(debug=True, host='0.0.0.0', port=5000)
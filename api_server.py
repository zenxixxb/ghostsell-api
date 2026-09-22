import json
import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BALANCE_FILE = "balance.json"
DATA_FILE = "products.json"
ORDERS_FILE = "orders.json"
PROMO_FILE = "promo.json"

# Токен бота — чтобы отправлять уведомления
BOT_TOKEN = "8836260327:AAGxBaWF_YWpTJr1H1Q1gsdNKbkUqM_WJOQ"

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def send_telegram_message(user_id, text):
    """Отправляет уведомление пользователю в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": user_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

@app.route('/')
def index():
    return "GhostSell API работает ✅"

@app.route('/api/balance', methods=['POST'])
def get_balance():
    data = request.json
    user_id = str(data.get('user_id', ''))
    balances = load_json(BALANCE_FILE)
    balance = balances.get(user_id, 0)
    return jsonify({"balance": balance})

@app.route('/api/products')
def get_products():
    data = load_json(DATA_FILE)
    result = []
    for key, product in data.items():
        if product.get("hidden", False):
            continue
        count = len([i for i in product.get("items", []) if isinstance(i, dict) and i.get("number")])
        if count > 0:
            result.append({
                "key": key,
                "name": product.get("name", key),
                "emoji": product.get("emoji", "🌍"),
                "price": product.get("price_rub", 0),
                "count": count,
                "desc": product.get("desc", "")
            })
    return jsonify({"products": result})

@app.route('/api/buy', methods=['POST'])
def buy():
    data = request.json
    user_id = str(data.get('user_id', ''))
    product_key = data.get('key', '')
    
    products = load_json(DATA_FILE)
    if product_key not in products:
        return jsonify({"success": False, "error": "Товар не найден"})
    
    product = products[product_key]
    price = product.get("price_rub", 0)
    
    balances = load_json(BALANCE_FILE)
    user_balance = balances.get(user_id, 0)
    
    if user_balance < price:
        return jsonify({"success": False, "error": f"Недостаточно средств. Баланс: {user_balance} ₽, нужно: {price} ₽"})
    
    items = product.get("items", [])
    number = None
    for i, item in enumerate(items):
        if isinstance(item, dict) and item.get("number"):
            number = item.get("number")
            items.pop(i)
            break
    
    if not number:
        return jsonify({"success": False, "error": "Товар закончился"})
    
    balances[user_id] = user_balance - price
    save_json(BALANCE_FILE, balances)
    save_json(DATA_FILE, products)
    
    orders = load_json(ORDERS_FILE)
    if user_id not in orders:
        orders[user_id] = []
    orders[user_id].append({
        "username": "mini_app",
        "product": product.get("name", product_key),
        "price": price,
        "status": "одобрен",
        "date": str(datetime.now()),
        "number": number,
        "phone": number
    })
    save_json(ORDERS_FILE, orders)
    
    # Уведомление пользователю в бот
    send_telegram_message(
        user_id,
        f"✅ *Покупка совершена!*\n\n"
        f"📦 Товар: {product.get('name')}\n"
        f"💰 Сумма: {price} ₽\n"
        f"📱 Номер: `{number}`\n"
        f"💳 Остаток: {balances[user_id]} ₽"
    )
    
    return jsonify({
        "success": True,
        "number": number,
        "balance": balances[user_id],
        "message": f"Покупка успешна! Номер: {number}"
    })

@app.route('/api/orders', methods=['POST'])
def get_orders():
    """Возвращает заказы пользователя"""
    data = request.json
    user_id = str(data.get('user_id', ''))
    orders = load_json(ORDERS_FILE)
    user_orders = orders.get(user_id, [])
    return jsonify({"orders": user_orders[::-1]})  # Свежие сверху

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

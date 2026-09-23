import json
import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ========== ФАЙЛЫ ==========
BALANCE_FILE = "balance.json"
DATA_FILE = "products.json"
ORDERS_FILE = "orders.json"
PROMO_FILE = "promo.json"
CODE_REQUESTS_FILE = "code_requests.json"
BONUS_FILE = "bonus.json"
DISCOUNTS_FILE = "discounts.json"

# ========== КОНФИГ ==========
SYNC_SECRET = "ghostsell_2026_secret_key"
BOT_TOKEN = "8836260327:AAGxBaWF_YWpTJr1H1Q1gsdNKbkUqM_WJOQ"
АДМИНЫ = [7940562298, 6169533449]


# ========== РАБОТА С ДАННЫМИ ==========
def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram_message(user_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": user_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def count_real(items):
    return len([
        i for i in items
        if isinstance(i, dict) and i.get("number") and not i.get("number").startswith("Номер")
    ])


# ========== ГЛАВНАЯ ==========
@app.route('/')
def index():
    return "GhostSell API работает ✅"


# ========== БАЛАНС ==========
@app.route('/api/balance', methods=['POST'])
def get_balance():
    data = request.json
    user_id = str(data.get('user_id', ''))
    balances = load_json(BALANCE_FILE)
    return jsonify({"balance": balances.get(user_id, 0)})


# ========== ТОВАРЫ ==========
@app.route('/api/products')
def get_products():
    data = load_json(DATA_FILE)
    result = []
    for key, product in data.items():
        if product.get("hidden", False):
            continue
        real = count_real(product.get("items", []))
        if real > 0:
            result.append({
                "key": key,
                "name": product.get("name", key),
                "emoji": product.get("emoji", "🌍"),
                "price": product.get("price_rub", 0),
                "count": real,
                "desc": product.get("desc", ""),
                "seller": product.get("seller", "admin"),
                "seller_verified": product.get("seller_verified", False)
            })
    return jsonify({"products": result})


# ========== ПОКУПКА ==========
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

    # Проверяем скидку с колеса
    discounts = load_json(DISCOUNTS_FILE)
    user_discount = discounts.get(user_id, 0)
    if user_discount > 0:
        price = round(price * (100 - user_discount) / 100)
        discounts[user_id] = 0
        save_json(DISCOUNTS_FILE, discounts)

    balances = load_json(BALANCE_FILE)
    user_balance = balances.get(user_id, 0)

    if user_balance < price:
        return jsonify({"success": False, "error": f"Недостаточно средств. Баланс: {user_balance} ₽, нужно: {price} ₽"})

    items = product.get("items", [])
    number = None
    for i, item in enumerate(items):
        if isinstance(item, dict) and item.get("number") and not item.get("number").startswith("Номер"):
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
        "price_rub": price,
        "price": price,
        "status": "одобрен",
        "date": str(datetime.now()),
        "number": number,
        "phone": number
    })
    save_json(ORDERS_FILE, orders)

    # Уведомление клиенту
    discount_text = f"\n🎰 Скидка: {user_discount}%" if user_discount > 0 else ""
    send_telegram_message(
        user_id,
        f"✅ *Покупка совершена!*\n\n"
        f"📦 Товар: {product.get('name')}\n"
        f"💰 Сумма: {price} ₽{discount_text}\n"
        f"📱 Номер: `{number}`\n"
        f"💳 Остаток: {balances[user_id]} ₽"
    )

    # Уведомление продавцу (если не админ)
    seller = product.get("seller", "admin")
    if seller != "admin":
        try:
            send_telegram_message(
                int(seller),
                f"💰 *Новая продажа!*\n\n"
                f"📦 Товар: {product.get('name')}\n"
                f"💵 Сумма: {price} ₽"
            )
        except:
            pass

    return jsonify({
        "success": True,
        "number": number,
        "balance": balances[user_id],
        "message": f"Покупка успешна! Номер: {number}"
    })


# ========== ЗАКАЗЫ ==========
@app.route('/api/orders', methods=['POST'])
def get_orders():
    data = request.json
    user_id = str(data.get('user_id', ''))
    orders = load_json(ORDERS_FILE)
    user_orders = orders.get(user_id, [])

    fixed = []
    for o in user_orders[::-1]:
        fixed.append({
            "product": o.get("product", "—"),
            "price": o.get("price_rub") or o.get("price", 0),
            "status": o.get("status", "—"),
            "number": o.get("number") or o.get("phone") or o.get("item", "—"),
            "date": o.get("date", "")
        })

    return jsonify({"orders": fixed})


# ========== ЗАПРОС КОДА ==========
@app.route('/api/request_code', methods=['POST'])
def request_code():
    data = request.json
    user_id = str(data.get('user_id', ''))
    phone = data.get('phone', '')
    order_index = data.get('order_index', 0)

    if not phone:
        return jsonify({"success": False, "error": "Нет номера телефона"})

    requests_data = load_json(CODE_REQUESTS_FILE)
    if user_id not in requests_data:
        requests_data[user_id] = []
    requests_data[user_id].append({
        "phone": phone,
        "order_index": order_index,
        "timestamp": str(datetime.now()),
        "status": "в ожидании"
    })
    save_json(CODE_REQUESTS_FILE, requests_data)

    for admin_id in АДМИНЫ:
        send_telegram_message(
            admin_id,
            f"🔑 *Запрос кода для входа*\n\n"
            f"👤 ID юзера: `{user_id}`\n"
            f"📱 Номер: `{phone}`\n"
            f"📦 Заказ: #{order_index}"
        )

    return jsonify({"success": True, "message": "Запрос отправлен"})


# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
@app.route('/api/bonus_status', methods=['POST'])
def bonus_status():
    data = request.json
    user_id = str(data.get('user_id', ''))
    bonuses = load_json(BONUS_FILE)
    user_bonus = bonuses.get(user_id, {})
    last_date = user_bonus.get('last_claim', '')
    today = str(datetime.now().date())
    can_claim = last_date != today
    return jsonify({"can_claim": can_claim})


@app.route('/api/claim_bonus', methods=['POST'])
def claim_bonus():
    data = request.json
    user_id = str(data.get('user_id', ''))
    today = str(datetime.now().date())

    bonuses = load_json(BONUS_FILE)
    user_bonus = bonuses.get(user_id, {})

    if user_bonus.get('last_claim') == today:
        return jsonify({"success": False, "error": "Уже забрано сегодня"})

    amount = 5
    balances = load_json(BALANCE_FILE)
    balances[user_id] = balances.get(user_id, 0) + amount
    save_json(BALANCE_FILE, balances)

    bonuses[user_id] = {"last_claim": today}
    save_json(BONUS_FILE, bonuses)

    return jsonify({"success": True, "amount": amount})


# ========== ТОП ПОКУПАТЕЛЕЙ ==========
@app.route('/api/top_buyers')
def top_buyers():
    orders = load_json(ORDERS_FILE)
    totals = {}
    for user_id, user_orders in orders.items():
        for o in user_orders:
            username = o.get('username', 'anon')
            price = o.get('price_rub') or o.get('price', 0)
            if username not in totals:
                totals[username] = 0
            totals[username] += price

    sorted_buyers = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    result = [{"username": u, "total": t} for u, t in sorted_buyers[:10]]
    return jsonify({"buyers": result})


# ========== СКИДКИ С КОЛЕСА ==========
@app.route('/api/save_discount', methods=['POST'])
def save_discount():
    data = request.json
    user_id = str(data.get('user_id', ''))
    discount = int(data.get('discount', 0))

    discounts = load_json(DISCOUNTS_FILE)
    discounts[user_id] = discount
    save_json(DISCOUNTS_FILE, discounts)

    return jsonify({"success": True})


# ========== СИНХРОНИЗАЦИЯ С АДМИН-БОТОМ ==========
@app.route('/api/sync_products', methods=['POST'])
def sync_products():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    products = data.get('products', {})
    if not products:
        return jsonify({"success": False, "error": "Пустые данные"})
    save_json(DATA_FILE, products)
    return jsonify({"success": True})


@app.route('/api/sync_balance', methods=['POST'])
def sync_balance():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    balances = data.get('balances', {})
    save_json(BALANCE_FILE, balances)
    return jsonify({"success": True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

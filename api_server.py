import json
import os
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
BONUS_FILE = "bonus.json"
DEPOSITS_FILE = "deposits.json"

SYNC_SECRET = "ghostsell_2026_secret_key"
BOT_TOKEN = "8836260327:AAGxBaWF_YWpTJr1H1Q1gsdNKbkUqM_WJOQ"

# ========== НАСТРОЙКИ ПОДПИСКИ ==========
CHANNEL_USERNAME = "@GhostSell_channel"
BONUS_COOLDOWN_SEC = 24 * 60 * 60
MIN_DEPOSIT_FOR_BONUS = 50
BONUS_MIN = 5
BONUS_MAX = 20


def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram_message(user_id, text):
    import requests
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass


def count_real(items):
    return len([i for i in items if isinstance(i, dict) and i.get("number") and not i.get("number").startswith("Номер")])


def get_total_deposit(user_id):
    deposits = load_json(DEPOSITS_FILE)
    user_deposits = deposits.get(str(user_id), [])
    return sum(d.get("amount", 0) for d in user_deposits if d.get("status") == "approved")


def now_ts():
    return int(datetime.now().timestamp())


@app.route('/')
def index():
    return "GhostSell API работает (Solo Shop) ✅"


@app.route('/api/check_subscription', methods=['POST'])
def check_subscription():
    import requests
    data = request.json or {}
    user_id = data.get('user_id')
    channel = data.get('channel', CHANNEL_USERNAME)

    if not user_id:
        return jsonify({"subscribed": False, "error": "no user_id"})
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        r = requests.post(url, json={"chat_id": channel, "user_id": user_id}, timeout=8)
        d = r.json()
        if not d.get("ok"):
            return jsonify({"subscribed": True, "status": "unknown"})
        status = d.get("result", {}).get("status", "")
        return jsonify({"subscribed": status in ["member", "administrator", "creator"], "status": status})
    except:
        return jsonify({"subscribed": True, "status": "unknown"})


@app.route('/api/balance', methods=['POST'])
def get_balance():
    data = request.json
    user_id = str(data.get('user_id', ''))
    balances = load_json(BALANCE_FILE)
    return jsonify({
        "balance": balances.get(user_id, 0),
        "total_deposit": get_total_deposit(user_id)
    })


@app.route('/api/get_all_balances', methods=['POST'])
def get_all_balances():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    return jsonify({"success": True, "balances": load_json(BALANCE_FILE)})


@app.route('/api/products')
def get_products():
    data = load_json(DATA_FILE)
    result = []
    for key, product in data.items():
        if product.get("hidden", False):
            continue
            
        # Блокировка РФ и УКР на уровне каталога
        name_lower = product.get("name", key).lower()
        if product.get("country") in ["RU", "UA"] or "россия" in name_lower or "+7" in name_lower or "украина" in name_lower or "+380" in name_lower or "380" in name_lower:
            continue
            
        real = count_real(product.get("items", []))
        if real > 0:
            result.append({
                "key": key,
                "name": product.get("name", key),
                "emoji": product.get("emoji", "🌍"),
                "price": product.get("price_rub", 0),
                "count": real,
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
        return jsonify({"success": False, "error": f"Недостаточно средств. Баланс: {user_balance} ₽"})

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
        "price_rub": price, "price": price,
        "status": "одобрен",
        "date": str(datetime.now()),
        "number": number, "phone": number
    })
    save_json(ORDERS_FILE, orders)

    send_telegram_message(user_id, f"✅ *Покупка совершена!*\n\n📦 {product.get('name')}\n💰 {price} ₽\n📱 Номер: `{number}`\n💳 Остаток: {balances[user_id]} ₽")

    return jsonify({"success": True, "number": number, "balance": balances[user_id], "message": f"Покупка успешна! Номер: {number}"})


@app.route('/api/orders', methods=['POST'])
def get_orders():
    data = request.json
    user_id = str(data.get('user_id', ''))
    orders = load_json(ORDERS_FILE).get(user_id, [])
    fixed = [{"product": o.get("product", "—"), "price": o.get("price_rub") or o.get("price", 0), "status": o.get("status", "—"), "number": o.get("number") or o.get("phone") or o.get("item", "—"), "date": o.get("date", "")} for o in orders[::-1]]
    return jsonify({"orders": fixed})


@app.route('/api/bonus_status', methods=['POST'])
def bonus_status():
    data = request.json
    user_id = str(data.get('user_id', ''))
    bonuses = load_json(BONUS_FILE)
    last_claim = bonuses.get(user_id, {}).get('last_claim_ts', 0)
    total_deposit = get_total_deposit(user_id)

    can_claim = (now_ts() - last_claim) >= BONUS_COOLDOWN_SEC
    deposit_ok = total_deposit >= MIN_DEPOSIT_FOR_BONUS

    return jsonify({"can_claim": can_claim and deposit_ok, "deposit_ok": deposit_ok, "total_deposit": total_deposit, "next_claim_in": 0 if can_claim else (BONUS_COOLDOWN_SEC - (now_ts() - last_claim))})


@app.route('/api/claim_bonus', methods=['POST'])
def claim_bonus():
    data = request.json
    user_id = str(data.get('user_id', ''))
    amount = max(BONUS_MIN, min(BONUS_MAX, int(data.get('amount', BONUS_MIN))))

    if get_total_deposit(user_id) < MIN_DEPOSIT_FOR_BONUS:
        return jsonify({"success": False, "error": f"Нужен депозит от {MIN_DEPOSIT_FOR_BONUS} ₽"})

    bonuses = load_json(BONUS_FILE)
    last_claim = bonuses.get(user_id, {}).get('last_claim_ts', 0)
    if (now_ts() - last_claim) < BONUS_COOLDOWN_SEC:
        return jsonify({"success": False, "error": "Бонус уже получен."})

    balances = load_json(BALANCE_FILE)
    balances[user_id] = balances.get(user_id, 0) + amount
    save_json(BALANCE_FILE, balances)

    bonuses[user_id] = {"last_claim_ts": now_ts(), "last_claim_date": str(datetime.now()), "total_claimed": bonuses.get(user_id, {}).get("total_claimed", 0) + amount}
    save_json(BONUS_FILE, bonuses)

    send_telegram_message(user_id, f"🎁 *Ежедневный бонус:* +{amount} ₽\n💳 Баланс: {balances[user_id]} ₽")
    return jsonify({"success": True, "amount": amount, "balance": balances[user_id]})


@app.route('/api/top_buyers')
def top_buyers():
    orders = load_json(ORDERS_FILE)
    totals = {}
    for user_id, user_orders in orders.items():
        for o in user_orders:
            username = o.get('username', 'anon')
            totals[username] = totals.get(username, 0) + (o.get('price_rub') or o.get('price', 0))
    sorted_buyers = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return jsonify({"buyers": [{"username": u, "total": t} for u, t in sorted_buyers[:10]]})


@app.route('/api/sync_products', methods=['POST'])
def sync_products():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    if not data.get('products'):
        return jsonify({"success": False, "error": "Пустые данные"})
    save_json(DATA_FILE, data.get('products'))
    return jsonify({"success": True})


@app.route('/api/sync_balance', methods=['POST'])
def sync_balance():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    save_json(BALANCE_FILE, data.get('balances', {}))
    return jsonify({"success": True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
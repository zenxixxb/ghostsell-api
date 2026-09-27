import json
import os
import time
import requests
import re
import zipfile
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ========== ФАЙЛЫ И КОНФИГ ==========
BALANCE_FILE = "balance.json"
DATA_FILE = "products.json"
ORDERS_FILE = "orders.json"
PROMO_FILE = "promo.json"
CODE_CACHE_FILE = "code_cache.json"
BONUS_FILE = "bonus.json"
DISCOUNTS_FILE = "discounts.json"
SELLERS_FILE = "sellers.json"
PENDING_FILE = "pending_products.json"
CHATS_FILE = "chats.json"
DEPOSITS_FILE = "deposits.json"
REVIEWS_FILE = "reviews.json"
ACCOUNTS_FILE = "accounts.json"
SESSIONS_DIR = "sessions/"

SYNC_SECRET = "ghostsell_2026_secret_key"
BOT_TOKEN = "8836260327:AAEqVehgIOOQ_R9XFMgcFN3mNf1P-u_Hdgo"
АДМИНЫ = [7940562298, 6169533449]
КОМИССИЯ = 20
LISTENER_PORT = 5001
CODE_TTL = 300

CHANNEL_USERNAME = "@GhostSell_channel"
BONUS_COOLDOWN_SEC = 24 * 60 * 60
MIN_DEPOSIT_FOR_BONUS = 50
BONUS_MIN, BONUS_MAX = 5, 20

request_logs = {}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_telegram_message(user_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def count_real(items):
    return len([i for i in items if isinstance(i, dict) and i.get("number") and not i.get("number").startswith("Номер")])

def get_total_deposit(user_id):
    deposits = load_json(DEPOSITS_FILE)
    return sum(d.get("amount", 0) for d in deposits.get(str(user_id), []) if d.get("status") == "approved")

def now_ts():
    return int(datetime.now().timestamp())

def check_rate_limit(user_id):
    now = datetime.now().timestamp()
    if user_id not in request_logs: request_logs[user_id] = []
    request_logs[user_id] = [t for t in request_logs[user_id] if now - t < 60]
    if len(request_logs[user_id]) >= 5: return False
    request_logs[user_id].append(now)
    return True

# ========== БАЗОВЫЕ API ==========
@app.route('/')
def index():
    return "GhostSell API работает ✅"

@app.route('/api/check_subscription', methods=['POST'])
def check_subscription():
    data = request.json or {}
    user_id = data.get('user_id')
    if not user_id: return jsonify({"subscribed": False})
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        r = requests.post(url, json={"chat_id": CHANNEL_USERNAME, "user_id": user_id}, timeout=8)
        d = r.json()
        if not d.get("ok"): return jsonify({"subscribed": True})
        return jsonify({"subscribed": d.get("result", {}).get("status", "") in ["member", "administrator", "creator"]})
    except:
        return jsonify({"subscribed": True})

@app.route('/api/balance', methods=['POST'])
def get_balance():
    user_id = str(request.json.get('user_id', ''))
    return jsonify({"balance": load_json(BALANCE_FILE).get(user_id, 0), "total_deposit": get_total_deposit(user_id)})

# ========== ТОВАРЫ И ПОКУПКА В MINI APP ==========
@app.route('/api/products')
def get_products():
    data = load_json(DATA_FILE)
    result = []
    for key, product in data.items():
        if product.get("hidden", False): continue
        nl = product.get("name", key).lower()
        if "россия" in nl or "+7" in nl or "ru" in nl or "украина" in nl or "+380" in nl or "ua" in nl:
            continue
        real = count_real(product.get("items", []))
        if real > 0:
            result.append({
                "key": key, "name": product.get("name", key),
                "emoji": product.get("emoji", "🌍"), "price": product.get("price_rub", 0),
                "count": real, "desc": product.get("desc", ""),
            })
    return jsonify({"products": result})

@app.route('/api/buy', methods=['POST'])
def buy():
    data = request.json
    user_id = str(data.get('user_id', ''))
    product_key = data.get('key', '')

    products = load_json(DATA_FILE)
    if product_key not in products: return jsonify({"success": False, "error": "Товар не найден"})

    product = products[product_key]
    price = product.get("price_rub", 0)

    balances = load_json(BALANCE_FILE)
    user_balance = balances.get(user_id, 0)
    if user_balance < price:
        return jsonify({"success": False, "error": f"Недостаточно средств. Баланс: {user_balance} ₽"})

    items = product.get("items", [])
    number = next((item.get("number") for item in items if isinstance(item, dict) and item.get("number")), None)
    
    if not number:
        return jsonify({"success": False, "error": "Товар закончился"})

    # ПРИВЯЗКА К ID ПОКУПАТЕЛЯ!
    accs = load_json(ACCOUNTS_FILE)
    acc_key = number if number in accs else f"+{number}"
    if acc_key in accs:
        accs[acc_key]["buyer_id"] = str(user_id)
        accs[acc_key]["status"] = "sold"
        save_json(ACCOUNTS_FILE, accs)

    items[:] = [it for it in items if it.get("number") != number] # Удаляем купленный номер
    balances[user_id] = user_balance - price
    save_json(BALANCE_FILE, balances)
    save_json(DATA_FILE, products)

    orders = load_json(ORDERS_FILE)
    if user_id not in orders: orders[user_id] = []
    orders[user_id].append({
        "username": "mini_app", "product": product.get("name"),
        "price": price, "status": "одобрен",
        "date": str(datetime.now()), "number": number
    })
    save_json(ORDERS_FILE, orders)

    send_telegram_message(user_id, f"✅ *Покупка совершена!*\n\n📦 {product.get('name')}\n💰 {price} ₽\n📱 Номер: `{number}`\n\nДля входа открой меню бота и нажми «Мои заказы».")

    return jsonify({"success": True, "number": number, "balance": balances[user_id], "message": f"Покупка успешна!"})

@app.route('/api/orders', methods=['POST'])
def get_orders():
    user_orders = load_json(ORDERS_FILE).get(str(request.json.get('user_id', '')), [])
    fixed = [{"product": o.get("product"), "price": o.get("price", 0), "status": o.get("status"), "number": o.get("number"), "date": o.get("date")} for o in user_orders[::-1]]
    return jsonify({"orders": fixed})

# ========== РАБОТА С КОДАМИ И TELETHON ==========
@app.route('/api/upload_batch', methods=['POST'])
def upload_batch():
    if 'file' not in request.files: return jsonify({"success": False, "error": "Нет файла"})
    file = request.files['file']
    batch_dir = os.path.join(SESSIONS_DIR, f"batch_{int(datetime.now().timestamp())}")
    os.makedirs(batch_dir, exist_ok=True)
    zip_path = os.path.join(batch_dir, file.filename)
    file.save(zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(batch_dir)
    os.remove(zip_path)
    
    accounts = load_json(ACCOUNTS_FILE)
    added, dead, with_2fa, phones = 0, 0, 0, []
    
    for root, _, files in os.walk(batch_dir):
        for f in files:
            if f.endswith('.session'):
                base = f.replace('.session', '')
                json_path = os.path.join(root, f"{base}.json")
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        try:
                            acc_data = json.load(jf)
                            phone = acc_data.get("phone", base)
                            if not phone.startswith("+"): phone = "+" + phone
                            accounts[phone] = {
                                "phone": phone, "session_file": os.path.join(root, f),
                                "json_file": json_path, "twoFA": acc_data.get("twoFA", ""),
                                "added_date": datetime.now().isoformat(), "status": "available",
                                "seller_id": "admin", "buyer_id": None
                            }
                            added += 1; phones.append(phone)
                            if acc_data.get("twoFA"): with_2fa += 1
                        except: pass
                            
    save_json(ACCOUNTS_FILE, accounts)
    try: requests.post(f"http://localhost:{LISTENER_PORT}/reload")
    except: pass
    return jsonify({"success": True, "added": added, "dead": dead, "with_2fa": with_2fa, "phones": phones})

@app.route('/api/get_code', methods=['POST'])
def get_code():
    data = request.json
    user_id = str(data.get("user_id"))
    phone = data.get("phone")
    if not phone.startswith("+"): phone = "+" + phone
    
    if not check_rate_limit(user_id):
        return jsonify({"success": False, "message": "Слишком много запросов (спам)."})
        
    accounts = load_json(ACCOUNTS_FILE)
    if phone not in accounts:
        return jsonify({"success": False, "message": "Аккаунт не найден на сервере."})
        
    if str(accounts[phone].get("buyer_id")) != user_id:
        return jsonify({"success": False, "message": "Это не ваш аккаунт!"})
        
    cache = load_json(CODE_CACHE_FILE)
    if phone in cache:
        code_data = cache[phone]
        if datetime.now().timestamp() - datetime.fromisoformat(code_data["date"]).timestamp() <= CODE_TTL:
            return jsonify({"success": True, "code": code_data["code"], "twoFA": accounts[phone].get("twoFA", "")})
            
    return jsonify({"success": False, "message": "Код пока не пришёл. Подождите пару секунд и нажмите Обновить."})

@app.route('/api/verify_2fa', methods=['POST'])
def verify_2fa():
    try: return jsonify(requests.post(f"http://localhost:{LISTENER_PORT}/verify_2fa", json=request.json).json())
    except: return jsonify({"success": False, "message": "Ошибка связи со слушателем."})

# ========== БОНУСЫ И ПРОЧЕЕ ==========
@app.route('/api/bonus_status', methods=['POST'])
def bonus_status():
    user_id = str(request.json.get('user_id', ''))
    last = load_json(BONUS_FILE).get(user_id, {}).get('last_claim_ts', 0)
    return jsonify({"can_claim": (now_ts() - last) >= BONUS_COOLDOWN_SEC})

@app.route('/api/claim_bonus', methods=['POST'])
def claim_bonus():
    user_id = str(request.json.get('user_id', ''))
    bonuses = load_json(BONUS_FILE)
    if (now_ts() - bonuses.get(user_id, {}).get('last_claim_ts', 0)) < BONUS_COOLDOWN_SEC:
        return jsonify({"success": False, "error": "Рано"})
    amt = max(BONUS_MIN, min(BONUS_MAX, int(request.json.get('amount', BONUS_MIN))))
    balances = load_json(BALANCE_FILE)
    balances[user_id] = balances.get(user_id, 0) + amt
    save_json(BALANCE_FILE, balances)
    bonuses[user_id] = {"last_claim_ts": now_ts(), "total_claimed": bonuses.get(user_id, {}).get("total_claimed", 0) + amt}
    save_json(BONUS_FILE, bonuses)
    return jsonify({"success": True, "amount": amt, "balance": balances[user_id]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
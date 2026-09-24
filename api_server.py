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
CODE_REQUESTS_FILE = "code_requests.json"
BONUS_FILE = "bonus.json"
DISCOUNTS_FILE = "discounts.json"
WHEEL_FILE = "wheel.json"
SELLERS_FILE = "sellers.json"
PENDING_FILE = "pending_products.json"
CHATS_FILE = "chats.json"

SYNC_SECRET = "ghostsell_2026_secret_key"
BOT_TOKEN = "8836260327:AAGxBaWF_YWpTJr1H1Q1gsdNKbkUqM_WJOQ"
АДМИНЫ = [7940562298, 6169533449]
КОМИССИЯ = 20


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
        requests.post(url, json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def count_real(items):
    return len([i for i in items if isinstance(i, dict) and i.get("number") and not i.get("number").startswith("Номер")])


def get_or_create_seller(user_id, username):
    sellers = load_json(SELLERS_FILE)
    uid = str(user_id)
    if uid not in sellers:
        sellers[uid] = {
            "username": username or f"user_{uid}",
            "balance": 0,
            "commission": КОМИССИЯ,
            "total_sold": 0,
            "total_earned": 0,
            "products_count": 0
        }
        save_json(SELLERS_FILE, sellers)
    return sellers[uid]


@app.route('/')
def index():
    return "GhostSell API работает ✅"


@app.route('/api/balance', methods=['POST'])
def get_balance():
    data = request.json
    user_id = str(data.get('user_id', ''))
    balances = load_json(BALANCE_FILE)
    return jsonify({"balance": balances.get(user_id, 0)})


@app.route('/api/get_all_balances', methods=['POST'])
def get_all_balances():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    balances = load_json(BALANCE_FILE)
    return jsonify({"success": True, "balances": balances})


@app.route('/api/products')
def get_products():
    data = load_json(DATA_FILE)
    sellers = load_json(SELLERS_FILE)
    result = []
    for key, product in data.items():
        if product.get("hidden", False):
            continue
        real = count_real(product.get("items", []))
        if real > 0:
            seller_id = product.get("seller_id", "admin")
            seller_info = sellers.get(str(seller_id), {})
            result.append({
                "key": key,
                "name": product.get("name", key),
                "emoji": product.get("emoji", "🌍"),
                "price": product.get("price_rub", 0),
                "count": real,
                "desc": product.get("desc", ""),
                "seller": seller_info.get("username", "admin"),
                "seller_id": seller_id,
                "seller_verified": product.get("seller_verified", False)
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

    seller_id = product.get("seller_id", "admin")
    commission = КОМИССИЯ

    print(f"🔍 BUY: seller_id={seller_id}")

    if seller_id and str(seller_id) != "admin":
        sellers = load_json(SELLERS_FILE)
        sid = str(seller_id)

        if sid not in sellers:
            sellers[sid] = {
                "username": f"user_{sid}",
                "balance": 0,
                "commission": КОМИССИЯ,
                "total_sold": 0,
                "total_earned": 0,
                "products_count": 0
            }
            print(f"🔍 Создан продавец {sid}")

        commission = sellers[sid].get("commission", КОМИССИЯ)
        seller_share = round(price * (100 - commission) / 100)
        print(f"🔍 price={price}, commission={commission}%, share={seller_share}")

        sellers[sid]["balance"] = sellers[sid].get("balance", 0) + seller_share
        sellers[sid]["total_sold"] = sellers[sid].get("total_sold", 0) + 1
        sellers[sid]["total_earned"] = sellers[sid].get("total_earned", 0) + seller_share
        save_json(SELLERS_FILE, sellers)

        print(f"🔍 Баланс {sid} = {sellers[sid]['balance']}")

        send_telegram_message(int(sid),
            f"💰 *Новая продажа!*\n\n📦 {product.get('name')}\n💵 Продано за: {price} ₽\n🏦 Комиссия ({commission}%): {price - seller_share} ₽\n✅ Вам: {seller_share} ₽")

    orders = load_json(ORDERS_FILE)
    if user_id not in orders:
        orders[user_id] = []
    orders[user_id].append({
        "username": "mini_app", "product": product.get("name", product_key),
        "price_rub": price, "price": price, "status": "одобрен",
        "date": str(datetime.now()), "number": number, "phone": number
    })
    save_json(ORDERS_FILE, orders)

    discount_text = f"\n🎰 Скидка: {user_discount}%" if user_discount > 0 else ""
    send_telegram_message(user_id,
        f"✅ *Покупка совершена!*\n\n📦 {product.get('name')}\n💰 {price} ₽{discount_text}\n📱 Номер: `{number}`\n💳 Остаток: {balances[user_id]} ₽")

    return jsonify({"success": True, "number": number, "balance": balances[user_id], "message": f"Покупка успешна! Номер: {number}"})


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
    requests_data[user_id].append({"phone": phone, "order_index": order_index, "timestamp": str(datetime.now()), "status": "в ожидании"})
    save_json(CODE_REQUESTS_FILE, requests_data)
    for admin_id in АДМИНЫ:
        send_telegram_message(admin_id, f"🔑 *Запрос кода*\n\n👤 ID: `{user_id}`\n📱 Номер: `{phone}`\n📦 Заказ: #{order_index}")
    return jsonify({"success": True, "message": "Запрос отправлен"})


@app.route('/api/bonus_status', methods=['POST'])
def bonus_status():
    data = request.json
    user_id = str(data.get('user_id', ''))
    bonuses = load_json(BONUS_FILE)
    last_date = bonuses.get(user_id, {}).get('last_claim', '')
    today = str(datetime.now().date())
    return jsonify({"can_claim": last_date != today})


@app.route('/api/claim_bonus', methods=['POST'])
def claim_bonus():
    data = request.json
    user_id = str(data.get('user_id', ''))
    today = str(datetime.now().date())
    bonuses = load_json(BONUS_FILE)
    if bonuses.get(user_id, {}).get('last_claim') == today:
        return jsonify({"success": False, "error": "Уже забрано сегодня"})
    balances = load_json(BALANCE_FILE)
    balances[user_id] = balances.get(user_id, 0) + 5
    save_json(BALANCE_FILE, balances)
    bonuses[user_id] = {"last_claim": today}
    save_json(BONUS_FILE, bonuses)
    return jsonify({"success": True, "amount": 5})


@app.route('/api/top_buyers')
def top_buyers():
    orders = load_json(ORDERS_FILE)
    totals = {}
    for user_id, user_orders in orders.items():
        for o in user_orders:
            username = o.get('username', 'anon')
            price = o.get('price_rub') or o.get('price', 0)
            totals[username] = totals.get(username, 0) + price
    sorted_buyers = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    result = [{"username": u, "total": t} for u, t in sorted_buyers[:10]]
    return jsonify({"buyers": result})


@app.route('/api/wheel_status', methods=['POST'])
def wheel_status():
    data = request.json
    user_id = str(data.get('user_id', ''))
    wheels = load_json(WHEEL_FILE)
    last_spin = wheels.get(user_id, {}).get('last_spin', 0)
    now = datetime.now().timestamp()
    week_seconds = 7 * 24 * 60 * 60
    can_spin = (now - last_spin) >= week_seconds
    next_spin_in = 0 if can_spin else int(week_seconds - (now - last_spin))
    return jsonify({"can_spin": can_spin, "next_spin_in": next_spin_in})


@app.route('/api/spin_wheel', methods=['POST'])
def spin_wheel():
    data = request.json
    user_id = str(data.get('user_id', ''))
    discount = int(data.get('discount', 0))
    wheels = load_json(WHEEL_FILE)
    last_spin = wheels.get(user_id, {}).get('last_spin', 0)
    now = datetime.now().timestamp()
    if (now - last_spin) < 7 * 24 * 60 * 60:
        return jsonify({"success": False, "error": "Ещё рано"})
    wheels[user_id] = {"last_spin": now}
    save_json(WHEEL_FILE, wheels)
    if discount > 0:
        discounts = load_json(DISCOUNTS_FILE)
        discounts[user_id] = discount
        save_json(DISCOUNTS_FILE, discounts)
    return jsonify({"success": True, "discount": discount})


@app.route('/api/seller_profile', methods=['POST'])
def seller_profile():
    data = request.json
    user_id = str(data.get('user_id', ''))
    username = data.get('username', '')
    seller = get_or_create_seller(user_id, username)
    return jsonify({"success": True, "seller": seller, "commission": КОМИССИЯ})


@app.route('/api/seller_products', methods=['POST'])
def seller_products():
    data = request.json
    user_id = str(data.get('user_id', ''))
    products = load_json(DATA_FILE)
    result = []
    for key, product in products.items():
        if str(product.get("seller_id", "")) == user_id:
            result.append({"key": key, "name": product.get("name", key), "emoji": product.get("emoji", "🌍"), "price": product.get("price_rub", 0), "count": count_real(product.get("items", [])), "hidden": product.get("hidden", False)})
    return jsonify({"products": result})


@app.route('/api/seller_pending', methods=['POST'])
def seller_pending():
    data = request.json
    user_id = str(data.get('user_id', ''))
    pending = load_json(PENDING_FILE)
    result = []
    for pid, item in pending.items():
        if str(item.get("seller_id", "")) == user_id:
            # Только активные заявки
            if item.get("status") == "pending":
                result.append({
                    "id": pid, "name": item.get("name"), "price": item.get("price"),
                    "status": item.get("status", "pending"),
                    "reason": item.get("reason", ""), "date": item.get("date", "")
                })
    return jsonify({"pending": result})


@app.route('/api/seller_submit', methods=['POST'])
def seller_submit():
    data = request.json
    user_id = str(data.get('user_id', ''))
    username = data.get('username', '')
    name = data.get('name', '').strip()
    price = int(data.get('price', 0))
    desc = data.get('desc', '').strip()
    emoji = data.get('emoji', '🌍')
    numbers_text = data.get('numbers', '').strip()
    category = data.get('category', 'no_spam')

    if not name or price <= 0 or not numbers_text:
        return jsonify({"success": False, "error": "Заполни все поля"})
    if price < 30:
        return jsonify({"success": False, "error": "Минимальная цена 30 ₽"})
    if price > 10000:
        return jsonify({"success": False, "error": "Максимальная цена 10000 ₽"})

    numbers = [n.strip() for n in numbers_text.split(",") if n.strip()]
    if not numbers:
        return jsonify({"success": False, "error": "Введи хотя бы один номер"})

    pending = load_json(PENDING_FILE)
    pid = f"pending_{int(datetime.now().timestamp())}_{user_id}"
    items = [{"number": n, "category": category} for n in numbers]
    pending[pid] = {
        "seller_id": user_id, "seller_username": username, "name": name, "price": price,
        "desc": desc, "emoji": emoji, "items": items, "status": "pending", "date": str(datetime.now())
    }
    save_json(PENDING_FILE, pending)

    for admin_id in АДМИНЫ:
        send_telegram_message(admin_id, f"📥 *Новая заявка*\n\n👤 @{username or user_id}\n🆔 `{user_id}`\n📦 {name}\n💰 {price} ₽\n📱 Номеров: {len(numbers)}")

    return jsonify({"success": True, "message": "Заявка отправлена"})


@app.route('/api/seller_withdraw', methods=['POST'])
def seller_withdraw():
    data = request.json
    user_id = str(data.get('user_id', ''))
    amount = int(data.get('amount', 0))
    sellers = load_json(SELLERS_FILE)
    sid = str(user_id)
    if sid not in sellers:
        return jsonify({"success": False, "error": "Продавец не найден"})
    if sellers[sid].get("balance", 0) < amount:
        return jsonify({"success": False, "error": "Недостаточно средств"})
    if amount < 100:
        return jsonify({"success": False, "error": "Минимум 100 ₽"})
    for admin_id in АДМИНЫ:
        send_telegram_message(admin_id, f"💸 *Запрос на вывод*\n\n👤 @{sellers[sid].get('username')}\n🆔 `{user_id}`\n💰 {amount} ₽")
    return jsonify({"success": True, "message": "Запрос отправлен"})


@app.route('/api/admin/pending', methods=['POST'])
def admin_pending():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    pending = load_json(PENDING_FILE)
    active = []
    for pid, p in pending.items():
        if p.get("status") == "pending":
            active.append({
                "id": pid, "seller_id": p.get("seller_id"), "seller_username": p.get("seller_username"),
                "name": p.get("name"), "price": p.get("price"), "desc": p.get("desc", ""),
                "emoji": p.get("emoji", "🌍"), "items": p.get("items", [])
            })
    return jsonify({"pending": active})


@app.route('/api/admin/approve_pending', methods=['POST'])
def admin_approve_pending():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    pid = data.get('pid')
    pending = load_json(PENDING_FILE)
    if pid not in pending:
        return jsonify({"success": False, "error": "Заявка не найдена"})
    p = pending[pid]
    products = load_json(DATA_FILE)
    seller_id = p.get("seller_id")
    ts = int(datetime.now().timestamp())
    key = f"seller_{seller_id}_{ts}"
    products[key] = {
        "name": p.get("name"), "emoji": p.get("emoji", "🌍"),
        "price_rub": p.get("price"), "price_stars": round(p.get("price", 0) * 0.7),
        "desc": p.get("desc", ""), "hidden": False, "items": p.get("items", []),
        "seller_id": seller_id, "seller_verified": False
    }
    save_json(DATA_FILE, products)
    pending[pid]["status"] = "approved"
    save_json(PENDING_FILE, pending)
    sellers = load_json(SELLERS_FILE)
    sid = str(seller_id)
    if sid in sellers:
        sellers[sid]["products_count"] = sellers[sid].get("products_count", 0) + 1
        save_json(SELLERS_FILE, sellers)
    send_telegram_message(int(seller_id), f"✅ *Товар одобрен!*\n\n📦 {p.get('name')} — {p.get('price')} ₽\n\nОн уже в каталоге!")
    return jsonify({"success": True})


@app.route('/api/admin/decline_pending', methods=['POST'])
def admin_decline_pending():
    data = request.json
    if data.get('secret') != SYNC_SECRET:
        return jsonify({"success": False, "error": "Неверный ключ"})
    pid = data.get('pid')
    reason = data.get('reason', 'Не прошёл модерацию')
    pending = load_json(PENDING_FILE)
    if pid not in pending:
        return jsonify({"success": False, "error": "Заявка не найдена"})
    pending[pid]["status"] = "declined"
    pending[pid]["reason"] = reason
    save_json(PENDING_FILE, pending)
    seller_id = pending[pid].get("seller_id")
    send_telegram_message(int(seller_id), f"❌ *Товар отклонён:* {pending[pid].get('name')}\n\n📝 {reason}\n\nСвяжись с @zilfrec")
    return jsonify({"success": True})


# ========== ЧАТ ==========

@app.route('/api/chat/create', methods=['POST'])
def chat_create():
    data = request.json
    buyer_id = str(data.get('buyer_id', ''))
    seller_id = str(data.get('seller_id', ''))
    product_name = data.get('product', '')

    if not buyer_id or not seller_id:
        return jsonify({"success": False, "error": "Нет участников"})
    if buyer_id == seller_id:
        return jsonify({"success": False, "error": "Нельзя писать самому себе"})

    participants = sorted([buyer_id, seller_id])
    chat_id = f"{participants[0]}_{participants[1]}"

    chats = load_json(CHATS_FILE)
    if chat_id not in chats:
        chats[chat_id] = {
            "buyer_id": buyer_id, "seller_id": seller_id,
            "product": product_name, "messages": [],
            "created": str(datetime.now())
        }
        save_json(CHATS_FILE, chats)

    return jsonify({"success": True, "chat_id": chat_id})


@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    data = request.json
    chat_id = data.get('chat_id', '')
    from_id = str(data.get('from_id', ''))
    text = data.get('text', '').strip()

    if not chat_id or not from_id or not text:
        return jsonify({"success": False, "error": "Пустое сообщение"})

    chats = load_json(CHATS_FILE)
    if chat_id not in chats:
        return jsonify({"success": False, "error": "Чат не найден"})

    chat = chats[chat_id]
    if from_id not in [chat["buyer_id"], chat["seller_id"]]:
        return jsonify({"success": False, "error": "Нет доступа"})

    msg = {"from": from_id, "text": text, "date": str(datetime.now())}
    chat["messages"].append(msg)
    save_json(CHATS_FILE, chats)

    to_id = chat["seller_id"] if from_id == chat["buyer_id"] else chat["buyer_id"]
    try:
        send_telegram_message(int(to_id), f"💬 *Новое сообщение*\n\n{text[:200]}\n\nОткрой Mini App чтобы ответить.")
    except:
        pass

    return jsonify({"success": True})


@app.route('/api/chat/get', methods=['POST'])
def chat_get():
    data = request.json
    chat_id = data.get('chat_id', '')
    user_id = str(data.get('user_id', ''))

    chats = load_json(CHATS_FILE)
    if chat_id not in chats:
        return jsonify({"success": False, "error": "Чат не найден"})

    chat = chats[chat_id]
    if user_id not in [chat["buyer_id"], chat["seller_id"]]:
        return jsonify({"success": False, "error": "Нет доступа"})

    return jsonify({
        "success": True, "messages": chat["messages"],
        "buyer_id": chat["buyer_id"], "seller_id": chat["seller_id"],
        "product": chat.get("product", "")
    })


@app.route('/api/chat/list', methods=['POST'])
def chat_list():
    data = request.json
    user_id = str(data.get('user_id', ''))

    chats = load_json(CHATS_FILE)
    result = []
    for chat_id, chat in chats.items():
        if user_id in [chat["buyer_id"], chat["seller_id"]]:
            last_msg = chat["messages"][-1] if chat["messages"] else None
            other_id = chat["seller_id"] if user_id == chat["buyer_id"] else chat["buyer_id"]
            result.append({
                "chat_id": chat_id, "other_id": other_id,
                "product": chat.get("product", ""),
                "last_message": last_msg["text"] if last_msg else "Нет сообщений",
                "last_date": last_msg["date"] if last_msg else chat.get("created", "")
            })

    result.sort(key=lambda x: x["last_date"], reverse=True)
    return jsonify({"chats": result})


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
import os
import json
import time
import random
import hmac
import hashlib
from urllib.parse import unquote
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

# এনভায়রনমেন্ট ভেরিয়েবল লোড করা
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- কনফিগারেশন ---
BOT_TOKEN = os.getenv("8336857025:AAHU9LtgSGy5oifVfMk2Le92vkpk94pq6k8")
ADMIN_ID = os.getenv("7605281774")
FIREBASE_DB_URL = "https://snowman-adventure-4fa71-default-rtdb.firebaseio.com"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

GAME_URL = "https://alamin12071985-a11y.github.io/Snowman-Adventure/"
GROUP_URL = "https://t.me/snowmanadventurediscuss"
CHANNEL_URL = "https://t.me/snowmanadventurecommunity"

# সার্ভার স্টার্ট হওয়ার সময় টোকেন চেক করা
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing!")
else:
    print(f"✅ Bot Token Loaded: {BOT_TOKEN[:5]}*******")

# --- Firebase ইনিশিয়ালাইজেশন ---
try:
    if not firebase_admin._apps:
        firebase_key_json = os.getenv("FIREBASE_KEY")
        if firebase_key_json:
            cred_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(cred_dict)
        else:
            if os.path.exists("firebase-adminsdk.json"):
                cred = credentials.Certificate("firebase-adminsdk.json")
            else:
                raise Exception("Firebase credentials not found!")

        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
        print("✅ Firebase connected successfully!")
except Exception as e:
    print(f"❌ Firebase Error: {e}")

# --- শপ ডেটা ---
SHOP_ITEMS = {
    'coin_starter': {'stars': 10, 'reward': 5000, 'type': 'coin'},
    'coin_small': {'stars': 20, 'reward': 10000, 'type': 'coin'},
    'coin_medium': {'stars': 60, 'reward': 40000, 'type': 'coin'},
    'coin_large': {'stars': 120, 'reward': 100000, 'type': 'coin'},
    'coin_mega': {'stars': 220, 'reward': 220000, 'type': 'coin'},
    'booster_3d': {'stars': 20, 'type': 'booster', 'duration': 3},
    'booster_15d': {'stars': 70, 'type': 'booster', 'duration': 15},
    'booster_30d': {'stars': 120, 'type': 'booster', 'duration': 30},
    'autotap_1d': {'stars': 20, 'type': 'autotap', 'duration': 1},
    'autotap_7d': {'stars': 80, 'type': 'autotap', 'duration': 7},
    'autotap_30d': {'stars': 200, 'type': 'autotap', 'duration': 30},
}

# --- SPIN WHEEL CONFIGURATION ---
SPIN_PRIZES = [0.001, 0.005, 0.01, 0.02, 0.1, 0.5, 0.002, 0.008]
SPIN_WEIGHTS = [40, 25, 10, 5, 1, 0.5, 15, 3.5] 

# --- হেল্পার ফাংশন ---
def save_bot_user(chat_id):
    try:
        ref = db.reference(f'bot_users/{chat_id}')
        ref.set(True)
    except Exception as e:
        print(f"Error saving user: {e}")

def get_all_users():
    try:
        ref = db.reference('bot_users')
        users = ref.get()
        if users:
            return list(users.keys())
        return []
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

def send_telegram_message(chat_id, text, reply_markup=None):
    payload = { "chat_id": chat_id, "text": text }
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(f"{BASE_URL}/sendMessage", json=payload)
    except Exception as e: print(f"Telegram API Error: {e}")

def update_user_perks(user_id, item_id):
    item = SHOP_ITEMS.get(item_id)
    if not item: return False
    
    ref = db.reference(f'users/{user_id}')
    data = ref.get() or {}
    now_ms = int(time.time() * 1000)

    if item['type'] == 'coin':
        new_balance = data.get('balance', 0) + item['reward']
        ref.update({'balance': new_balance})
    
    elif item['type'] in ['booster', 'autotap']:
        field = f"{item['type']}EndTime"
        current_end = data.get(field, 0)
        start_point = max(now_ms, current_end)
        duration_ms = item['duration'] * 24 * 60 * 60 * 1000
        new_end = start_point + duration_ms
        ref.update({field: new_end})
    
    return True

# --- নতুন রাউট: AUTH (লগিন এবং ডেটা লোড) ---
@app.route('/auth', methods=['POST'])
def auth_user():
    req_data = request.json
    user_id = str(req_data.get('user_id'))
    
    # টেলিগ্রাম ভ্যালিডেশন (Simple Version)
    # প্রোডাকশনের জন্য initData ভ্যালিডেশন করা উচিত
    
    if not user_id:
        return jsonify({"error": "User ID missing"}), 400

    ref = db.reference(f'users/{user_id}')
    user_data = ref.get()

    if not user_data:
        # নতুন ইউজার ডিফল্ট ডেটা
        user_data = {
            "balance": 500,
            "tonBalance": 0.0,
            "level": 1,
            "referralCount": 0,
            "tapCount": 0,
            "lastActive": int(time.time() * 1000)
        }
        ref.set(user_data)
    else:
        # বিদ্যমান ইউজারের লাস্ট এক্টিভ আপডেট
        ref.update({"lastActive": int(time.time() * 1000)})

    return jsonify(user_data)

# --- নতুন রাউট: SYNC TAPS (ট্যাপ সেভ করা) ---
@app.route('/sync_taps', methods=['POST'])
def sync_taps():
    try:
        req_data = request.json
        user_id = str(req_data.get('user_id'))
        taps = int(req_data.get('taps', 0))

        if not user_id or taps <= 0:
            return jsonify({"status": "error", "reason": "Invalid data"}), 400

        ref = db.reference(f'users/{user_id}')
        user_data = ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "reason": "User not found"}), 404

        # ব্যালেন্স আপডেট লজিক
        # এখানে সার্ভার সাইড লেভেল চেক করে গুণ করা যেতে পারে নিরাপত্তার জন্য
        level = user_data.get('level', 1)
        # সিম্পল লজিক: ধরে নিচ্ছি ফ্রন্টএন্ড থেকে শুধু ট্যাপ সংখ্যা আসছে
        # আপনি চাইলে এখানে tapMultiplier লজিকও যোগ করতে পারেন
        earned_coins = taps * level 
        
        new_balance = user_data.get('balance', 0) + earned_coins
        new_tap_count = user_data.get('tapCount', 0) + taps

        ref.update({
            'balance': new_balance,
            'tapCount': new_tap_count
        })

        return jsonify({"status": "ok", "balance": new_balance})

    except Exception as e:
        print(f"Sync Error: {e}")
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route('/create_invoice', methods=['POST'])
def create_invoice():
    req_data = request.json
    user_id = req_data.get('user_id')
    item_id = req_data.get('item_id')
    
    print(f"🔹 Invoice Request: User={user_id}, Item={item_id}")

    if not user_id or not item_id:
        return jsonify({"ok": False, "error": "Missing data"}), 400

    item = SHOP_ITEMS.get(item_id)
    if not item: 
        return jsonify({"ok": False, "error": "Item not found"}), 400

    payload = {
        "title": f"Buy {item_id.replace('_', ' ').title()}",
        "description": "Boost your Snowman Adventure!",
        "payload": f"{item_id}_{user_id}",
        "provider_token": "", 
        "currency": "XTR", 
        "prices": [{"label": "Price", "amount": int(item['stars'])}] 
    }
    
    try:
        r = requests.post(f"{BASE_URL}/createInvoiceLink", json=payload)
        resp_data = r.json()
        return jsonify(resp_data)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/spin_wheel', methods=['POST'])
def spin_wheel():
    req_data = request.json
    user_id = req_data.get('user_id')
    
    if not user_id:
        return jsonify({"result": False, "error": "User ID required"}), 400
    
    ref = db.reference(f'users/{user_id}')
    user_data = ref.get() or {}
    
    # --- Cooldown Logic (24 Hours) ---
    last_spin = user_data.get('lastSpinTime', 0)
    current_time = int(time.time() * 1000)
    cooldown_ms = 24 * 60 * 60 * 1000 # 24 Hours
    
    if (current_time - last_spin) < cooldown_ms:
        remaining_sec = (cooldown_ms - (current_time - last_spin)) / 1000
        hours = int(remaining_sec // 3600)
        minutes = int((remaining_sec % 3600) // 60)
        return jsonify({
            "result": False, 
            "error": f"Wait {hours}h {minutes}m for next spin!"
        })

    # Spin Logic
    chosen_index = random.choices(range(8), weights=SPIN_WEIGHTS, k=1)[0]
    prize_amount = SPIN_PRIZES[chosen_index]
    
    current_ton = float(user_data.get('tonBalance', 0.0))
    new_ton = current_ton + prize_amount
    
    ref.update({
        'tonBalance': new_ton,
        'lastSpinTime': current_time
    })
    
    # [FIX] ভেরিয়েবল নাম new_ton_balance করা হয়েছে ফ্রন্টএন্ডের সাথে মিল রাখতে
    return jsonify({
        "result": True,
        "index": chosen_index,
        "prize": prize_amount,
        "new_ton_balance": new_ton 
    })

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    if 'pre_checkout_query' in update:
        query_id = update['pre_checkout_query']['id']
        requests.post(f"{BASE_URL}/answerPreCheckoutQuery", json={
            "pre_checkout_query_id": query_id, 
            "ok": True
        })
        return "OK", 200

    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg.get('from', {}).get('id')
        save_bot_user(chat_id)

        if 'successful_payment' in msg:
            payload = msg['successful_payment']['invoice_payload']
            try:
                item_id, uid = payload.split('_', 1)
                if update_user_perks(uid, item_id):
                    send_telegram_message(chat_id, f"✅ Payment Successful! Your {item_id} rewards have been added.")
            except Exception as e:
                print(f"Payment logic error: {e}")
            return "OK", 200

        if text.startswith('/broadcast') and str(user_id) == str(ADMIN_ID):
            broadcast_msg = text.replace('/broadcast', '').strip()
            if broadcast_msg:
                users = get_all_users()
                for uid in users:
                    try:
                        requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": uid, "text": broadcast_msg})
                        time.sleep(0.05)
                    except: continue
                send_telegram_message(chat_id, "✅ Broadcast sent.")
            return "OK", 200

        keyboard = {
            "inline_keyboard": [
                [{"text": "🚀 Play Game ❄️", "web_app": {"url": GAME_URL}}],
                [{"text": "Join Community 📢", "url": CHANNEL_URL}],
                [{"text": "Join Discussion 💬", "url": GROUP_URL}]
            ]
        }

        if text == '/start':
            welcome_text = "Welcome to Snowman Adventure! ☃️\nTap Play to start earning!"
            send_telegram_message(chat_id, welcome_text, keyboard)
        else:
            send_telegram_message(chat_id, "Tap Play to open the app! 👇", keyboard)

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

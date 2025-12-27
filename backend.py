import os
import json
import time
import hmac
import hashlib
import random
import requests
from urllib.parse import unquote
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

# --- SETUP & CONFIGURATION ---
load_dotenv()

app = Flask(__name__)
CORS(app) # প্রোডাকশনে চাইলে নির্দিষ্ট ডোমেইন সেট করতে পারেন

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
FIREBASE_DB_URL = "https://snowman-adventure-4fa71-default-rtdb.firebaseio.com" # আপনার DB URL
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Game Constants
GAME_URL = "https://alamin12071985-a11y.github.io/Snowman-Adventure/"
CHANNEL_URL = "https://t.me/snowmanadventurecommunity"

# --- FIREBASE CONNECTION (Render Friendly) ---
# Render এ 'FIREBASE_CREDENTIALS' নামে Environment Variable সেট করতে হবে
try:
    if not firebase_admin._apps:
        firebase_json = os.getenv("FIREBASE_CREDENTIALS")
        if firebase_json:
            # Environment Variable থেকে JSON লোড করা (Render এর জন্য)
            cred = credentials.Certificate(json.loads(firebase_json))
        elif os.path.exists("firebase-adminsdk.json"):
            # লোকাল টেস্টিং এর জন্য ফাইল থেকে
            cred = credentials.Certificate("firebase-adminsdk.json")
        else:
            raise Exception("No Firebase Credentials Found!")

        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
        print("✅ Firebase Connected Successfully")
except Exception as e:
    print(f"❌ Firebase Error: {e}")

# --- DATA CONFIGURATION ---
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

SPIN_PRIZES = [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 0.05, 0.2]
SPIN_WEIGHTS = [40, 25, 10, 5, 1, 0.5, 15, 3.5]

# --- SECURITY FUNCTION (ANTI-HACK) ---
def verify_telegram_data(init_data):
    """
    টেলিগ্রাম থেকে আসা ডাটা ভেরিফাই করে।
    এটি নিশ্চিত করে যে রিকোয়েস্টটি আসল টেলিগ্রাম অ্যাপ থেকেই আসছে।
    """
    if not BOT_TOKEN: return None
    try:
        parsed_data = unquote(init_data)
        data_parts = parsed_data.split('&')
        
        hash_part = next((part for part in data_parts if part.startswith('hash=')), None)
        if not hash_part: return None
        
        received_hash = hash_part.split('=')[1]
        data_to_check = sorted([part for part in data_parts if not part.startswith('hash=')])
        data_check_string = '\n'.join(data_to_check)
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != received_hash:
            return None
            
        user_part = next((part for part in data_parts if part.startswith('user=')), None)
        user_json = user_part.split('user=')[1]
        return json.loads(user_json)
    except Exception:
        return None

# --- HELPER FUNCTIONS ---
def send_telegram_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(f"{BASE_URL}/sendMessage", json=payload)
    except: pass

def update_user_perks(user_id, item_id):
    """শপ থেকে আইটেম কিনলে ডাটাবেস আপডেট করে"""
    item = SHOP_ITEMS.get(item_id)
    if not item: return False
    
    ref = db.reference(f'users/{user_id}')
    data = ref.get() or {}
    now_ms = int(time.time() * 1000)

    updates = {}
    if item['type'] == 'coin':
        updates['balance'] = data.get('balance', 0) + item['reward']
    
    elif item['type'] in ['booster', 'autotap']:
        field = f"{item['type']}EndTime"
        current_end = data.get(field, 0)
        start_point = max(now_ms, current_end)
        duration_ms = item['duration'] * 24 * 60 * 60 * 1000
        updates[field] = start_point + duration_ms
        
    if updates:
        ref.update(updates)
        return True
    return False

# --- API ENDPOINTS ---

@app.route('/')
def home():
    return "Snowman Security Server is Active!"

# 1. AUTH & LOAD DATA (Secure)
@app.route('/auth', methods=['POST'])
def auth_user():
    init_data = request.headers.get('Authorization')
    user_info = verify_telegram_data(init_data)
    
    if not user_info:
        return jsonify({"error": "Unauthorized"}), 403
        
    user_id = str(user_info['id'])
    ref = db.reference(f'users/{user_id}')
    user_db = ref.get()
    
    if not user_db:
        # নতুন ইউজার তৈরি
        new_user = {
            "balance": 500,
            "tonBalance": 0.0,
            "level": 1,
            "username": user_info.get('username', 'Unknown'),
            "last_sync": int(time.time()),
            "referralCount": 0
        }
        # রেফারেল চেকিং (start_param থেকে)
        # ফ্রন্টেন্ড থেকে আলাদাভাবে start_param পাঠাতে হবে অথবা initData চেক করতে হবে
        ref.set(new_user)
        return jsonify(new_user)
    
    return jsonify(user_db)

# 2. SYNC TAPS (Anti-Cheat & Referral Commission)
@app.route('/sync_taps', methods=['POST'])
def sync_taps():
    init_data = request.headers.get('Authorization')
    user_info = verify_telegram_data(init_data)
    
    if not user_info:
        return jsonify({"status": "error", "reason": "Unauthorized"}), 403

    payload = request.json
    taps_count = payload.get('taps', 0)
    user_id = str(user_info['id'])
    
    ref = db.reference(f'users/{user_id}')
    user_db = ref.get()
    
    if not user_db:
        return jsonify({"status": "error", "reason": "User not found"}), 404

    # --- Anti-Cheat Logic ---
    current_time = int(time.time())
    last_sync = user_db.get('last_sync', current_time - 5)
    time_diff = current_time - last_sync
    
    # বুস্টার চেক করা
    multiplier = 1
    if user_db.get('boosterEndTime', 0) > (current_time * 1000):
        multiplier = 2
    
    # ধরা যাক মানুষ সর্বোচ্চ সেকেন্ডে ১৫ টা ট্যাপ করতে পারে
    max_possible = (time_diff * 15) + 50 # ৫০ বাফার
    
    if taps_count > max_possible:
        # হ্যাক ডিটেক্টেড - ট্যাপ বাতিল
        print(f"⚠️ Suspicious activity: User {user_id}")
        return jsonify({
            "status": "rejected", 
            "balance": user_db.get('balance', 0)
        })

    # ব্যালেন্স ক্যালকুলেশন
    level = user_db.get('level', 1)
    earned_coins = taps_count * level * multiplier
    new_balance = user_db.get('balance', 0) + earned_coins
    
    # 10% Referral Commission (Safe Transaction)
    referrer_id = user_db.get('referredBy')
    if referrer_id and earned_coins > 10:
        commission = int(earned_coins * 0.10)
        if commission > 0:
            try:
                # রেফারারের ব্যালেন্স অ্যাটমিকভাবে আপডেট করা
                r_ref = db.reference(f'users/{referrer_id}/balance')
                r_ref.transaction(lambda current: (current or 0) + commission)
            except: pass

    # ইউজারের ডাটা আপডেট
    ref.update({
        "balance": new_balance,
        "last_sync": current_time,
        "tapCount": user_db.get('tapCount', 0) + taps_count
    })
    
    return jsonify({"status": "ok", "balance": new_balance})

# 3. SECURE SPIN WHEEL
@app.route('/spin_wheel', methods=['POST'])
def spin_wheel_secure():
    init_data = request.headers.get('Authorization')
    user_info = verify_telegram_data(init_data)
    
    if not user_info:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
        
    user_id = str(user_info['id'])
    ref = db.reference(f'users/{user_id}')
    user_db = ref.get() or {}
    
    # 24 Hour Cooldown Check
    last_spin = user_db.get('lastSpinTime', 0)
    now_ms = int(time.time() * 1000)
    
    # একদিন পার হয়েছে কিনা চেক (এখানে ৮৬৪০০০০০ ms = ২৪ ঘন্টা)
    if (now_ms - last_spin) < 86400000:
        return jsonify({"ok": False, "error": "Cooldown active"}), 400
        
    # Server-side Randomness (Hack proof)
    chosen_index = random.choices(range(8), weights=SPIN_WEIGHTS, k=1)[0]
    prize_amount = SPIN_PRIZES[chosen_index]
    
    new_ton = float(user_db.get('tonBalance', 0.0)) + prize_amount
    
    ref.update({
        'tonBalance': new_ton,
        'lastSpinTime': now_ms
    })
    
    return jsonify({
        "result": True,
        "index": chosen_index,
        "prize": prize_amount,
        "new_ton_balance": new_ton
    })

# 4. PAYMENT & SHOP
@app.route('/create_invoice', methods=['POST'])
def create_invoice():
    # এখানে initData চেক করা ভালো, তবে পেমেন্টের জন্য শিথিল করা যায়
    req_data = request.json
    user_id = req_data.get('user_id')
    item_id = req_data.get('item_id')
    
    item = SHOP_ITEMS.get(item_id)
    if not item or not user_id:
        return jsonify({"ok": False}), 400

    payload = {
        "title": f"Buy {item_id.replace('_', ' ').title()}",
        "description": "Upgrade your game!",
        "payload": f"{item_id}_{user_id}",
        "provider_token": "", # Stars Payment
        "currency": "XTR",
        "prices": [{"label": "Price", "amount": item['stars']}]
    }
    r = requests.post(f"{BASE_URL}/createInvoiceLink", json=payload)
    return jsonify(r.json())

# 5. TELEGRAM WEBHOOK (Bot Logic)
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    
    if 'pre_checkout_query' in update:
        requests.post(f"{BASE_URL}/answerPreCheckoutQuery", json={
            "pre_checkout_query_id": update['pre_checkout_query']['id'], 
            "ok": True
        })
        return "OK", 200

    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        
        # Payment Success Handling
        if 'successful_payment' in msg:
            try:
                data = msg['successful_payment']['invoice_payload']
                item_id, uid = data.split('_', 1)
                if update_user_perks(uid, item_id):
                    send_telegram_message(chat_id, "✅ Payment Successful! Reward Added.")
            except: pass
            return "OK", 200

        # Welcome Message
        text = msg.get('text', '')
        if text.startswith('/start'):
            # স্টার্ট প্যারামিটার হ্যান্ডলিং (রেফারেল)
            # /start 12345 (এখানে 12345 হলো রেফারার আইডি)
            args = text.split(' ')
            if len(args) > 1:
                referrer_id = args[1]
                # এখানে রেফারেল লজিক ডাটাবেসে সেভ করতে পারেন যদি ইউজার নতুন হয়
                # ফ্রন্টেন্ড থেকেও হ্যান্ডেল করা যায়, তবে ব্যাকএন্ডে রাখা নিরাপদ

            welcome_text = "☃️ *Welcome to Snowman Adventure!*\nTap, Earn, and Win Real Crypto!"
            kb = {"inline_keyboard": [[{"text": "🎮 Play Now", "web_app": {"url": GAME_URL}}],
                                      [{"text": "📢 Community", "url": CHANNEL_URL}]]}
            send_telegram_message(chat_id, welcome_text, kb)

    return "OK", 200

if __name__ == '__main__':
    # লোকাল পিসিতে রান করার জন্য
    app.run(host='0.0.0.0', port=5000)

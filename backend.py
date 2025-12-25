import os
import json
import time
import random
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

# এনভায়রনমেন্ট ভেরিয়েবল লোড করা (লোকাল পিসির জন্য)
load_dotenv()

app = Flask(__name__)
# CORS Allow all (প্রোডাকশনে নির্দিষ্ট ডোমেইন দিলে ভালো)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- কনফিগারেশন (Env Variables থেকে নেওয়া) ---
BOT_TOKEN = os.getenv("BOT_TOKEN") # .env ফাইলে বা সার্ভার কনফিগে সেট করবেন
ADMIN_ID = os.getenv("ADMIN_ID") # .env ফাইলে সেট করবেন
FIREBASE_DB_URL = "https://snowman-adventure-4fa71-default-rtdb.firebaseio.com"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# গেমের ওয়েব লিংক
GAME_URL = "https://alamin12071985-a11y.github.io/Snowman-Adventure/"
GROUP_URL = "https://t.me/snowmanadventurediscuss"
CHANNEL_URL = "https://t.me/snowmanadventurecommunity"

# --- Firebase ইনিশিয়ালাইজেশন (Advanced Secure Way) ---
try:
    if not firebase_admin._apps:
        # অপশন ১: যদি সার্ভারে Environment Variable হিসেবে থাকে (Render/Railway এর জন্য বেস্ট)
        firebase_key_json = os.getenv("FIREBASE_KEY")
        
        if firebase_key_json:
            cred_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(cred_dict)
        else:
            # অপশন ২: লোকাল পিসিতে ফাইল থেকে
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
# 8 Segments (Index 0 to 7)
SPIN_PRIZES = [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 0.05, 0.2]
# জেতার চান্স কন্ট্রোল (Total doesn't have to be 100, just ratio)
# [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 0.05, 0.2]
SPIN_WEIGHTS = [40, 25, 10, 5, 1, 0.5, 15, 3.5] 

# --- হেল্পার ফাংশন ---

def save_bot_user(chat_id):
    """বট ইউজারদের লিস্ট সেভ করা"""
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
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload)
    except Exception as e:
        print(f"Telegram API Error: {e}")

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
        # যদি বর্তমান সময় শেষের সময়ের চেয়ে কম হয় (অর্থাৎ একটিভ আছে), তাহলে শেষের সময় থেকেই যোগ হবে
        start_point = max(now_ms, current_end)
        duration_ms = item['duration'] * 24 * 60 * 60 * 1000
        new_end = start_point + duration_ms
        ref.update({field: new_end})
    
    return True

# --- রাউটসমূহ ---

@app.route('/')
def home():
    return "Snowman Adventure Backend is Running Securely!"

@app.route('/create_invoice', methods=['POST'])
def create_invoice():
    req_data = request.json
    user_id = req_data.get('user_id')
    item_id = req_data.get('item_id')
    
    if not user_id or not item_id:
        return jsonify({"ok": False, "error": "Missing data"}), 400

    item = SHOP_ITEMS.get(item_id)
    if not item: 
        return jsonify({"ok": False, "error": "Item not found"}), 400

    payload = {
        "title": f"Buy {item_id.replace('_', ' ').title()}",
        "description": "Boost your Snowman Adventure!",
        "payload": f"{item_id}_{user_id}",
        "provider_token": "", # Stars Payment (Empty for digital goods)
        "currency": "XTR", 
        "prices": [{"label": "Price", "amount": item['stars']}] 
    }
    
    r = requests.post(f"{BASE_URL}/createInvoiceLink", json=payload)
    return jsonify(r.json())

# --- SPIN WHEEL LOGIC (SECURE) ---
@app.route('/spin_wheel', methods=['POST'])
def spin_wheel():
    req_data = request.json
    user_id = req_data.get('user_id')
    
    if not user_id:
        return jsonify({"ok": False, "error": "User ID required"}), 400
    
    # Firebase থেকে চেক করুন লাস্ট স্পিন কখন হয়েছে (Backend Validation)
    ref = db.reference(f'users/{user_id}')
    user_data = ref.get() or {}
    last_spin = user_data.get('lastSpinTime', 0)
    
    # বর্তমান তারিখ চেক করা (Cooldown)
    # (Optional: এখানে আপনি সার্ভার সাইড টাইমার লজিক বসাতে পারেন)
    
    # স্পিন ক্যালকুলেশন
    chosen_index = random.choices(range(8), weights=SPIN_WEIGHTS, k=1)[0]
    prize_amount = SPIN_PRIZES[chosen_index]
    
    # আপডেট ব্যালেন্স
    current_ton = float(user_data.get('tonBalance', 0.0))
    new_ton = current_ton + prize_amount
    
    ref.update({
        'tonBalance': new_ton,
        'lastSpinTime': int(time.time() * 1000)
    })
    
    # ফ্রন্টেন্ডকে রেজাল্ট পাঠানো
    return jsonify({
        "result": True,
        "index": chosen_index,
        "prize": prize_amount,
        "new_balance": new_ton
    })

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    # 1. Payment Pre-Checkout (Must accept within 10s)
    if 'pre_checkout_query' in update:
        query_id = update['pre_checkout_query']['id']
        requests.post(f"{BASE_URL}/answerPreCheckoutQuery", json={
            "pre_checkout_query_id": query_id, 
            "ok": True
        })
        return "OK", 200

    # 2. Message Handling
    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg.get('from', {}).get('id')

        # ইউজার সেভ করা
        save_bot_user(chat_id)

        # পেমেন্ট সফল হলে
        if 'successful_payment' in msg:
            payload = msg['successful_payment']['invoice_payload']
            try:
                item_id, uid = payload.split('_', 1)
                if update_user_perks(uid, item_id):
                    send_telegram_message(chat_id, f"✅ Payment Successful! Your {item_id} rewards have been added.")
            except Exception as e:
                print(f"Payment logic error: {e}")
            return "OK", 200

        # --- ADMIN BROADCAST ---
        if text.startswith('/broadcast') and str(user_id) == str(ADMIN_ID):
            broadcast_msg = text.replace('/broadcast', '').strip()
            if broadcast_msg:
                users = get_all_users()
                count = 0
                send_telegram_message(chat_id, f"📡 Sending to {len(users)} users...")
                for uid in users:
                    try:
                        send_telegram_message(uid, broadcast_msg)
                        count += 1
                        time.sleep(0.05)
                    except:
                        continue
                send_telegram_message(chat_id, f"✅ Sent to {count} users.")
            else:
                send_telegram_message(chat_id, "Usage: `/broadcast Your Message`")
            return "OK", 200

        # --- WELCOME MESSAGE ---
        welcome_text = (
            "☃️ **Welcome to Snowman Adventure!** ❄️\n\n"
            "Tap to play, earn coins, and upgrade your Snowman! 🏆\n\n"
            "👇 **Start Now!**"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "🚀 Play Game ❄️", "web_app": {"url": GAME_URL}}],
                [{"text": "Join Community", "url": CHANNEL_URL}]
            ]
        }
        send_telegram_message(chat_id, welcome_text, keyboard)

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

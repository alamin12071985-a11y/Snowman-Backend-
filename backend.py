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

# এনভায়রনমেন্ট ভেরিয়েবল লোড করা
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- কনফিগারেশন ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
FIREBASE_DB_URL = "https://snowman-adventure-4fa71-default-rtdb.firebaseio.com"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

GAME_URL = "https://alamin12071985-a11y.github.io/Snowman-Adventure/"
GROUP_URL = "https://t.me/snowmanadventurediscuss"
CHANNEL_URL = "https://t.me/snowmanadventurecommunity"

# সার্ভার স্টার্ট হওয়ার সময় টোকেন চেক করা (Debugging)
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing! Please set it in Environment Variables.")
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
SPIN_PRIZES = [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 0.05, 0.2]
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
    payload = {
        "chat_id": chat_id,
        "text": text,
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
    
    # 1. Debugging: চেক করা হচ্ছে ডেটা আসছে কিনা
    print(f"🔹 Invoice Request: User={user_id}, Item={item_id}")

    if not user_id or not item_id:
        return jsonify({"ok": False, "error": "Missing data"}), 400

    item = SHOP_ITEMS.get(item_id)
    if not item: 
        print(f"❌ Item not found in SHOP_ITEMS: {item_id}")
        return jsonify({"ok": False, "error": "Item not found"}), 400

    # 2. Payload তৈরি (Stars Payment)
    payload = {
        "title": f"Buy {item_id.replace('_', ' ').title()}",
        "description": "Boost your Snowman Adventure!",
        "payload": f"{item_id}_{user_id}",
        "provider_token": "",  # Telegram Stars এর জন্য এটি ফাঁকা থাকতে হবে
        "currency": "XTR", 
        "prices": [{"label": "Price", "amount": int(item['stars'])}] # int নিশ্চিত করা হলো
    }
    
    try:
        # 3. Telegram API কল করা
        r = requests.post(f"{BASE_URL}/createInvoiceLink", json=payload)
        resp_data = r.json()
        
        # 4. Debugging: টেলিগ্রামের রেসপন্স চেক করা
        if not resp_data.get("ok"):
            print(f"❌ Telegram API Error: {resp_data}") # সার্ভার লগে এরর দেখাবে
        else:
            print(f"✅ Invoice Link Created: {resp_data.get('result')}")

        return jsonify(resp_data)
        
    except Exception as e:
        print(f"❌ Server Error in create_invoice: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/spin_wheel', methods=['POST'])
def spin_wheel():
    req_data = request.json
    user_id = req_data.get('user_id')
    
    if not user_id:
        return jsonify({"ok": False, "error": "User ID required"}), 400
    
    ref = db.reference(f'users/{user_id}')
    user_data = ref.get() or {}
    
    chosen_index = random.choices(range(8), weights=SPIN_WEIGHTS, k=1)[0]
    prize_amount = SPIN_PRIZES[chosen_index]
    
    current_ton = float(user_data.get('tonBalance', 0.0))
    new_ton = current_ton + prize_amount
    
    ref.update({
        'tonBalance': new_ton,
        'lastSpinTime': int(time.time() * 1000)
    })
    
    return jsonify({
        "result": True,
        "index": chosen_index,
        "prize": prize_amount,
        "new_balance": new_ton
    })

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    # 1. Payment Pre-Checkout
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

        # --- ৩টি বাটন কনফিগারেশন ---
        keyboard = {
            "inline_keyboard": [
                [{"text": "🚀 Play Game ❄️", "web_app": {"url": GAME_URL}}],
                [{"text": "Join Community 📢", "url": CHANNEL_URL}],
                [{"text": "Join Discussion 💬", "url": GROUP_URL}]
            ]
        }

        # --- মেসেজ লজিক ---
        if text == '/start':
            # ইউজার যখন START এ ক্লিক করবে
            welcome_text = (
                "Alright, welcome to Snowman Adventure ☃️👋\n"
                "You’re officially in!\n"
                "This mini app is all about having fun, earning rewards, and exploring step by step — no rush, just vibes ❄️\n"
                "Tap around, complete tasks, invite friends, and see how far you can go 🚀\n"
                "We’re still building and improving things, so if anything feels confusing or off, let us know. Your feedback actually matters here 💬\n"
                "Good luck on your journey, and enjoy the adventure!\n"
                "Let’s see how far your snowman can go ⛄️✨"
            )
            send_telegram_message(chat_id, welcome_text, keyboard)
        
        else:
            # ইউজার যখন অন্য কিছু লিখবে
            reply_text = (
                "Hey there! 👋❄️\n"
                "Looks like you sent a message — nice 😄\n"
                "Just a quick note: Snowman Adventure works through the buttons and features inside the mini app, not regular chat messages.\n"
                "👉 Use the app menu\n"
                "👉 Tap, complete tasks, invite friends\n"
                "👉 Explore and earn rewards along the way\n"
                "If you’re stuck or something feels off, don’t worry — we’re improving things step by step, and your feedback helps a lot 💬\n"
                "Now jump back into the app and keep the adventure going"
            )
            send_telegram_message(chat_id, reply_text, keyboard)

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

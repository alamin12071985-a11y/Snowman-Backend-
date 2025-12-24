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
# CORS Allow all
CORS(app, resources={r"/*": {"origins": "*"}})

# --- কনফিগারেশন ---
BOT_TOKEN = "8336857025:AAHU9LtgSGy5oifVfMk2Le92vkpk94pq6k8" # আপনার বটের টোকেন
ADMIN_ID = 7605281774  # আপনার অ্যাডমিন আইডি
FIREBASE_DB_URL = "https://snowman-adventure-4fa71-default-rtdb.firebaseio.com"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# গেমের ওয়েব লিংক (GitHub Pages বা হোস্টেড লিংক)
GAME_URL = "https://alamin12071985-a11y.github.io/Snowman-Adventure/"
GROUP_URL = "https://t.me/snowmanadventurediscuss"
CHANNEL_URL = "https://t.me/snowmanadventurecommunity"

# --- Firebase ইনিশিয়ালাইজেশন ---
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-adminsdk.json")
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
        print("Firebase connected!")
except Exception as e:
    print(f"Firebase Error: {e}")

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
    'noads_1d': {'stars': 15, 'type': 'noads', 'duration': 1},
    'noads_15d': {'stars': 60, 'type': 'noads', 'duration': 15},
    'noads_30d': {'stars': 100, 'type': 'noads', 'duration': 30},
    'skin_rare': {'stars': 30, 'type': 'skin', 'reward': 'Rare Skin'},
    'skin_epic': {'stars': 60, 'type': 'skin', 'reward': 'Epic Skin'},
    'skin_legendary': {'stars': 90, 'type': 'skin', 'reward': 'Legendary Skin'},
}

# --- SPIN WHEEL CONFIGURATION ---
# 8 Segments on the wheel
# Prizes are in TON amounts
SPIN_PRIZES = [0.001, 0.0, 0.05, 0.0, 1.0, 0.0, 0.1, 0.0]
# Probabilities for each index (0 to 7) - must sum up to 100 or be proportional
# High chance for 0, Low chance for high amounts to prevent hacks/losses
SPIN_WEIGHTS = [15, 40, 5, 20, 1, 15, 3, 1]

# --- হেল্পার ফাংশন ---

def save_bot_user(chat_id):
    """বট ইউজারদের লিস্ট সেভ করা (ব্রডকাস্টের জন্য)"""
    try:
        ref = db.reference(f'bot_users/{chat_id}')
        ref.set(True)
    except Exception as e:
        print(f"Error saving user: {e}")

def get_all_users():
    """ফায়ারবেস থেকে সব বট ইউজারের লিস্ট আনা"""
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
    
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def update_user_perks(user_id, item_id):
    item = SHOP_ITEMS.get(item_id)
    if not item: return False
    
    ref = db.reference(f'users/{user_id}')
    data = ref.get() or {}
    now_ms = int(time.time() * 1000)

    if item['type'] == 'coin':
        new_balance = data.get('balance', 0) + item['reward']
        ref.update({'balance': new_balance})
    
    elif item['type'] in ['booster', 'autotap', 'noads']:
        field = f"{item['type']}EndTime"
        current_end = data.get(field, now_ms)
        duration_ms = item['duration'] * 24 * 60 * 60 * 1000
        new_end = max(now_ms, current_end) + duration_ms
        ref.update({field: new_end})
    
    return True

# --- রাউটসমূহ ---

@app.route('/')
def home():
    return "Snowman Adventure Backend Running!"

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
        "provider_token": "", 
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
    
    # 1. Check if user can spin (Add cooldown logic here if needed)
    # For now, we assume free or handled by frontend cost visually, but logic is here.
    
    # 2. Determine Prize based on Weighted Probability
    # indices: 0, 1, 2, 3, 4, 5, 6, 7
    # prizes: [0.001, 0.0, 0.05, 0.0, 1.0, 0.0, 0.1, 0.0]
    
    chosen_index = random.choices(range(8), weights=SPIN_WEIGHTS, k=1)[0]
    prize_amount = SPIN_PRIZES[chosen_index]
    
    # 3. Update User Balance in Firebase
    ref = db.reference(f'users/{user_id}')
    user_data = ref.get() or {}
    
    current_ton = user_data.get('tonBalance', 0.0)
    # Ensure float conversion
    try:
        current_ton = float(current_ton)
    except:
        current_ton = 0.0
        
    new_ton = current_ton + prize_amount
    
    ref.update({
        'tonBalance': new_ton,
        'lastSpinTime': int(time.time() * 1000)
    })
    
    # Return index so frontend knows where to stop the wheel
    return jsonify({
        "ok": True,
        "index": chosen_index,
        "prize": prize_amount
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

        # ব্রডকাস্টের জন্য ইউজার সেভ করা
        save_bot_user(chat_id)

        # পেমেন্ট কনফার্মেশন
        if 'successful_payment' in msg:
            payload = msg['successful_payment']['invoice_payload']
            try:
                item_id, uid = payload.split('_', 1)
                if update_user_perks(uid, item_id):
                    send_telegram_message(chat_id, f"✅ Payment Successful! Your {item_id} rewards have been added.")
            except:
                pass
            return "OK", 200

        # --- ADMIN BROADCAST FEATURE ---
        # কমান্ড: /broadcast আপনার মেসেজ
        if text.startswith('/broadcast'):
            if str(user_id) == str(ADMIN_ID):
                broadcast_msg = text.replace('/broadcast', '').strip()
                if broadcast_msg:
                    users = get_all_users()
                    count = 0
                    send_telegram_message(chat_id, f"📡 Broadcasting to {len(users)} users...")
                    
                    for uid in users:
                        try:
                            # ব্রডকাস্ট মেসেজে কোনো বাটন থাকবে না, শুধু টেক্সট
                            send_telegram_message(uid, broadcast_msg)
                            count += 1
                            time.sleep(0.05) # Telegram Limit এড়ানোর জন্য ছোট ডিলে
                        except:
                            continue # কেউ ব্লক করলে স্কিপ করবে
                    
                    send_telegram_message(chat_id, f"✅ Broadcast sent to {count} users.")
                else:
                    send_telegram_message(chat_id, "⚠️ Please type a message. Ex: `/broadcast Hello All`")
            else:
                # এডমিন না হলে কিছু বলবে না অথবা ওয়েলকাম মেসেজ দেখাবে
                pass
            
            # ব্রডকাস্ট কমান্ড দিলে ওয়েলকাম মেসেজ দেখানোর দরকার নেই, তাই এখানে রিটার্ন
            if str(user_id) == str(ADMIN_ID):
                return "OK", 200

        # --- WELCOME MESSAGE & BUTTONS ---
        # ইউজার যা-ই টাইপ করুক, এই মেসেজ এবং বাটন যাবে
        welcome_text = (
            "☃️ **Welcome to Snowman Adventure!** ❄️\n\n"
            "Tap to play, earn coins, and upgrade your Snowman! "
            "Invite friends to earn huge rewards and compete in the leaderboard. 🏆\n\n"
            "👇 **Start your journey now!**"
        )

        keyboard = {
            "inline_keyboard": [
                # ১টি বড় বাটন (Launch Game)
                [{"text": "🚀 Launch ❄️", "web_app": {"url": GAME_URL}}],
                # ২টি ছোট বাটন (Update, Discuss)
                [
                    {"text": "Update", "url": CHANNEL_URL},
                    {"text": "Discuss", "url": GROUP_URL}
                ]
            ]
        }

        send_telegram_message(chat_id, welcome_text, keyboard)

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

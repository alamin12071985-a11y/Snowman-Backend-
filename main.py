# --- START OF FILE main.py ---

import os
import sys
import logging
import asyncio
import sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# Check Environment Variables
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)

if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE SETUP (SQLite) ---
# ইউজারদের আইডি সেভ করার জন্য, যাতে ব্রডকাস্ট পাঠানো যায়
DB_FILE = "snowman_users.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"DB Error: {e}")
    finally:
        conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- SHOP CONFIGURATION ---
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},
    'coin_small': {'price': 50, 'amount': 1},
    'coin_medium': {'price': 100, 'amount': 1},
    'coin_large': {'price': 250, 'amount': 1},
    'coin_mega': {'price': 500, 'amount': 1},
}

# --- BOT INITIALIZATION ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

# --- BUTTONS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [
            InlineKeyboardButton(text="❄️ Join Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discussion Group 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- TELEGRAM HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # ইউজার ডাটাবেসে সেভ করা হচ্ছে
    add_user(user_id)
    
    # ফরম্যাটেড মেসেজ (HTML Mode)
    text = f"""
<b>❄️☃️ Hey {first_name}, Welcome to Snowman Adventure! ☃️❄️</b>

Brrrr… the snow is falling and your journey starts <b>RIGHT NOW!</b> 🌨️✨

Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁

<b>Here’s what’s waiting for you 👇</b>

➡️ <b>Tap & Earn:</b> Collect coins instantly ❄️
➡️ <b>Daily Tasks:</b> Complete and win 🔑
➡️ <b>Lucky Spin:</b> Spin & win surprises 🎡
➡️ <b>Invite Friends:</b> Earn MORE rewards 💫
➡️ <b>Leaderboard:</b> Climb to the top 🏆

Every tap matters. Every coin counts.
And you are now part of the <b>Snowman family</b> 🤍☃️

So don’t wait…
👉 <b>Start tapping, start winning, and enjoy the adventure! 🎮❄️</b>
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@router.message(F.text)
async def echo_all(message: types.Message):
    first_name = message.from_user.first_name
    
    text = f"""
<b>❄️☃️ Hey {first_name}, Welcome Back! ☃️❄️</b>

Snowman heard you typing… and got excited! 😄💫
That means it’s time to jump back into the icy fun ❄️🎮

<b>What’s waiting for you right now 👇</b>

➡️ Tap the Snowman & earn coins 💰
➡️ Complete tasks for instant rewards 🎯
➡️ Spin and win surprises 🎡
➡️ Invite friends & grow faster 👥
➡️ Chase the top of the leaderboard 🏆

Every click brings progress.
Every moment brings rewards. 🌟

<b>Choose your next move below and keep the adventure going ⬇️</b>

❄️ <i>Stay cool. Keep tapping. Snowman Adventure never sleeps!</i> ☃️🔥
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- PAYMENT HANDLERS ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("❄️ <b>Payment Successful!</b> Your items have been added. Restart the game to see changes! ☃️", parse_mode="HTML")

# --- DAILY BROADCAST TASK (AUTOMATIC) ---
async def send_daily_broadcast():
    """এই ফাংশনটি অটোমেটিক প্রতিদিন রান হবে"""
    logging.info("⏳ Starting Daily Broadcast...")
    
    users = get_all_users()
    if not users:
        logging.info("No users found to broadcast.")
        return

    caption = """
<b>❄️🚨 HEY! Your Daily Rewards Are MELTING AWAY! 🚨❄️</b>

Snowman is waving at you right now ☃️👋
Today = <b>FREE rewards</b>, but only if you show up! 😱🎁

<b>🔥 Don’t skip this 👇</b>

➡️ 🎡 <b>Daily Spin is ACTIVE</b> — one spin can change your day!
➡️ 🎯 <b>Daily Tasks are OPEN</b> — quick actions, instant coins 💰
➡️ ⏳ Miss today = lose today’s rewards forever

Just 30 seconds can mean:
💰 More coins
🚀 Faster levels
🏆 Higher rank

The snow is falling… the prizes are waiting…
👉 <b>Open Snowman Adventure NOW and claim today’s wins! 🎮❄️</b>

<i>Tap smart. Spin daily. Stay ahead.</i> ☃️💫
    """
    
    # আপনার দেওয়া ইমেজ ফাইল আইডি (এটি ভুল হলে এরর আসতে পারে, তাই ট্রাই-এক্সেপ্ট ব্লক আছে)
    photo_file_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"
    
    count = 0
    for user_id in users:
        try:
            await bot.send_photo(chat_id=user_id, photo=photo_file_id, caption=caption, parse_mode="HTML", reply_markup=get_main_keyboard())
            count += 1
            await asyncio.sleep(0.05) # Telegram Limit এড়ানোর জন্য ছোট বিরতি
        except Exception as e:
            logging.error(f"Failed to send to {user_id}: {e}")
            
    logging.info(f"✅ Daily Broadcast sent to {count} users.")

# --- API ROUTES ---

async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if item_id not in SHOP_ITEMS:
            return web.json_response({"error": "Item not found"}, status=404)

        item = SHOP_ITEMS[item_id]
        
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        return web.json_response({"result": link})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast_manual(request):
    """ম্যানুয়ালি ব্রডকাস্ট ট্রিগার করার জন্য"""
    asyncio.create_task(send_daily_broadcast())
    return web.Response(text="🚀 Broadcast process started in background!")

async def home(request):
    return web.Response(text="⛄ Snowman Adventure Backend is Running Successfully! ❄️")

# --- WEBHOOK & STARTUP ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db() # ডাটাবেস তৈরি
    
    # অটোমেটিক শিডিউলার সেটআপ (প্রতিদিন সকাল ৮:০০ টায়)
    scheduler.add_job(send_daily_broadcast, 'cron', hour=8, minute=0)
    scheduler.start()
    
    logging.info(f"🔗 Webhook set to: {WEBHOOK_URL}")
    logging.info("⏰ Daily Broadcast Scheduler Started (08:00 AM)")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    scheduler.shutdown()
    logging.info("🔌 Bot Shutdown")

# --- MAIN EXECUTION ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast_manual) # ম্যানুয়াল কলের জন্য
    app.router.add_get('/', home)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

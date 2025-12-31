import os
import sys
import logging
import asyncio
import sqlite3
import html  # HTML নাম ফিক্স করার জন্য
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- LOGGING SETUP (বিস্তারিত এরর দেখার জন্য) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

if not BOT_TOKEN:
    logging.error("❌ CRITICAL: BOT_TOKEN is missing!")
    sys.exit(1)

if not APP_URL:
    logging.error("❌ CRITICAL: APP_URL is missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE SETUP (Safe Mode) ---
DB_FILE = "snowman_users.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
        conn.commit()
        conn.close()
        logging.info("✅ Database initialized successfully.")
    except Exception as e:
        logging.error(f"❌ Database Init Error: {e}")

def add_user(user_id):
    """সেফলি ইউজার এড করার ফাংশন"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"⚠️ Failed to add user to DB: {e}")

def get_all_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logging.error(f"⚠️ Failed to fetch users: {e}")
        return []

# --- SHOP ITEMS ---
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},
    'coin_small': {'price': 50, 'amount': 1},
    'coin_medium': {'price': 100, 'amount': 1},
    'coin_large': {'price': 250, 'amount': 1},
    'coin_mega': {'price': 500, 'amount': 1},
}

# --- BOT INIT ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

# --- KEYBOARD ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [
            InlineKeyboardButton(text="❄️ Join Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discussion Group 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    try:
        user_id = message.from_user.id
        # নাম Escape করা হচ্ছে যাতে HTML এরর না হয়
        first_name = html.escape(message.from_user.first_name)
        
        # ডাটাবেসে সেভ
        add_user(user_id)
        
        text = f"""
❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️

Brrrr… the snow is falling and your journey starts <b>RIGHT NOW!</b> 🌨️✨

<b>Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁</b>

<blockquote>👉 <b>Tap & Earn:</b> Collect coins instantly ❄️
👉 <b>Daily Tasks:</b> Complete and win 🔑
👉 <b>Lucky Spin:</b> Spin & win surprises 🎡
👉 <b>Invite Friends:</b> Earn MORE rewards 💫
👉 <b>Leaderboard:</b> Climb to the top 🏆</blockquote>

Every tap matters. Every coin counts.
And you are now part of the <b>Snowman family</b> 🤍☃️

👇 <b>Start Your Journey Below</b> 👇
        """
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
        logging.info(f"✅ Sent WELCOME message to {user_id}")

    except Exception as e:
        logging.error(f"❌ Error in /start command: {e}")

@router.message(F.text)
async def echo_all(message: types.Message):
    try:
        user_id = message.from_user.id
        first_name = html.escape(message.from_user.first_name)
        
        logging.info(f"📩 Received text from {user_id}: {message.text}")

        text = f"""
❄️☃️ <b>Hey {first_name}, Welcome Back!</b> ☃️❄️

Snowman heard you typing… and got excited! 😄💫
That means it’s time to jump back into the icy fun ❄️🎮

<b>Here is your current status update:</b>

<blockquote>➡️ <b>Tap the Snowman:</b> Earn coins 💰
➡️ <b>Complete Tasks:</b> Get instant rewards 🎯
➡️ <b>Spin the Wheel:</b> Win surprises 🎡
➡️ <b>Invite Friends:</b> Grow faster 👥
➡️ <b>Rank Up:</b> Chase the top spot 🏆</blockquote>

Every click brings progress.
Every moment brings rewards. 🌟

<b>Choose your next move below and keep the adventure going ⬇️</b>

❄️ <i>Stay cool. Keep tapping. Snowman Adventure never sleeps!</i> ☃️🔥
        """
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
        logging.info(f"✅ Sent REPLY message to {user_id}")

    except Exception as e:
        logging.error(f"❌ Error in echo_all handler: {e}")

# --- PAYMENT ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    try:
        await message.answer(
            "<blockquote>❄️ <b>Payment Successful!</b>\nYour items have been added. Restart the game to see changes! ☃️</blockquote>", 
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Payment Msg Error: {e}")

# --- BROADCAST ---
async def send_daily_broadcast():
    logging.info("⏳ Starting Daily Broadcast...")
    users = get_all_users()
    
    if not users:
        logging.info("⚠️ No users found for broadcast.")
        return

    caption = """
❄️🚨 <b>HEY! Your Daily Rewards Are MELTING AWAY!</b> 🚨❄️

Snowman is waving at you right now ☃️👋
Today = <b>FREE rewards</b>, but only if you show up! 😱🎁

<blockquote>➡️ 🎡 <b>Daily Spin is ACTIVE:</b>
One spin can change your day!

➡️ 🎯 <b>Daily Tasks are OPEN:</b>
Quick actions, instant coins 💰

➡️ ⏳ <b>Warning:</b>
Miss today = lose today’s rewards forever</blockquote>

Just 30 seconds can mean:
💰 More coins | 🚀 Faster levels | 🏆 Higher rank

The snow is falling… the prizes are waiting…
👉 <b>Open Snowman Adventure NOW and claim today’s wins! 🎮❄️</b>
    """
    
    photo_file_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"
    
    success_count = 0
    for user_id in users:
        try:
            await bot.send_photo(
                chat_id=user_id, 
                photo=photo_file_id, 
                caption=caption, 
                parse_mode="HTML", 
                reply_markup=get_main_keyboard()
            )
            success_count += 1
            await asyncio.sleep(0.05) 
        except Exception as e:
            logging.error(f"❌ Failed to send to {user_id}: {e}")
            
    logging.info(f"✅ Broadcast finished. Sent to {success_count} users.")

# --- SERVER ROUTES ---
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
        logging.error(f"Invoice API Error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast_manual(request):
    asyncio.create_task(send_daily_broadcast())
    return web.Response(text="🚀 Broadcast started manually!")

async def home(request):
    return web.Response(text="⛄ Snowman Bot is Running! ❄️")

# --- LIFECYCLE ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
    # Schedule: Every day at 08:00 AM
    scheduler.add_job(send_daily_broadcast, 'cron', hour=8, minute=0)
    scheduler.start()
    logging.info(f"✅ Webhook set: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    scheduler.shutdown()
    logging.info("🛑 Bot Stopped")

# --- MAIN ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast_manual)
    app.router.add_get('/', home)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

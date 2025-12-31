import os
import sys
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- CONFIGURATION (ENV VARS) ---
# Render Environment থেকে ডাটা নিবে
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL") 

# ভেরিয়েবল ঠিকমতো সেট না থাকলে কোড রান হবে না এবং লগে এরর দেখাবে
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing in Render Settings!")
    sys.exit(1)

if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing in Render Settings!")
    sys.exit(1)

# Webhook পাথ কনফিগারেশন
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- SHOP CONFIGURATION ---
# 1 Telegram Star = Approx 1-2 Taka value logic
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},  # 10 Stars
    'coin_small': {'price': 50, 'amount': 1},
    'coin_medium': {'price': 100, 'amount': 1},
    'coin_large': {'price': 250, 'amount': 1},
    'coin_mega': {'price': 500, 'amount': 1},
    'booster_3d': {'price': 20, 'amount': 1},
    'booster_15d': {'price': 70, 'amount': 1},
    'booster_30d': {'price': 120, 'amount': 1},
    'autotap_1d': {'price': 20, 'amount': 1},
    'autotap_7d': {'price': 80, 'amount': 1},
    'autotap_30d': {'price': 200, 'amount': 1},
}

# --- BOT INITIALIZATION ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- BUTTONS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️Start App☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [
            InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discuss 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- TELEGRAM HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ Hey {first_name}, Welcome to Snowman Adventure! ☃️❄️
Brrrr… the snow is falling and your journey starts RIGHT NOW! 🌨️✨
Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁
Here’s what’s waiting for you 👇
➡️ Tap & earn coins ❄️
➡️ Complete daily tasks 🔑
➡️ Spin & win surprises 🎡
➡️ Invite friends and earn MORE 💫
➡️ Climb the leaderboard 🏆
Every tap matters.
Every coin counts.
And you are now part of the Snowman family 🤍☃️
So don’t wait…
👉 Start tapping, start winning, and enjoy the adventure! 🎮❄️
    """
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(F.text)
async def echo_all(message: types.Message):
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ Hey {first_name}, Welcome Back to Snowman Adventure! ☃️❄️
Snowman heard you typing… and got excited! 😄💫
That means it’s time to jump back into the icy fun ❄️🎮
What’s waiting for you right now 👇
➡️ Tap the Snowman & earn coins 💰
➡️ Complete tasks for instant rewards 🎯
➡️ Spin and win surprises 🎡
➡️ Invite friends & grow faster 👥
➡️ Chase the top of the leaderboard 🏆
Every click brings progress.
Every moment brings rewards. 🌟
Choose your next move below and keep the adventure going ⬇️

❄️ Stay cool. Keep tapping.
Snowman Adventure never sleeps! ☃️🔥
    """
    await message.answer(text, reply_markup=get_main_keyboard())

# --- PAYMENT HANDLERS ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("❄️ Payment Successful! Your items have been added. Restart the game to see changes! ☃️")

# --- WEBHOOK TRIGGERS ---
async def on_startup(bot: Bot):
    logging.info(f"🔗 Setting webhook to: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    logging.info("🔌 Deleting webhook...")
    await bot.delete_webhook()

# --- API ROUTES (SHOP & BROADCAST) ---

async def create_invoice_api(request):
    """ফ্রন্টএন্ড থেকে পেমেন্ট রিকোয়েস্ট হ্যান্ডেল করে"""
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if item_id not in SHOP_ITEMS:
            return web.json_response({"error": "Item not found"}, status=404)

        item = SHOP_ITEMS[item_id]
        
        # Telegram Stars Invoice (XTR currency)
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Stars এর জন্য এটি ফাঁকা থাকে
            currency="XTR",
            prices=prices,
        )
        return web.json_response({"result": link})
    except Exception as e:
        logging.error(f"Invoice Error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast(request):
    """ডেইলি ব্রডকাস্ট পাঠানোর ফাংশন (Cron Job এর জন্য)"""
    
    # টেস্ট করার জন্য URL এর সাথে ?chat_id=12345 দিয়ে কল করা যাবে
    # প্রোডাকশনে আপনি ডাটাবেস থেকে সব ইউজার আইডি লুপ করবেন
    chat_id = request.rel_url.query.get('chat_id')
    
    caption = """
❄️🚨 HEY! Your Daily Rewards Are MELTING AWAY! 🚨❄️
Snowman is waving at you right now ☃️👋
Today = FREE rewards, but only if you show up! 😱🎁
🔥 Don’t skip this 👇
➡️ 🎡 Daily Spin is ACTIVE — one spin can change your day!
➡️ 🎯 Daily Tasks are OPEN — quick actions, instant coins 💰
➡️ ⏳ Miss today = lose today’s rewards forever
Just 30 seconds can mean:
💰 More coins
🚀 Faster levels
🏆 Higher rank
The snow is falling… the prizes are waiting…
👉 Open Snowman Adventure NOW and claim today’s wins! 🎮❄️
Tap smart. Spin daily. Stay ahead. ☃️💫
    """
    
    photo_file_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"

    try:
        if chat_id:
            await bot.send_photo(chat_id=chat_id, photo=photo_file_id, caption=caption, reply_markup=get_main_keyboard())
            return web.Response(text=f"Broadcast sent to {chat_id}")
        else:
            return web.Response(text="Broadcast endpoint active. Provide ?chat_id=... to test.")
    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)

async def home(request):
    return web.Response(text="⛄ Snowman Adventure Backend is Running Successfully! ❄️")

# --- MAIN APP EXECUTION ---
def main():
    # Register Startup/Shutdown for Webhook
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Setup Web App
    app = web.Application()
    
    # Routes
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast)
    app.router.add_get('/', home)

    # Setup Aiogram Webhook Handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Integrate Bot with Web App
    setup_application(app, dp, bot=bot)

    # Run App
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

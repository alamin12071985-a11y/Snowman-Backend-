import os
import sys
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiohttp import web

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- ENVIRONMENT CHECK ---
# Render থেকে ভেরিয়েবলগুলো ঠিকমতো লোড হচ্ছে কিনা চেক করা
BOT_TOKEN = os.getenv("8336857025:AAHU9LtgSGy5oifVfMk2Le92vkpk94pq6k8")
if not BOT_TOKEN:
    logging.error("CRITICAL ERROR: 'BOT_TOKEN' is missing in Environment Variables!")
    sys.exit(1) # কোড বন্ধ করে দিবে যাতে আপনি লগে এরর দেখেন

GAME_URL = os.getenv("GAME_URL", "https://alamin12071985-a11y.github.io/Snowman-Adventure/")
PORT = int(os.getenv("PORT", 10000)) # Render default port usually 10000

# --- SHOP CONFIG ---
SHOP_ITEMS = {
    'coin_starter': {'price': 1, 'amount': 100},
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

# --- BOT SETUP ---
try:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)
except Exception as e:
    logging.error(f"Failed to initialize Bot: {e}")
    sys.exit(1)

# --- KEYBOARDS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️Start App☃️", url="https://t.me/snowmanadventurebot/startapp")],
        [
            InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discuss 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- HANDLERS ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ Hey {first_name}, Welcome to Snowman Adventure! ☃️❄️
Tap the Snowman, earn shiny coins 💰 and unlock cool rewards 🎁
👉 Start tapping, start winning! 🎮❄️
    """
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(F.text)
async def echo_all(message: types.Message):
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ Hey {first_name}, Welcome Back! ☃️❄️
Snowman never sleeps! Keep tapping! ☃️🔥
    """
    await message.answer(text, reply_markup=get_main_keyboard())

@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("❄️ Payment Successful! Restart the game! ☃️")

# --- WEB SERVER ---
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
        logging.error(f"Invoice Error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast(request):
    caption = "❄️🚨 HEY! Your Daily Rewards Are MELTING AWAY! 🚨❄️\nCheck the app now!"
    photo_file_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"
    # Note: In production, use your DB to get chat_ids
    return web.Response(text="Broadcast logic loaded.")

async def home(request):
    return web.Response(text="Snowman Backend is Running!")

# --- MAIN APP LOOP ---
async def main():
    # 1. Setup Web App
    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast)
    app.router.add_get('/', home)

    # 2. Setup Runner
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    
    logging.info(f"Starting Web Server on port {PORT}...")
    await site.start()

    # 3. Start Bot Polling in Background
    logging.info("Starting Bot Polling...")
    # asyncio.create_task ব্যবহার করে পোলিং ব্যাকগ্রাউন্ডে চালানো হচ্ছে
    polling_task = asyncio.create_task(dp.start_polling(bot))

    # 4. Keep Alive
    try:
        # সার্ভার যাতে বন্ধ না হয় তার জন্য অপেক্ষা করা
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logging.info("Stopping...")
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.critical(f"Unhandled Exception: {e}")
        sys.exit(1)

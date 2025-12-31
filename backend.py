import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

# --- CONFIGURATION ---
# Render Environment Variables থেকে এগুলো পাবে
BOT_TOKEN = os.getenv("8336857025:AAHU9LtgSGy5oifVfMk2Le92vkpk94pq6k8") 
# আপনার ফ্রন্টএন্ড গেমের URL (যেখানে index.html হোস্ট করা আছে)
GAME_URL = os.getenv("GAME_URL", "https://alamin12071985-a11y.github.io/Snowman-Adventure/") 
# পেমেন্ট প্রোভাইডার টোকেন (Stars এর জন্য সাধারণত খালি থাকে যদি ডিজিটাল গুডস হয়, অথবা BotFather থেকে নিতে হয়)
# Telegram Stars এর জন্য এটি লাইভ পেমেন্ট।

# Shop Items (Frontend এর সাথে মিল রেখে)
SHOP_ITEMS = {
    'coin_starter': {'price': 1, 'amount': 100},   # 1 Star = 100 Taka value logic (Adjust as needed)
    'coin_small': {'price': 50, 'amount': 1},      # Example: 50 Stars
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

# --- SETUP ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- KEYBOARDS ---
def get_main_keyboard():
    # Button Layout: 1 Big, 2 Small
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

# Echo Handler for any text
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

# --- PAYMENT HANDLERS (TELEGRAM STARS) ---

@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    # পেমেন্ট সফল হলে এখানে ডাটাবেস আপডেট লজিক বসাতে পারেন (Firebase Admin SDK দিয়ে)
    # অথবা ফ্রন্টএন্ড চেক করে নিবে।
    await message.answer("❄️ Payment Successful! Your items have been added. Restart the game to see changes! ☃️")

# --- WEB SERVER (API FOR FRONTEND) ---

async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id') # Telegram User ID needed

        if item_id not in SHOP_ITEMS:
            return web.json_response({"error": "Item not found"}, status=404)

        item = SHOP_ITEMS[item_id]
        
        # Telegram Stars Invoice Link
        # Currency must be XTR for Stars
        prices = [LabeledPrice(label=item_id, amount=item['price'])] # Amount is 1 = 1 Star
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Stars এর জন্য ফাঁকা থাকে
            currency="XTR",
            prices=prices,
        )
        
        return web.json_response({"result": link})
    except Exception as e:
        logging.error(f"Error creating invoice: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast(request):
    """
    এই এন্ডপয়েন্টটি প্রতিদিন একবার কল করতে হবে (Cron Job ব্যবহার করে)।
    """
    # নোট: এখানে সব ইউজারের লুপ চালানো উচিত। কিন্তু সিম্পলিসিটির জন্য
    # আপনি আপনার ডাটাবেস থেকে সব ইউজার আইডি নিয়ে লুপ করবেন।
    # এখানে ডেমো হিসেবে আমরা কোড স্ট্রাকচার দিচ্ছি।
    
    # demo: request এ 'chat_id' পাঠালে টেস্ট করা যাবে
    params = request.rel_url.query
    chat_id = params.get('chat_id') # Testing purpose
    
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
            return web.Response(text="No chat_id provided for test. In production, loop through DB users.")
    except Exception as e:
        return web.Response(text=f"Failed: {str(e)}")

async def home(request):
    return web.Response(text="Snowman Adventure Backend is Running! ☃️")

# --- APP RUNNER ---

async def main():
    # Web App Setup
    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast) # Cron Job hits this
    app.router.add_get('/', home)

    # Setup Webhook or Polling (Using Polling for simplicity on Render worker, 
    # but strictly Webhook is better. Here we run Bot + Web Server same loop)
    
    # Run Bot in background
    asyncio.create_task(dp.start_polling(bot))
    
    # Run Web Server
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

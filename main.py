import os
import sys
import logging
import asyncio
import json
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# --- ADMIN CONFIGURATION ---
ADMIN_ID = 7605281774  # <--- আপনার টেলিগ্রাম আইডি
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# --- VALIDATION ---
if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN or APP_URL is missing!")
    sys.exit(1)

APP_URL = APP_URL.rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (Users Management) ---
DB_FILE = "users.json"

def load_users():
    """ফাইল থেকে ইউজার লিস্ট লোড করা"""
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r") as f:
            content = f.read().strip()
            if not content: return set()
            return set(json.loads(content))
    except Exception:
        return set()

async def save_user_async(user_id):
    """বটকে স্লো না করে ইউজার সেভ করা (Async)"""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _save_user_sync, user_id)
    except Exception as e:
        logging.error(f"Save Error: {e}")

def _save_user_sync(user_id):
    """সিঙ্ক সেভ ফাংশন"""
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                json.dump(list(users), f)
            logging.info(f"🆕 New User Saved: {user_id}")
    except Exception:
        pass

# --- SHOP ITEMS ---
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},
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

# --- FSM STATES ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# --- KEYBOARDS ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Play Game ☃️", url=f"https://t.me/snowmanadventurebot/app")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ])

def get_broadcast_menu(data):
    # স্ট্যাটাস চেক করা হচ্ছে
    has_media = "✅ Set" if data.get('media_id') else "❌ Empty"
    has_text = "✅ Set" if data.get('text') else "❌ Empty"
    has_btn = "✅ Set" if data.get('buttons') else "❌ Empty"

    kb = [
        [
            InlineKeyboardButton(text=f"🖼️ Media ({has_media})", callback_data="br_media"),
            InlineKeyboardButton(text=f"📝 Text ({has_text})", callback_data="br_text")
        ],
        [
            InlineKeyboardButton(text=f"🔘 Buttons ({has_btn})", callback_data="br_buttons")
        ],
        [InlineKeyboardButton(text="👀 Preview Message", callback_data="br_preview")],
        [
            InlineKeyboardButton(text="🗑 Cancel", callback_data="br_cancel"),
            InlineKeyboardButton(text="🚀 SEND NOW", callback_data="br_send")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def parse_buttons(button_text):
    if not button_text: return None
    try:
        kb = []
        lines = button_text.split('\n')
        for line in lines:
            parts = line.split('-')
            if len(parts) >= 2:
                text = parts[0].strip()
                url = parts[1].strip()
                if url.startswith('@'): url = f"https://t.me/{url[1:]}"
                elif not url.startswith('http'): url = f"https://{url}"
                kb.append([InlineKeyboardButton(text=text, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except: return None

# --- TELEGRAM HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await save_user_async(message.from_user.id)
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️

Brrrr… the snow is falling and your journey starts <b>RIGHT NOW!</b> 🌨️✨

Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁

<b>Here’s what’s waiting for you:</b>
➡️ Tap & earn coins ❄️
➡️ Complete daily tasks 🔑
➡️ Spin & win surprises 🎡
➡️ Invite friends and earn MORE 💫

So don’t wait…
👉 Start tapping, start winning! 🎮❄️
    """
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message):
    # কেউ মেসেজ দিলে আবার ওয়েলকাম মেসেজ দিবে
    await cmd_start(message)

# --- BROADCAST SYSTEM (FIXED) ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("📢 **Broadcast Menu**\n\nSelect an option below to setup:", reply_markup=get_broadcast_menu({}))
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼️ **Send the Photo now:**\n(Or send text to cancel)")
    await state.set_state(BroadcastState.waiting_for_media)

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def input_media(message: types.Message, state: FSMContext):
    # ছবি পাওয়ার পর ডাটা সেভ করে আবার মেনু দেওয়া হবে
    await state.update_data(media_id=message.photo[-1].file_id)
    data = await state.get_data()
    await message.answer("✅ **Image Saved!**\nWhat to do next?", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 **Send the Message Text now:**")
    await state.set_state(BroadcastState.waiting_for_text)

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def input_text(message: types.Message, state: FSMContext):
    # টেক্সট পাওয়ার পর ডাটা সেভ করে আবার মেনু দেওয়া হবে
    await state.update_data(text=message.text)
    data = await state.get_data()
    await message.answer("✅ **Text Saved!**\nWhat to do next?", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    msg = "🔘 **Send Buttons in this format:**\n\n`Button Name - URL`\n\nExample:\n`Play Game - https://t.me/bot`"
    await call.message.edit_text(msg, parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_buttons)

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def input_buttons(message: types.Message, state: FSMContext):
    if not parse_buttons(message.text):
        await message.answer("❌ Invalid Format. Try again: `Name - URL`")
        return
    await state.update_data(buttons=message.text)
    data = await state.get_data()
    await message.answer("✅ **Buttons Saved!**\nReady to send?", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    markup = parse_buttons(data.get('buttons'))
    try:
        if data.get('media_id'):
            await call.message.answer_photo(data['media_id'], caption=data.get('text'), reply_markup=markup)
        else:
            await call.message.answer(data.get('text') or "Empty", reply_markup=markup)
        await call.message.answer("☝️ **This is the Preview.**", reply_markup=get_broadcast_menu(data))
    except Exception as e:
        await call.answer(f"Error: {e}", show_alert=True)

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState.menu))
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast Cancelled.")

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('text') and not data.get('media_id'):
        await call.answer("❌ Can't send empty message!", show_alert=True)
        return

    await call.message.edit_text("🚀 **Sending Broadcast...**\n(This might take a while)")
    
    # লোডিং ইউজারস
    users = load_users()
    markup = parse_buttons(data.get('buttons'))
    sent = 0
    blocked = 0
    
    for user_id in users:
        try:
            if data.get('media_id'):
                await bot.send_photo(chat_id=user_id, photo=data['media_id'], caption=data.get('text'), reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=data.get('text'), reply_markup=markup)
            sent += 1
            await asyncio.sleep(0.05) # Rate limit protection
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            pass
            
    await call.message.answer(f"✅ **Broadcast Completed!**\n\n📩 Sent: {sent}\n🚫 Blocked: {blocked}")
    await state.clear()

# --- PAYMENT & API HANDLERS ---
@router.pre_checkout_query()
async def on_pre_checkout(q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(m: types.Message):
    await m.answer("✅ Payment Received! Item added to inventory.")

def cors_response(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})
async def options_handler(r):
    return web.Response(status=200, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS"})

async def create_invoice_api(request):
    try:
        data = await request.json()
        item = SHOP_ITEMS.get(data.get('item_id'))
        if not item: return cors_response({"error": "Item not found"}, 404)
        link = await bot.create_invoice_link(
            title="Shop Purchase", description=data.get('item_id'), payload=f"{data.get('user_id')}_{data.get('item_id')}",
            provider_token="", currency="XTR", prices=[LabeledPrice(label=data.get('item_id'), amount=item['price'])]
        )
        return cors_response({"result": link})
    except Exception as e: return cors_response({"error": str(e)}, 500)

async def verify_join_api(request):
    try:
        uid = int((await request.json()).get('user_id'))
        async def chk(cid):
            try: return (await bot.get_chat_member(cid, uid)).status in ['member', 'administrator', 'creator', 'restricted']
            except: return False
        c, g = await asyncio.gather(chk(CHANNEL_USERNAME), chk(GROUP_USERNAME))
        return cors_response({"joined": c and g})
    except: return cors_response({"joined": False})

async def home(request):
    return web.Response(text="⛄ Bot is Active and Running!", status=200)

# --- KEEP ALIVE & STARTUP (Render Fix) ---

async def keep_alive_task():
    """Render কে জাগিয়ে রাখার জন্য প্রতি ২ মিনিট পর পর পিং করবে"""
    await asyncio.sleep(5)
    url = f"{APP_URL}/"
    logging.info(f"🔄 Keep-Alive Started for: {url}")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # নিজের সার্ভারেই রিকোয়েস্ট পাঠানো হচ্ছে
                async with session.get(url) as resp:
                    pass 
            except: pass
            await asyncio.sleep(120) # 2 মিনিট

async def set_webhook_background():
    """ব্যাকগ্রাউন্ডে ওয়েব হুক সেট করা"""
    await asyncio.sleep(1)
    try:
        # drop_pending_updates=False মানে অফলাইন মেসেজও আসবে
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=False, allowed_updates=["message", "callback_query", "pre_checkout_query"])
        logging.info("✅ Webhook Set Successfully!")
    except Exception as e:
        logging.error(f"❌ Webhook Error: {e}")

async def on_startup(app):
    asyncio.create_task(set_webhook_background())
    asyncio.create_task(keep_alive_task())

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

# --- MAIN EXECUTION ---
def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    app.router.add_get('/', home)
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)
    
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)

    logging.info(f"🚀 Server starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()

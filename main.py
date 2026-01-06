import os
import sys
import logging
import asyncio
import json
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

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# --- ADMIN CONFIGURATION ---
# আপনার নিজের টেলিগ্রাম আইডি এখানে দিন (Broadcast এর জন্য)
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# --- VALIDATION ---
if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN or APP_URL is missing!")
    sys.exit(1)

# URL Cleaning
APP_URL = APP_URL.rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (Safe JSON Handling) ---
DB_FILE = "users.json"

def load_users():
    """Loads users from JSON file safely."""
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
    """Saves user asynchronously to prevent blocking the bot."""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _save_user_sync, user_id)
    except Exception as e:
        logging.error(f"❌ Error saving user async: {e}")

def _save_user_sync(user_id):
    """Internal sync function for file writing."""
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                json.dump(list(users), f)
            logging.info(f"🆕 New user saved: {user_id}")
    except Exception as e:
        logging.error(f"❌ DB Write Error: {e}")

# --- SHOP ITEMS (Stars XTR) ---
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

# --- FSM STATES (For Broadcast) ---
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
    kb = [
        [InlineKeyboardButton(text="❄️ Play Game ☃️", url=f"https://t.me/snowmanadventurebot/app")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_menu(data):
    has_media = "✅ Set" if data.get('media_id') else "❌ Empty"
    has_text = "✅ Set" if data.get('text') else "❌ Empty"
    has_btn = "✅ Set" if data.get('buttons') else "❌ Empty"

    kb = [
        [
            InlineKeyboardButton(text=f"🖼️ Media", callback_data="br_media"),
            InlineKeyboardButton(text=f"👀 {has_media}", callback_data="br_dummy_media")
        ],
        [
            InlineKeyboardButton(text=f"📝 Text", callback_data="br_text"),
            InlineKeyboardButton(text=f"👀 {has_text}", callback_data="br_dummy_text")
        ],
        [
            InlineKeyboardButton(text=f"🔘 Buttons", callback_data="br_buttons"),
            InlineKeyboardButton(text=f"👀 {has_btn}", callback_data="br_dummy_btn")
        ],
        [InlineKeyboardButton(text="👀 Full Preview", callback_data="br_preview")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="br_cancel"),
            InlineKeyboardButton(text="Next ➡️", callback_data="br_send")
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
                if url.startswith('@'):
                    url = f"https://t.me/{url[1:]}"
                elif not url.startswith('http'):
                    url = f"https://{url}"
                kb.append([InlineKeyboardButton(text=text, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except:
        return None

# --- TELEGRAM HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Async save to avoid blocking
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
    """Auto-reply with the start menu."""
    await cmd_start(message)

# --- BROADCAST SYSTEM ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("📢 **Broadcast Menu**", reply_markup=get_broadcast_menu({}), parse_mode="Markdown")
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼️ **Send photo**", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_media)

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 **Send text**", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_text)

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔘 **Send buttons:** `Text-URL`\nExample: `Play-https://t.me/bot`", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_buttons)

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState.menu))
async def cb_cancel_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast cancelled.")

@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    btn = parse_buttons(data.get('buttons'))
    try:
        if data.get('media_id'):
            await call.message.answer_photo(photo=data['media_id'], caption=data.get('text'), reply_markup=btn)
        else:
            await call.message.answer(text=data.get('text') or "No text set", reply_markup=btn)
        await call.message.answer("☝️ Preview.", reply_markup=get_broadcast_menu(data))
    except Exception as e:
        await call.answer(f"Error: {str(e)}", show_alert=True)

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('text') and not data.get('media_id'):
        await call.answer("❌ Set Text or Media!", show_alert=True)
        return

    await call.message.edit_text("⏳ Sending broadcast...")
    markup = parse_buttons(data.get('buttons'))
    users = load_users()
    count = 0
    blocked = 0
    
    for user_id in users:
        try:
            if data.get('media_id'):
                await bot.send_photo(chat_id=user_id, photo=data['media_id'], caption=data.get('text'), reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=data.get('text'), reply_markup=markup)
            count += 1
            await asyncio.sleep(0.04) # Prevent flooding limits
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            pass
    
    await call.message.answer(f"✅ Broadcast Done!\n👥 Sent: {count}\n🚫 Blocked: {blocked}")
    await state.clear()

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def input_media(m: types.Message, state: FSMContext):
    await state.update_data(media_id=m.photo[-1].file_id)
    await m.answer("✅ Image Set", reply_markup=get_broadcast_menu(await state.get_data()))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def input_text(m: types.Message, state: FSMContext):
    await state.update_data(text=m.text)
    await m.answer("✅ Text Set", reply_markup=get_broadcast_menu(await state.get_data()))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def input_buttons(m: types.Message, state: FSMContext):
    if not parse_buttons(m.text):
        await m.answer("❌ Invalid format")
        return
    await state.update_data(buttons=m.text)
    await m.answer("✅ Buttons Set", reply_markup=get_broadcast_menu(await state.get_data()))
    await state.set_state(BroadcastState.menu)

# --- PAYMENT HANDLERS ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("✅ Payment Successful! Item added.")

# --- API HELPERS (CORS) ---
def cors_response(data, status=200):
    return web.json_response(
        data,
        status=status,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

async def options_handler(request):
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# --- API ENDPOINTS ---

async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing params"}, status=400)

        item = SHOP_ITEMS.get(item_id)
        if not item:
            return cors_response({"error": "Item not found"}, status=404)

        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Stars
            currency="XTR",
            prices=[LabeledPrice(label=item_id, amount=item['price'])],
        )
        return cors_response({"result": link})
    except Exception as e:
        return cors_response({"error": str(e)}, status=500)

async def verify_join_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        if not user_id: return cors_response({"joined": False}, status=400)
        
        try: user_id = int(user_id)
        except: return cors_response({"joined": False})

        valid = ['member', 'administrator', 'creator', 'restricted']

        async def check(cid):
            try:
                m = await bot.get_chat_member(cid, user_id)
                return m.status in valid
            except: return False

        in_channel, in_group = await asyncio.gather(check(CHANNEL_USERNAME), check(GROUP_USERNAME))
        return cors_response({"joined": in_channel and in_group})
    except Exception as e:
        return cors_response({"error": str(e)}, status=500)

async def home(request):
    """Health check for Render."""
    return web.Response(text="⛄ Snowman Bot is Running!", status=200)

# --- LIFECYCLE (WEBHOOK FIX) ---

async def set_webhook_background():
    """Sets webhook in background so Render doesn't timeout."""
    await asyncio.sleep(1) # Wait for server to start
    logging.info(f"🔗 Setting webhook to: {WEBHOOK_URL}")
    try:
        # drop_pending_updates=False is KEY to receiving offline messages
        await bot.set_webhook(
            WEBHOOK_URL,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
        logging.info("✅ Webhook Set Successfully!")
    except Exception as e:
        logging.error(f"❌ Webhook Failed: {e}")

async def on_startup(app):
    # This runs the webhook setup in the background
    asyncio.create_task(set_webhook_background())

async def on_shutdown(app):
    logging.info("🔌 Shutting down...")
    await bot.delete_webhook()
    await bot.session.close()

# --- APP EXECUTION ---
def main():
    app = web.Application()
    
    # 1. Register Handlers
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # 2. Add Routes
    app.router.add_get('/', home)
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)

    # 3. Add Webhook Handler (POST)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    app.router.add_post(WEBHOOK_PATH, webhook_requests_handler)

    # 4. Run App
    logging.info(f"🚀 Starting Server on Port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()

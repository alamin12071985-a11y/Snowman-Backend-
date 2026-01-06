import os
import sys
import logging
import asyncio
import json
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, TokenBasedRequestHandler
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
# .env ফাইল অথবা Environment Variables থেকে এগুলো লোড হবে
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# --- ADMIN CONFIGURATION ---
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# --- VALIDATION ---
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)
if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing!")
    sys.exit(1)

# URL Cleaning
APP_URL = APP_URL.rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (Simple JSON) ---
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
    except (json.JSONDecodeError, Exception) as e:
        logging.warning(f"⚠️ Database error: {e}. Starting fresh.")
        return set()

def save_user(user_id):
    """Saves a user ID to the JSON file."""
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                json.dump(list(users), f)
            logging.info(f"🆕 New user saved: {user_id}")
    except Exception as e:
        logging.error(f"❌ Error saving user: {e}")

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

# --- FSM STATES ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# --- BOT SETUP ---
# গ্লোবাল ভেরিয়েবল হিসেবে বট এবং ডিসপ্যাচার ডিক্লেয়ার করা হলো
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
    try:
        user_id = message.from_user.id
        save_user(user_id)
        
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
    except Exception as e:
        logging.error(f"Error in start command: {e}")

@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message):
    await cmd_start(message)

# --- BROADCAST HANDLERS ---
@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.update_data(media_id=None, text=None, buttons=None)
    await message.answer("📢 **Broadcast Menu**", reply_markup=get_broadcast_menu({}), parse_mode="Markdown")
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼️ **Send photo** (or send text to cancel)", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_media)

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 **Send caption/text**", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_text)

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    msg = "🔘 **Send buttons format:**\n`Text-URL`\n\nExample:\n`Play-https://t.me/bot`"
    await call.message.edit_text(msg, parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_buttons)

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState.menu))
async def cb_cancel_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast setup cancelled.")

@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text') or "No text set."
    btn_markup = parse_buttons(data.get('buttons'))
    try:
        if media_id:
            await call.message.answer_photo(photo=media_id, caption=text, reply_markup=btn_markup)
        else:
            await call.message.answer(text=text, reply_markup=btn_markup)
        await call.message.answer("☝️ Preview. Edit or Send.", reply_markup=get_broadcast_menu(data))
    except Exception as e:
        await call.answer(f"Error: {str(e)}", show_alert=True)

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text')
    buttons_raw = data.get('buttons')
    
    if not text and not media_id:
        await call.answer("❌ Set Text or Media first!", show_alert=True)
        return

    await call.message.edit_text("⏳ Sending broadcast... This may take time.")
    markup = parse_buttons(buttons_raw)
    current_users = load_users()
    count = 0
    blocked = 0
    
    for user_id in current_users:
        try:
            if media_id:
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
            count += 1
            await asyncio.sleep(0.04) 
        except TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            logging.error(f"Broadcast error for {user_id}: {e}")
    
    await call.message.answer(f"✅ Broadcast Complete!\n\n👥 Sent: {count}\n🚫 Blocked/Failed: {blocked}")
    await state.clear()

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def input_media(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(media_id=photo_id)
    data = await state.get_data()
    await message.answer("✅ Image Set!", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def input_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    data = await state.get_data()
    await message.answer("✅ Text Set!", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def input_buttons(message: types.Message, state: FSMContext):
    if parse_buttons(message.text) is None:
        await message.answer("❌ Invalid format! Try `Text-URL`")
        return
    await state.update_data(buttons=message.text)
    data = await state.get_data()
    await message.answer("✅ Buttons Set!", reply_markup=get_broadcast_menu(data))
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
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400"
        }
    )

async def options_handler(request):
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400"
        }
    )

# --- API ENDPOINTS ---
async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing item_id or user_id"}, status=400)
        if item_id not in SHOP_ITEMS:
            return cors_response({"error": "Item not found"}, status=404)

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
        return cors_response({"result": link})
    except Exception as e:
        logging.error(f"Invoice Error: {e}")
        return cors_response({"error": str(e)}, status=500)

async def verify_join_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "No user ID"}, status=400)
        try:
            user_id = int(user_id)
        except ValueError:
            return cors_response({"joined": False, "error": "Invalid User ID format"})

        valid_statuses = ['member', 'administrator', 'creator', 'restricted']

        async def check_chat(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                return member.status in valid_statuses
            except TelegramBadRequest:
                return False
            except Exception as e:
                logging.error(f"Check error {chat_id}: {e}")
                return False

        is_in_channel, is_in_group = await asyncio.gather(
            check_chat(CHANNEL_USERNAME),
            check_chat(GROUP_USERNAME)
        )

        return cors_response({"joined": (is_in_channel and is_in_group)})
    except Exception as e:
        return cors_response({"error": str(e)}, status=500)

async def home(request):
    return web.Response(text="⛄ Snowman Adventure Backend is Running! ❄️")

# --- LIFECYCLE (WEBHOOK SETUP) ---
async def on_startup(app):
    logging.info(f"🔗 Setting webhook to: {WEBHOOK_URL}")
    try:
        await bot.set_webhook(
            WEBHOOK_URL,
            drop_pending_updates=True, # Optional: পুরানো আপডেট ক্লিয়ার করার জন্য
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
        info = await bot.get_webhook_info()
        logging.info(f"✅ Webhook Set Successfully! URL: {info.url}")
    except Exception as e:
        logging.error(f"❌ Failed to set webhook: {e}")

async def on_shutdown(app):
    logging.info("🔌 Shutting down...")
    await bot.delete_webhook()
    await bot.session.close()

# --- MAIN EXECUTION ---
def main():
    app = web.Application()
    
    # 1. Register Startup/Shutdown Handlers
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # 2. Add API Routes
    app.router.add_get('/', home)
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)

    # 3. Add Webhook Handler (Correct Way for Aiogram 3)
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    # এখানে POST মেথড হতে হবে
    app.router.add_post(WEBHOOK_PATH, webhook_requests_handler)

    # 4. Run App
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

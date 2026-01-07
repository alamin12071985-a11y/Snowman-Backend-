import os
import sys
import logging
import asyncio
import json
import random
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery, PreCheckoutQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# --- 1. LOGGING & CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# Admin & Channel Config
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# Validation
if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN or APP_URL is missing!")
    # For local testing without env vars, uncomment below (DO NOT USE IN PRODUCTION)
    # sys.exit(1)

# URL Formatting
APP_URL = (APP_URL or "").rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- 2. DATABASE SYSTEM (JSON) ---
DB_FILE = "users.json"

def load_users():
    """Loads user IDs from the JSON file safely."""
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r") as f:
            content = f.read()
            if not content: return set()
            return set(json.loads(content))
    except Exception as e:
        logging.error(f"⚠️ Database Load Error: {e}")
        return set()

def save_user(user_id):
    """Saves a new user ID to the database."""
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                json.dump(list(users), f)
            logging.info(f"🆕 New User Added: {user_id}")
    except Exception as e:
        logging.error(f"❌ Database Save Error: {e}")

# --- 3. SHOP ITEMS CONFIGURATION ---
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

# --- NEW: SPIN PRIZES CONFIGURATION ---
SPIN_PRIZES = [
    0.00000048, 
    0.00000060,
    0.00000080, 
    0.00000100,
    0.00000050, 
    0.00000030,
    0.00000020, 
    0.00000150
]

# --- 4. STATES & BOT INIT ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# --- 5. KEYBOARD HELPERS ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Play Snowman Adventure ☃️", url="https://t.me/snowmanadventurebot/app")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ])

def get_broadcast_menu(data):
    # Icons to show status
    s_media = "✅ Set" if data.get('media_id') else "❌ Empty"
    s_text = "✅ Set" if data.get('text') else "❌ Empty"
    s_btn = "✅ Set" if data.get('buttons') else "❌ Empty"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🖼️ Media [{s_media}]", callback_data="br_media"),
            InlineKeyboardButton(text=f"📝 Text [{s_text}]", callback_data="br_text")
        ],
        [InlineKeyboardButton(text=f"🔘 Buttons [{s_btn}]", callback_data="br_buttons")],
        [
            InlineKeyboardButton(text="👀 Preview", callback_data="br_preview"),
            InlineKeyboardButton(text="🚀 Send Now", callback_data="br_send")
        ],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="br_cancel")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="br_back")]])

def parse_buttons(text):
    if not text: return None
    try:
        kb = []
        for line in text.split('\n'):
            if '-' in line:
                t, u = line.split('-', 1)
                kb.append([InlineKeyboardButton(text=t.strip(), url=u.strip())])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except: return None

# ==========================================
#  6. BOT HANDLERS
# ==========================================

# --- Start Handler ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Handles /start command. Saves user and sends welcome message.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # Save user to DB
    save_user(user_id)
    
    welcome_text = (
        f"❄️☃️ <b>Hello, {first_name}!</b> ☃️❄️\n\n"
        "Welcome to <b>Snowman Adventure!</b> 🌨️\n"
        "Tap, earn coins, upgrade levels and invite friends!\n\n"
        "👇 <b>Click below to start playing:</b>"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# --- Broadcast System (Admin Only) ---

@router.message(Command("broadcast"))
async def broadcast_command(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return # Ignore non-admins
    await state.clear()
    await state.set_state(BroadcastState.menu)
    await message.answer("📢 <b>Broadcast Admin Panel</b>\n\nConfigure your post below:", reply_markup=get_broadcast_menu({}), parse_mode="HTML")

@router.callback_query(F.data == "br_back", StateFilter(BroadcastState))
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await call.message.edit_text("📢 <b>Broadcast Admin Panel</b>", reply_markup=get_broadcast_menu(data), parse_mode="HTML")

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def cancel_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast operation cancelled.")

# -- Inputs --
@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def ask_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_media)
    await call.message.edit_text("🖼️ <b>Send the photo/video now.</b>", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def save_media(message: types.Message, state: FSMContext):
    await state.update_data(media_id=message.photo[-1].file_id)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ <b>Media Saved!</b>", reply_markup=get_broadcast_menu(data), parse_mode="HTML")

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def ask_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    await call.message.edit_text("📝 <b>Send the text caption now.</b>", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def save_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ <b>Text Saved!</b>", reply_markup=get_broadcast_menu(data), parse_mode="HTML")

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def ask_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_buttons)
    await call.message.edit_text(
        "🔘 <b>Send Buttons in format:</b>\n`Text-URL`\n`Text-URL`\n\nExample:\n`Play-https://google.com`", 
        reply_markup=get_cancel_kb(), 
        parse_mode="Markdown"
    )

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def save_buttons(message: types.Message, state: FSMContext):
    if parse_buttons(message.text) is None:
        await message.answer("❌ Invalid Format! Try again.", reply_markup=get_cancel_kb())
        return
    await state.update_data(buttons=message.text)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ <b>Buttons Saved!</b>", reply_markup=get_broadcast_menu(data), parse_mode="HTML")

# -- Preview --
@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def preview_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media = data.get('media_id')
    text = data.get('text')
    kb = parse_buttons(data.get('buttons'))

    try:
        if media:
            await call.message.answer_photo(photo=media, caption=text, reply_markup=kb)
        elif text:
            await call.message.answer(text=text, reply_markup=kb)
        else:
            await call.answer("⚠️ Nothing to preview! Add text or media.", show_alert=True)
            return
        
        await call.message.answer("👆 <b>Preview above.</b> Menu:", reply_markup=get_broadcast_menu(data), parse_mode="HTML")
    except Exception as e:
        await call.answer(f"Error: {e}", show_alert=True)

# -- Sending Logic (Background Task) --
async def perform_broadcast(admin_chat_id, data):
    """
    Sends messages in background to avoid blocking the bot.
    """
    media = data.get('media_id')
    text = data.get('text')
    kb = parse_buttons(data.get('buttons'))
    users = load_users()
    
    sent_count = 0
    blocked_count = 0
    
    # Notify Admin Start
    await bot.send_message(admin_chat_id, f"🚀 <b>Broadcast Started!</b>\nTarget Users: {len(users)}", parse_mode="HTML")

    for user_id in users:
        try:
            if media:
                await bot.send_photo(chat_id=user_id, photo=media, caption=text, reply_markup=kb)
            elif text:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            sent_count += 1
            await asyncio.sleep(0.04) # 25 messages per second max
        except TelegramForbiddenError:
            blocked_count += 1
        except Exception as e:
            logging.warning(f"Failed to send to {user_id}: {e}")
    
    # Notify Admin Finish
    await bot.send_message(
        admin_chat_id, 
        f"✅ <b>Broadcast Complete!</b>\n\n📨 Sent: {sent_count}\n🚫 Blocked: {blocked_count}", 
        parse_mode="HTML"
    )

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def start_sending(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('text') and not data.get('media_id'):
        await call.answer("⚠️ Cannot send empty message!", show_alert=True)
        return
    
    await call.message.edit_text("⏳ <b>Sending in background...</b>\nYou will receive a report when done.", parse_mode="HTML")
    
    # Run the broadcast loop as a separate task so it doesn't freeze the bot
    asyncio.create_task(perform_broadcast(call.message.chat.id, data))
    
    await state.clear()

# --- Payment Handlers ---
@router.pre_checkout_query()
async def checkout_handler(checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    await message.answer("✅ <b>Payment Successful!</b>\nYour items have been added.", parse_mode="HTML")

# ==========================================
#  7. API HELPERS & ENDPOINTS (BACKEND)
# ==========================================

def cors_response(data, status=200):
    """Helper to return JSON with correct CORS headers."""
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
    """Handles Preflight (OPTIONS) requests for CORS."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400"
        }
    )

# -- Join Verify API --
async def verify_join_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "Missing user_id"}, status=400)

        try:
            user_id = int(user_id)
        except ValueError:
            return cors_response({"joined": False, "error": "Invalid ID format"}, status=400)

        # Check membership
        async def check_member(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                return member.status in ['member', 'administrator', 'creator', 'restricted']
            except Exception as e:
                logging.error(f"Membership Check Error ({chat_id}): {e}")
                return False

        in_channel = await check_member(CHANNEL_USERNAME)
        in_group = await check_member(GROUP_USERNAME)
        
        if in_channel and in_group:
            return cors_response({"joined": True})
        else:
            return cors_response({"joined": False})

    except Exception as e:
        logging.error(f"API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# -- Invoice API --
async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing data"}, status=400)
        
        item = SHOP_ITEMS.get(item_id)
        if not item:
            return cors_response({"error": "Item not found"}, status=404)

        prices = [LabeledPrice(label=f"Buy {item_id}", amount=item['price'])]
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Stars Payment
            currency="XTR",
            prices=prices,
        )
        return cors_response({"result": link})

    except Exception as e:
        logging.error(f"Invoice API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# -- UPDATED: Ad Verification API --
async def verify_ad_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        # New parameter for provider tracking (Adsgram vs GigaPub)
        provider = data.get('provider', 'unknown') 

        if not user_id:
            return cors_response({"success": False, "error": "Missing user_id"}, status=400)
        
        logging.info(f"📺 Ad watched by user {user_id} via provider: {provider}")
        
        # Here you could extend logic to increment specific counters in a database if needed.
        # For now, we simply confirm success so frontend can process rewards.
        
        return cors_response({"success": True})

    except Exception as e:
        logging.error(f"Ad Verify API Error: {e}")
        return cors_response({"success": False, "error": str(e)}, status=500)

# -- NEW: Play Spin API (Server-side Logic) --
async def play_spin_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False, "error": "Missing user_id"}, status=400)
            
        # Determine prize server-side to prevent cheating
        # Random index 0-7
        idx = random.randint(0, len(SPIN_PRIZES) - 1)
        amount = SPIN_PRIZES[idx]
        
        logging.info(f"🎰 User {user_id} spun: Index {idx}, Amount {amount}")
        
        return cors_response({
            "success": True,
            "index": idx,
            "amount": amount
        })
    except Exception as e:
        logging.error(f"Spin API Error: {e}")
        return cors_response({"success": False}, status=500)

# -- NEW: Complete Task API --
async def complete_task_api(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        if not user_id or not task_id:
            return cors_response({"success": False}, status=400)
            
        logging.info(f"✅ User {user_id} completed task {task_id}")
        # Here you could check database to see if task was already done
        
        return cors_response({"success": True})
    except Exception as e:
        logging.error(f"Task API Error: {e}")
        return cors_response({"success": False}, status=500)

async def home_handler(request):
    return web.Response(text="☃️ Snowman Adventure Backend Running... ❄️")

# ==========================================
#  8. LIFECYCLE & EXECUTION
# ==========================================

async def on_startup(bot: Bot):
    if WEBHOOK_URL.startswith("http"):
        logging.info(f"🔗 Setting Webhook: {WEBHOOK_URL}")
        await bot.set_webhook(WEBHOOK_URL)
    else:
        logging.warning("⚠️ No APP_URL set, webhook not configured.")

async def on_shutdown(bot: Bot):
    logging.info("🔌 Removing Webhook...")
    await bot.delete_webhook()

def main():
    # Register Startup/Shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Setup Web App
    app = web.Application()
    
    # Routes
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)
    
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    
    # Ad Route (Updated)
    app.router.add_post('/verify-ad', verify_ad_api)
    app.router.add_options('/verify-ad', options_handler)
    
    # New Routes
    app.router.add_post('/play-spin', play_spin_api)
    app.router.add_options('/play-spin', options_handler)
    
    app.router.add_post('/complete-task', complete_task_api)
    app.router.add_options('/complete-task', options_handler)
    
    app.router.add_get('/', home_handler)

    # Webhook Handler
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Run
    setup_application(app, dp, bot=bot)
    
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

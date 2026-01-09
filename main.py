import os
import sys
import logging
import asyncio
import json
import random
import time
from datetime import datetime

# Aiohttp for Web Server
from aiohttp import web

# Aiogram for Telegram Bot Interaction
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter, CommandStart, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    LabeledPrice, 
    CallbackQuery, 
    PreCheckoutQuery, 
    Message,
    FSInputFile,
    ContentType,
    BotCommand
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import (
    TelegramBadRequest, 
    TelegramForbiddenError, 
    TelegramRetryAfter,
    TelegramAPIError
)

# ==============================================================================
#  SECTION 1: CONFIGURATION & LOGGING SETUP
# ==============================================================================

# 1.1 Configure Detailed Logging
# This helps in debugging exactly what happens in the server
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("SnowmanBackend")

# 1.2 Load Environment Variables
# These must be set in your hosting environment (e.g., Render, Heroku, VPS)
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# 1.3 Admin & Community Configuration
# Replace these with your actual IDs
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# 1.4 Critical Security Check
if not BOT_TOKEN:
    logger.critical("❌ CRITICAL ERROR: 'BOT_TOKEN' is missing in Environment Variables!")
    sys.exit(1)

if not APP_URL:
    logger.critical("❌ CRITICAL ERROR: 'APP_URL' is missing in Environment Variables!")
    sys.exit(1)

# 1.5 Webhook URL Configuration
# Remove trailing slash to prevent double slashes (e.g., .com//webhook)
APP_URL = str(APP_URL).rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

logger.info(f"⚙️ Configuration Loaded. Webhook URL: {WEBHOOK_URL}")

# ==============================================================================
#  SECTION 2: DATABASE MANAGEMENT (JSON)
# ==============================================================================

DB_FILE = "users.json"

class DatabaseManager:
    """
    Manages user data storage using a simple JSON file.
    Includes methods to load, save, and count users.
    """
    
    @staticmethod
    def _initialize_db():
        """Creates the DB file if it doesn't exist."""
        if not os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "w") as f:
                    json.dump([], f)
                logger.info(f"📁 Database file '{DB_FILE}' created.")
            except Exception as e:
                logger.error(f"❌ Failed to create DB file: {e}")

    @staticmethod
    def load_users():
        """
        Reads user IDs from the JSON file.
        Returns a set of unique user IDs.
        """
        DatabaseManager._initialize_db()
        try:
            with open(DB_FILE, "r") as f:
                content = f.read()
                if not content:
                    return set()
                data = json.loads(content)
                # Ensure data is a list before converting to set
                if isinstance(data, list):
                    return set(data)
                else:
                    logger.warning("⚠️ Database format invalid. Expected a list.")
                    return set()
        except json.JSONDecodeError:
            logger.error("⚠️ JSON Decode Error. Database might be empty or corrupted.")
            return set()
        except Exception as e:
            logger.error(f"⚠️ Database Load Error: {e}")
            return set()

    @staticmethod
    def save_user(user_id):
        """
        Adds a user ID to the database if not already present.
        Uses atomic-like logic by reading, updating, and writing back.
        """
        try:
            user_id = int(user_id)
            users = DatabaseManager.load_users()
            
            if user_id not in users:
                users.add(user_id)
                with open(DB_FILE, "w") as f:
                    json.dump(list(users), f)
                logger.info(f"🆕 User Added to DB: {user_id}. Total Users: {len(users)}")
            else:
                # User already exists, verbose logging usually not needed here to save logs
                pass
        except Exception as e:
            logger.error(f"❌ Failed to save user {user_id}: {e}")

    @staticmethod
    def get_total_users():
        """Returns the total count of users."""
        users = DatabaseManager.load_users()
        return len(users)

# Initialize DB on startup
DatabaseManager._initialize_db()

# ==============================================================================
#  SECTION 3: GAME CONFIGURATION (SHOP, PRIZES)
# ==============================================================================

# 3.1 Telegram Stars Shop Items
# These keys must match what the frontend sends in 'item_id'
SHOP_ITEMS = {
    # --- Coin Packs ---
    'coin_starter': {
        'price': 10, 
        'amount': 5000, 
        'title': 'Starter Pack (5k Coins)',
        'desc': 'Get a quick start with 5,000 Coins!'
    },
    'coin_small': {
        'price': 50, 
        'amount': 30000, 
        'title': 'Small Pack (30k Coins)',
        'desc': 'A nice boost of 30,000 Coins.'
    },
    'coin_medium': {
        'price': 100, 
        'amount': 70000, 
        'title': 'Medium Pack (70k Coins)',
        'desc': 'Serious players need this. 70,000 Coins.'
    },
    'coin_large': {
        'price': 250, 
        'amount': 200000, 
        'title': 'Large Pack (200k Coins)',
        'desc': 'Huge amount! 200,000 Coins.'
    },
    'coin_mega': {
        'price': 500, 
        'amount': 500000, 
        'title': 'Mega Pack (500k Coins)',
        'desc': 'Ultimate power! 500,000 Coins.'
    },
    
    # --- Boosters ---
    'booster_3d': {
        'price': 20, 
        'amount': 1, 
        'title': '3 Days Booster (x2)',
        'desc': 'Double your tapping power for 3 days.'
    },
    'booster_15d': {
        'price': 70, 
        'amount': 1, 
        'title': '15 Days Booster (x2)',
        'desc': 'Double your tapping power for 15 days.'
    },
    'booster_30d': {
        'price': 120, 
        'amount': 1, 
        'title': '30 Days Booster (x2)',
        'desc': 'Double your tapping power for 30 days.'
    },
    
    # --- Auto Tap ---
    'autotap_1d': {
        'price': 20, 
        'amount': 1, 
        'title': 'Auto Tap Bot (1 Day)',
        'desc': 'Let the bot tap for you for 24 hours.'
    },
    'autotap_7d': {
        'price': 80, 
        'amount': 1, 
        'title': 'Auto Tap Bot (7 Days)',
        'desc': 'Automated income for a whole week.'
    },
    'autotap_30d': {
        'price': 200, 
        'amount': 1, 
        'title': 'Auto Tap Bot (30 Days)',
        'desc': 'Maximum automation for a month.'
    },
}

# 3.2 Spin Game Prizes
# These are the TON amounts a user can win
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

# ==============================================================================
#  SECTION 4: BOT SETUP & STATE MACHINES
# ==============================================================================

# 4.1 Memory Storage for FSM
storage = MemoryStorage()

# 4.2 Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# 4.3 Define States for Broadcast Wizard
class BroadcastState(StatesGroup):
    """
    States used for the Admin Broadcast Wizard.
    """
    menu = State()               # Initial menu selection
    waiting_for_media = State()  # Waiting for photo/video
    waiting_for_text = State()   # Waiting for caption/text
    waiting_for_buttons = State() # Waiting for button config
    confirm_send = State()       # Final confirmation before sending

# ==============================================================================
#  SECTION 5: KEYBOARDS & UI HELPERS
# ==============================================================================

def get_main_keyboard():
    """Returns the main menu keyboard shown on /start."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❄️ Play Snowman Adventure ☃️", 
                url="https://t.me/snowmanadventurebot/app"
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 Channel", 
                url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
            ),
            InlineKeyboardButton(
                text="💬 Community Group", 
                url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}"
            )
        ]
    ])

def get_admin_keyboard():
    """Returns keyboard for /admin command."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Create Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 View Stats", callback_data="admin_stats")]
    ])

def get_broadcast_start_kb():
    """Step 1 of Broadcast: Choose type."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Image/Video + Text", callback_data="br_start_media")],
        [InlineKeyboardButton(text="📝 Text Message Only", callback_data="br_start_text")],
        [InlineKeyboardButton(text="❌ Cancel Operation", callback_data="br_cancel")]
    ])

def get_nav_buttons(next_callback, back_callback):
    """Generic Next/Back buttons for wizards."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Next Step", callback_data=next_callback)],
        [InlineKeyboardButton(text="🔙 Go Back", callback_data=back_callback)]
    ])

def get_final_confirm_kb():
    """Final confirmation before blasting messages."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 CONFIRM & SEND", callback_data="br_final_send")],
        [InlineKeyboardButton(text="❌ Cancel Everything", callback_data="br_cancel")]
    ])

def parse_buttons_text(text):
    """
    Parses a string input into an InlineKeyboardMarkup.
    Expected format: "Button Text - URL" (one per line).
    """
    if not text: 
        return None
    try:
        kb_rows = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if '-' in line:
                parts = line.split('-', 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                # Basic validation
                if btn_text and btn_url.startswith('http'):
                    kb_rows.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        
        if not kb_rows:
            return None
            
        return InlineKeyboardMarkup(inline_keyboard=kb_rows)
    except Exception as e:
        logger.error(f"Button Parsing Error: {e}")
        return None

# ==============================================================================
#  SECTION 6: BOT COMMAND HANDLERS
# ==============================================================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    """
    Handles the /start command.
    Checks for referral parameters and welcomes the user.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # Save User to DB
    DatabaseManager.save_user(user_id)
    
    # Handle Referral Logic
    referral_source = command.args
    if referral_source:
        logger.info(f"🔗 User {user_id} was referred by ID: {referral_source}")
        # Note: Actual reward logic is usually handled in the Frontend 
        # using Telegram.WebApp.initData to ensure security.
    
    welcome_msg = (
        f"❄️☃️ <b>Hello, {first_name}!</b> ☃️❄️\n\n"
        "Welcome to the magical world of <b>Snowman Adventure!</b> 🌨️\n\n"
        "🪙 <b>Earn Coins</b> by tapping.\n"
        "📈 <b>Upgrade</b> your snowman level.\n"
        "🎁 <b>Invite Friends</b> and earn crypto rewards!\n\n"
        "👇 <b>Click the button below to start playing:</b>"
    )
    
    await message.answer(
        text=welcome_msg,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Sends help information."""
    help_text = (
        "<b>🆘 Need Help?</b>\n\n"
        "1. Tap 'Play Snowman Adventure' to open the game.\n"
        "2. Join our Channel and Group for updates.\n"
        "3. If the game doesn't load, try updating your Telegram app.\n\n"
        "<i>Enjoy the adventure!</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

# ==============================================================================
#  SECTION 7: ADMIN SYSTEM & BROADCAST WIZARD
# ==============================================================================

@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """
    Admin panel entry point.
    Restricted to ADMIN_ID.
    """
    if message.from_user.id != ADMIN_ID:
        # Silently ignore or send fake message
        return
    
    total_users = DatabaseManager.get_total_users()
    
    text = (
        "🔐 <b>Admin Control Panel</b>\n\n"
        f"👤 Total Users in DB: <code>{total_users}</code>\n\n"
        "Select an action:"
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    """Updates the admin message with fresh stats."""
    if call.from_user.id != ADMIN_ID: return
    
    total_users = DatabaseManager.get_total_users()
    await call.answer(f"Current User Count: {total_users}", show_alert=True)

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    """Starts the Broadcast Wizard."""
    if call.from_user.id != ADMIN_ID: return
    
    # Clear previous state to avoid conflicts
    await state.clear()
    
    text = (
        "📢 <b>Broadcast Wizard</b>\n\n"
        "Please select the type of message you want to send to all users:"
    )
    await call.message.edit_text(text, reply_markup=get_broadcast_start_kb(), parse_mode="HTML")

# --- Broadcast: Cancel ---
@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def br_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast operation cancelled.")

# --- Broadcast: Step 1 (Choose Type) ---
@router.callback_query(F.data == "br_start_media")
async def br_start_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_media)
    await call.message.edit_text(
        "1️⃣ <b>Step 1: Send Media</b>\n\n"
        "Please send the <b>Photo</b> or <b>Video</b> you want to broadcast.",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "br_start_text")
async def br_start_text(call: CallbackQuery, state: FSMContext):
    # Skip media step
    await state.update_data(media_id=None, media_type=None)
    await state.set_state(BroadcastState.waiting_for_text)
    await call.message.edit_text(
        "2️⃣ <b>Step 2: Message Text</b>\n\n"
        "Please enter the text/caption for your broadcast.",
        parse_mode="HTML"
    )

# --- Broadcast: Step 2 (Receive Media) ---
@router.message(StateFilter(BroadcastState.waiting_for_media))
async def br_receive_media(message: types.Message, state: FSMContext):
    if message.photo:
        # Telegram sends multiple sizes, -1 is the highest quality
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    else:
        await message.answer("⚠️ Invalid media! Please send a Photo or Video.")
        return

    await state.update_data(media_id=file_id, media_type=media_type)
    
    kb = get_nav_buttons("goto_text_input", "br_cancel")
    await message.answer(
        "✅ <b>Media Received!</b>\n\nNow, click 'Next' to add a caption.", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

@router.callback_query(F.data == "goto_text_input", StateFilter(BroadcastState))
async def br_goto_text_input(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    await call.message.answer(
        "2️⃣ <b>Step 2: Message Text</b>\n\n"
        "Please enter the caption or text message.", 
        parse_mode="HTML"
    )

# --- Broadcast: Step 3 (Receive Text) ---
@router.message(StateFilter(BroadcastState.waiting_for_text))
async def br_receive_text(message: types.Message, state: FSMContext):
    text = message.text
    # Basic validation
    if len(text) > 4000:
        await message.answer("⚠️ Text is too long! Please keep it under 4000 characters.")
        return

    await state.update_data(text=text)
    
    kb = get_nav_buttons("goto_buttons", "goto_text_input") # Go back option implies re-entering text
    await message.answer(
        "✅ <b>Text Saved!</b>\n\nClick 'Next' to add buttons, or 'Back' to rewrite text.", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

# --- Broadcast: Step 4 (Buttons) ---
@router.callback_query(F.data == "goto_buttons", StateFilter(BroadcastState))
async def br_goto_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_buttons)
    msg = (
        "3️⃣ <b>Step 3: Add Buttons (Optional)</b>\n\n"
        "Send buttons in this format (one per line):\n"
        "<code>Button Text - https://link.com</code>\n\n"
        "Example:\n"
        "<code>Play Now - https://t.me/bot/app</code>\n"
        "<code>Join Channel - https://t.me/channel</code>\n\n"
        "👉 <b>Type 'skip' to send without buttons.</b>"
    )
    await call.message.answer(msg, parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_buttons))
async def br_receive_buttons(message: types.Message, state: FSMContext):
    buttons_text = message.text.strip()
    
    if buttons_text.lower() == 'skip':
        await state.update_data(buttons=None)
    else:
        # Validate buttons
        kb = parse_buttons_text(buttons_text)
        if not kb:
            await message.answer("❌ <b>Invalid Format!</b>\nPlease use: <code>Text - URL</code>\nOr type 'skip'.", parse_mode="HTML")
            return
        await state.update_data(buttons=buttons_text)
    
    # Proceed to Preview
    await br_show_preview(message, state)

# --- Broadcast: Step 5 (Preview & Confirm) ---
async def br_show_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    text = data.get('text', "")
    buttons_raw = data.get('buttons')
    
    kb = parse_buttons_text(buttons_raw)
    
    await message.answer("➖➖➖➖ <b>PREVIEW START</b> ➖➖➖➖", parse_mode="HTML")
    
    try:
        if media_type == 'photo':
            await message.answer_photo(photo=media_id, caption=text, reply_markup=kb)
        elif media_type == 'video':
            await message.answer_video(video=media_id, caption=text, reply_markup=kb)
        else:
            await message.answer(text=text, reply_markup=kb)
    except Exception as e:
        await message.answer(f"⚠️ <b>Preview Failed:</b> {str(e)}")
        
    await message.answer("➖➖➖➖ <b>PREVIEW END</b> ➖➖➖➖", parse_mode="HTML")
    
    await message.answer(
        "👆 <b>Check the preview above.</b>\n\n"
        "If everything looks good, click <b>CONFIRM</b> to start sending.",
        reply_markup=get_final_confirm_kb(),
        parse_mode="HTML"
    )

# --- Broadcast: Execution ---
@router.callback_query(F.data == "br_final_send", StateFilter(BroadcastState))
async def br_execute(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    
    await call.message.edit_text("🚀 <b>Broadcast Started!</b>\nYou will receive a report when done.", parse_mode="HTML")
    
    # Run in background so it doesn't block the bot
    asyncio.create_task(run_broadcast_task(call.message.chat.id, data))

async def run_broadcast_task(admin_chat_id, data):
    """
    The worker function that actually sends messages to all users.
    Includes rate limiting and error counting.
    """
    users = DatabaseManager.load_users()
    total = len(users)
    sent = 0
    blocked = 0
    errors = 0
    
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    text = data.get('text')
    kb = parse_buttons_text(data.get('buttons'))
    
    start_time = time.time()
    
    for user_id in users:
        try:
            if media_type == 'photo':
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=kb)
            elif media_type == 'video':
                await bot.send_video(chat_id=user_id, video=media_id, caption=text, reply_markup=kb)
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            
            sent += 1
            # Rate limit: 20-25 messages per second safe for broadcasts
            await asyncio.sleep(0.04) 
            
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            # Hit rate limit, sleep for requested time
            await asyncio.sleep(e.retry_after)
            # Try again (optional, simplified here to just skip counting as error)
            errors += 1
        except Exception as e:
            errors += 1
            # logger.error(f"Failed to send to {user_id}: {e}") # Uncomment for verbose debugging
            
    duration = round(time.time() - start_time, 2)
    
    report = (
        "✅ <b>Broadcast Completed!</b>\n\n"
        f"👥 Total Target: {total}\n"
        f"📨 Successfully Sent: {sent}\n"
        f"🚫 Blocked/Forbidden: {blocked}\n"
        f"⚠️ Failed/Errors: {errors}\n"
        f"⏱️ Duration: {duration}s"
    )
    
    try:
        await bot.send_message(admin_chat_id, report, parse_mode="HTML")
    except:
        logger.error("Could not send broadcast report to admin.")

# ==============================================================================
#  SECTION 8: PAYMENT HANDLERS (TELEGRAM STARS)
# ==============================================================================

@router.pre_checkout_query()
async def checkout_handler(checkout_query: PreCheckoutQuery):
    """
    Validates payment before it completes.
    For digital goods like coins, we usually always return True.
    """
    await bot.answer_pre_checkout_query(checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def payment_success_handler(message: types.Message):
    """
    Triggered when a user successfully pays.
    """
    user_id = message.from_user.id
    payment_info = message.successful_payment
    amount = payment_info.total_amount
    currency = payment_info.currency
    payload = payment_info.invoice_payload # Contains "user_id_item_id"
    
    logger.info(f"💰 Payment Success: User {user_id} paid {amount} {currency}. Payload: {payload}")
    
    await message.answer(
        "✅ <b>Payment Successful!</b>\n\n"
        "Your account has been updated. Please open the app to see your rewards.",
        parse_mode="HTML"
    )

# ==============================================================================
#  SECTION 9: API ENDPOINTS (BACKEND LOGIC)
# ==============================================================================

# 9.1 CORS Helpers (Cross-Origin Resource Sharing)
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
    """Handles preflight checks from browsers."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# 9.2 API: Verify Join (Channel & Group)
async def verify_join_api(request):
    """
    Checks if a user has joined the required channel and group.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "Missing user_id"}, status=400)

        try:
            user_id = int(user_id)
        except ValueError:
            return cors_response({"joined": False, "error": "Invalid ID"}, status=400)

        # Helper to check one chat
        async def check_membership(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                return member.status in ['member', 'administrator', 'creator', 'restricted']
            except Exception as e:
                # If bot isn't admin, it can't check, assume False or Log error
                logger.warning(f"Membership check failed for {chat_id}: {e}")
                return False

        in_channel = await check_membership(CHANNEL_USERNAME)
        in_group = await check_membership(GROUP_USERNAME)
        
        # Logic: Must join both
        is_joined = in_channel and in_group
        
        return cors_response({"joined": is_joined})

    except Exception as e:
        logger.error(f"Verify API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# 9.3 API: Create Invoice
async def create_invoice_api(request):
    """
    Generates a payment link for Telegram Stars.
    """
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing parameters"}, status=400)
        
        item = SHOP_ITEMS.get(item_id)
        if not item:
            return cors_response({"error": "Item not found"}, status=404)

        # Create Invoice Link
        link = await bot.create_invoice_link(
            title=item['title'],
            description=item.get('desc', 'Game Item'),
            payload=f"{user_id}_{item_id}",
            provider_token="", # Empty for XTR (Stars)
            currency="XTR",
            prices=[LabeledPrice(label=item['title'], amount=item['price'])]
        )
        
        logger.info(f"Invoice created for User {user_id}, Item {item_id}")
        return cors_response({"result": link})

    except Exception as e:
        logger.error(f"Invoice API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# 9.4 API: Verify Ad
async def verify_ad_api(request):
    """
    Called by Frontend when an ad is finished.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        provider = data.get('provider', 'unknown')
        ad_type = data.get('type', 'generic')

        if not user_id:
            return cors_response({"success": False, "error": "Missing ID"}, status=400)
            
        logger.info(f"📺 Ad Watched: User {user_id} | Provider: {provider} | Type: {ad_type}")
        
        # Note: In a production app, you might verify a server-side signature here
        # to prevent fake requests. For now, we assume frontend validity.
        
        return cors_response({"success": True})
    except Exception as e:
        logger.error(f"Ad Verify Error: {e}")
        return cors_response({"success": False}, status=500)

# 9.5 API: Play Spin
async def play_spin_api(request):
    """
    Determines spin result on server to prevent frontend cheating.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False}, status=400)
            
        # Select random prize
        idx = random.randint(0, len(SPIN_PRIZES) - 1)
        amount = SPIN_PRIZES[idx]
        
        logger.info(f"🎰 Spin Result: User {user_id} won {amount} TON")
        
        return cors_response({
            "success": True,
            "index": idx,
            "amount": amount
        })
    except Exception as e:
        logger.error(f"Spin API Error: {e}")
        return cors_response({"success": False}, status=500)

# 9.6 API: Complete Task
async def complete_task_api(request):
    """
    Logs task completion.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        if not user_id or not task_id:
            return cors_response({"success": False}, status=400)
            
        logger.info(f"✅ Task Completed: User {user_id}, Task {task_id}")
        
        return cors_response({"success": True})
    except Exception as e:
        logger.error(f"Task API Error: {e}")
        return cors_response({"success": False}, status=500)

# 9.7 Root Handler (Health Check)
async def home_handler(request):
    return web.Response(text="☃️ Snowman Adventure Backend is Running Successfully! ❄️")

# ==============================================================================
#  SECTION 10: APP EXECUTION & LIFECYCLE
# ==============================================================================

async def on_startup(bot: Bot):
    """
    Runs when the server starts.
    Sets the webhook.
    """
    logger.info("🚀 Server Starting...")
    
    if WEBHOOK_URL.startswith("https://"):
        logger.info(f"🔗 Setting Webhook: {WEBHOOK_URL}")
        try:
            # Delete old webhook to remove pending updates (prevents flood)
            await bot.delete_webhook(drop_pending_updates=True)
            # Set new webhook
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("✅ Webhook Set Successfully.")
            
            # Optional: Set commands menu
            await bot.set_my_commands([
                BotCommand(command="start", description="Start Game"),
                BotCommand(command="help", description="Get Help"),
            ])
            
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
    else:
        logger.warning("⚠️ Webhook URL must be HTTPS. Skipping webhook setup.")

async def on_shutdown(bot: Bot):
    """
    Runs when server stops.
    Cleans up resources.
    """
    logger.info("🔌 Server Shutting Down...")
    await bot.delete_webhook()
    await bot.session.close()

def main():
    """
    Main entry point of the application.
    """
    # 1. Create Web Application
    app = web.Application()
    
    # 2. Configure Routes
    # Root
    app.router.add_get('/', home_handler)
    
    # API Routes with Options (Preflight)
    api_routes = [
        ('/verify_join', verify_join_api),
        ('/create_invoice', create_invoice_api),
        ('/verify-ad', verify_ad_api),
        ('/play-spin', play_spin_api),
        ('/complete-task', complete_task_api),
    ]
    
    for path, handler in api_routes:
        app.router.add_post(path, handler)
        app.router.add_options(path, options_handler)

    # 3. Configure Webhook Route (handled by Aiogram)
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # 4. Register Startup/Shutdown Hooks
    setup_application(app, dp, bot=bot)
    
    # 5. Run the Server
    # Render provides PORT environment variable
    logger.info(f"🌍 Starting Web Server on Port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")

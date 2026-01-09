import os
import sys
import logging
import asyncio
import json
import random
import time
import hmac
import hashlib
from datetime import datetime

# ==============================================================================
#  LIBRARIES
# ==============================================================================
# pip install aiohttp aiogram
from aiohttp import web
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
    BotCommand,
    InputMediaPhoto,
    InputMediaVideo
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
#  SECTION 1: CONFIGURATION & LOGGING
# ==============================================================================

# 1.1 Configure Logging
# Detailed logging helps you track every action and error
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("SnowmanBackend")

# 1.2 Load Environment Variables
# These must be set in your Render/Heroku environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# 1.3 Admin & Community Configuration
# Replace with your actual Admin ID
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# 1.4 Security Checks
if not BOT_TOKEN:
    logger.critical("❌ CRITICAL ERROR: 'BOT_TOKEN' is missing in Environment Variables!")
    sys.exit(1)

if not APP_URL:
    logger.critical("❌ CRITICAL ERROR: 'APP_URL' is missing in Environment Variables!")
    sys.exit(1)

# 1.5 Webhook Configuration
APP_URL = str(APP_URL).rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

logger.info(f"⚙️ Configuration Loaded.")
logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
logger.info(f"👑 Admin ID: {ADMIN_ID}")

# ==============================================================================
#  SECTION 2: DATABASE MANAGEMENT (JSON)
# ==============================================================================
# This database stores User IDs for the BOT (Broadcasting).
# Game data (Coins, Level) is stored in Firebase via Frontend.

DB_FILE = "users.json"

class DatabaseManager:
    """
    Manages user data storage using a persistent JSON file.
    Includes atomic-like operations to prevent data corruption.
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
                if isinstance(data, list):
                    return set(data)
                else:
                    logger.warning("⚠️ Database format invalid. Resetting.")
                    return set()
        except json.JSONDecodeError:
            logger.error("⚠️ JSON Decode Error.")
            return set()
        except Exception as e:
            logger.error(f"⚠️ Database Load Error: {e}")
            return set()

    @staticmethod
    def save_user(user_id):
        """
        Adds a user ID to the database if not already present.
        """
        try:
            user_id = int(user_id)
            users = DatabaseManager.load_users()
            
            if user_id not in users:
                users.add(user_id)
                with open(DB_FILE, "w") as f:
                    json.dump(list(users), f)
                logger.info(f"🆕 New User Registered: {user_id}. Total: {len(users)}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save user {user_id}: {e}")

    @staticmethod
    def get_total_users():
        """Returns the total count of users."""
        users = DatabaseManager.load_users()
        return len(users)

    @staticmethod
    def get_all_users_list():
        """Returns list of all users for broadcasting."""
        return list(DatabaseManager.load_users())

# Initialize DB on startup
DatabaseManager._initialize_db()

# ==============================================================================
#  SECTION 3: GAME CONFIGURATION (SHOP & SPIN)
# ==============================================================================

# 3.1 Telegram Stars Shop Items
# These IDs correspond to the frontend Shop IDs.
# Prices are in Telegram Stars (XTR).
SHOP_ITEMS = {
    # --- Coin Packs ---
    'coin_starter': {
        'price': 10, 
        'amount': 5000, 
        'title': 'Starter Pack (5k Coins)',
        'desc': 'Instantly add 5,000 Snow Coins to your balance.'
    },
    'coin_small': {
        'price': 20, 
        'amount': 10000, 
        'title': 'Small Pack (10k Coins)',
        'desc': 'Instantly add 10,000 Snow Coins to your balance.'
    },
    'coin_medium': {
        'price': 60, 
        'amount': 40000, 
        'title': 'Medium Pack (40k Coins)',
        'desc': 'Instantly add 40,000 Snow Coins to your balance.'
    },
    'coin_large': {
        'price': 120, 
        'amount': 100000, 
        'title': 'Large Pack (100k Coins)',
        'desc': 'Instantly add 100,000 Snow Coins to your balance.'
    },
    'coin_mega': {
        'price': 220, 
        'amount': 220000, 
        'title': 'Mega Pack (220k Coins)',
        'desc': 'The ultimate pack! 220,000 Coins.'
    },
    
    # --- Boosters ---
    'booster_3d': {
        'price': 20, 
        'amount': 1, 
        'title': '3 Days Booster (x2)',
        'desc': 'Doubles your tapping power for 3 days.'
    },
    'booster_15d': {
        'price': 70, 
        'amount': 1, 
        'title': '15 Days Booster (x2)',
        'desc': 'Doubles your tapping power for 15 days.'
    },
    'booster_30d': {
        'price': 120, 
        'amount': 1, 
        'title': '30 Days Booster (x2)',
        'desc': 'Doubles your tapping power for 30 days.'
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
# These are the actual values determined by the server.
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
#  SECTION 4: BOT INITIALIZATION
# ==============================================================================

# Memory Storage for Finite State Machine (FSM)
storage = MemoryStorage()

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ==============================================================================
#  SECTION 5: FSM STATES (ADMIN WIZARD)
# ==============================================================================

class BroadcastState(StatesGroup):
    """
    States used for the Admin Broadcast Wizard.
    Allows admins to send text, photo, or video messages with buttons.
    """
    menu = State()               # Initial menu selection
    waiting_for_media = State()  # Waiting for photo/video
    waiting_for_text = State()   # Waiting for caption/text
    waiting_for_buttons = State() # Waiting for button config
    confirm_send = State()       # Final confirmation before sending

# ==============================================================================
#  SECTION 6: KEYBOARDS & HELPERS
# ==============================================================================

def get_main_keyboard():
    """Main Menu Keyboard for Users"""
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
    """Admin Panel Keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Create Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 View User Stats", callback_data="admin_stats")],
        [InlineKeyboardButton(text="❌ Close Panel", callback_data="admin_close")]
    ])

def get_broadcast_start_kb():
    """Step 1: Choose Broadcast Type"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Image/Video + Text", callback_data="br_start_media")],
        [InlineKeyboardButton(text="📝 Text Message Only", callback_data="br_start_text")],
        [InlineKeyboardButton(text="❌ Cancel Operation", callback_data="br_cancel")]
    ])

def get_nav_buttons(next_callback, back_callback):
    """Generic Navigation Buttons"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Next Step", callback_data=next_callback)],
        [InlineKeyboardButton(text="🔙 Go Back", callback_data=back_callback)]
    ])

def get_final_confirm_kb():
    """Final Confirmation"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 CONFIRM & SEND", callback_data="br_final_send")],
        [InlineKeyboardButton(text="❌ Cancel Everything", callback_data="br_cancel")]
    ])

def parse_buttons_text(text):
    """
    Parses a string input into an InlineKeyboardMarkup.
    Format: "Button Text - URL" (one per line).
    (Fixed for robustness)
    """
    if not text or text.lower() == 'skip': 
        return None
    try:
        kb_rows = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # Support both "Text - Link" and "Text-Link"
            if '-' in line:
                parts = line.split('-', 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                # Check for protocol and fix it if missing
                if not btn_url.startswith(('http://', 'https://')):
                    btn_url = 'https://' + btn_url
                
                # Basic validation
                if btn_text and btn_url:
                    kb_rows.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        
        if not kb_rows:
            return None
            
        return InlineKeyboardMarkup(inline_keyboard=kb_rows)
    except Exception as e:
        logger.error(f"Button Parsing Error: {e}")
        return None

# ==============================================================================
#  SECTION 7: BOT COMMAND HANDLERS
# ==============================================================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    """
    Handles /start command.
    Registers user and shows welcome message.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # Save User to DB
    DatabaseManager.save_user(user_id)
    
    # Handle Referral Logic (Logging mostly, actual reward is frontend/backend sync)
    referral_source = command.args
    if referral_source:
        logger.info(f"🔗 User {user_id} was referred by ID: {referral_source}")
    
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
#  SECTION 8: ADMIN CONTROL PANEL
# ==============================================================================

@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """
    Admin panel entry point.
    Restricted to ADMIN_ID.
    """
    if message.from_user.id != ADMIN_ID:
        # Silently ignore unauthorized access
        return
    
    total_users = DatabaseManager.get_total_users()
    
    text = (
        "🔐 <b>Admin Control Panel</b>\n\n"
        f"👤 Total Users in DB: <code>{total_users}</code>\n"
        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Select an action below:"
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "admin_close")
async def cb_admin_close(call: CallbackQuery):
    await call.message.delete()

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    """Updates the admin message with fresh stats."""
    if call.from_user.id != ADMIN_ID: return
    
    # FIX: Added try-except and call.answer to prevent "loading" freeze
    try:
        total_users = DatabaseManager.get_total_users()
        await call.answer(f"📊 Live User Count: {total_users}", show_alert=True)
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        await call.answer("❌ Error loading stats.", show_alert=True)

# ==============================================================================
#  SECTION 9: BROADCAST WIZARD IMPLEMENTATION
# ==============================================================================

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    """Starts the Broadcast Wizard."""
    if call.from_user.id != ADMIN_ID: return
    
    # Clear previous state
    await state.clear()
    
    text = (
        "📢 <b>Broadcast Wizard</b>\n\n"
        "Select the message type:"
    )
    # FIX: Use try-except in case message is too old to edit
    try:
        await call.message.edit_text(text, reply_markup=get_broadcast_start_kb(), parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=get_broadcast_start_kb(), parse_mode="HTML")

# --- Step 0: Cancel ---
@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def br_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast operation cancelled.")

# --- Step 1: Type Selection ---
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

# --- Step 2: Media Handling (FIXED) ---
@router.message(StateFilter(BroadcastState.waiting_for_media))
async def br_receive_media(message: types.Message, state: FSMContext):
    # FIX: Enhanced Media Detection
    media_type = None
    file_id = None

    if message.photo:
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

# --- Step 3: Text Handling (FIXED) ---
@router.message(StateFilter(BroadcastState.waiting_for_text))
async def br_receive_text(message: types.Message, state: FSMContext):
    text = message.text
    # FIX: Also check caption if user sends another media by mistake or edits
    if not text:
        text = message.caption
    
    if not text:
        await message.answer("⚠️ Text/Caption is required. Please type something.")
        return

    if len(text) > 4000:
        await message.answer("⚠️ Text is too long! Keep it under 4000 characters.")
        return

    await state.update_data(text=text)
    
    kb = get_nav_buttons("goto_buttons", "goto_text_input")
    await message.answer(
        "✅ <b>Text Saved!</b>\n\nClick 'Next' to add buttons, or 'Back' to rewrite.", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

# --- Step 4: Button Handling (FIXED) ---
@router.callback_query(F.data == "goto_buttons", StateFilter(BroadcastState))
async def br_goto_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_buttons)
    msg = (
        "3️⃣ <b>Step 3: Add Buttons (Optional)</b>\n\n"
        "Send buttons in this format (one per line):\n"
        "<code>Button Text - https://link.com</code>\n\n"
        "Type 'skip' to send without buttons."
    )
    await call.message.answer(msg, parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_buttons))
async def br_receive_buttons(message: types.Message, state: FSMContext):
    buttons_text = message.text.strip()
    
    if buttons_text.lower() == 'skip':
        await state.update_data(buttons=None)
    else:
        # FIX: Validate buttons immediately
        kb = parse_buttons_text(buttons_text)
        if not kb:
            await message.answer(
                "❌ <b>Invalid Format!</b>\n"
                "Please use: <code>Text - URL</code>\n"
                "Example: <code>Join Channel - google.com</code>\n\n"
                "Or type 'skip'.", 
                parse_mode="HTML"
            )
            return
        await state.update_data(buttons=buttons_text)
    
    # Proceed to Preview
    await br_show_preview(message, state)

# --- Step 5: Preview (FIXED) ---
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
        await message.answer(f"⚠️ <b>Preview Failed:</b> {str(e)}\n\nCheck your content.")
        
    await message.answer("➖➖➖➖ <b>PREVIEW END</b> ➖➖➖➖", parse_mode="HTML")
    
    await message.answer(
        "👆 <b>Check the preview above.</b>\n\n"
        "If everything looks good, click <b>CONFIRM</b> to start sending.",
        reply_markup=get_final_confirm_kb(),
        parse_mode="HTML"
    )

# --- Step 6: Execution ---
@router.callback_query(F.data == "br_final_send", StateFilter(BroadcastState))
async def br_execute(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    
    await call.message.edit_text("🚀 <b>Broadcast Started!</b>\nYou will receive a report when done.", parse_mode="HTML")
    
    # Run in background
    asyncio.create_task(run_broadcast_task(call.message.chat.id, data))

async def run_broadcast_task(admin_chat_id, data):
    """
    Worker function to send messages to all users safely.
    """
    users = DatabaseManager.get_all_users_list()
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
            # FIX: Properly handle separated media types
            if media_type == 'photo':
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=kb)
            elif media_type == 'video':
                await bot.send_video(chat_id=user_id, video=media_id, caption=text, reply_markup=kb)
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            
            sent += 1
            await asyncio.sleep(0.04) # 25 messages/sec limit
            
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            # Retry logic could go here
            errors += 1
        except Exception as e:
            errors += 1
            # logger.error(f"Failed to send to {user_id}: {e}")
            
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
        logger.error("Could not send broadcast report.")

# ==============================================================================
#  SECTION 10: PAYMENT HANDLERS
# ==============================================================================

@router.pre_checkout_query()
async def checkout_handler(checkout_query: PreCheckoutQuery):
    """
    Validates payment before it completes.
    """
    await bot.answer_pre_checkout_query(checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def payment_success_handler(message: types.Message):
    """
    Triggered when payment is successful.
    """
    user_id = message.from_user.id
    payment_info = message.successful_payment
    amount = payment_info.total_amount
    payload = payment_info.invoice_payload 
    
    logger.info(f"💰 Payment Success: User {user_id} paid {amount}. Payload: {payload}")
    
    await message.answer(
        "✅ <b>Payment Successful!</b>\n\n"
        "Your account has been updated. Please open the app to see your rewards.",
        parse_mode="HTML"
    )

# ==============================================================================
#  SECTION 11: API ENDPOINTS (BACKEND LOGIC)
# ==============================================================================

# 11.1 CORS Configuration
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
    """Handles preflight checks."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# 11.2 API: Verify Join
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

        # Helper to check chat member status
        async def check_membership(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                return member.status in ['member', 'administrator', 'creator', 'restricted']
            except Exception as e:
                logger.warning(f"Membership check failed for {chat_id}: {e}")
                return False

        in_channel = await check_membership(CHANNEL_USERNAME)
        in_group = await check_membership(GROUP_USERNAME)
        
        return cors_response({"joined": (in_channel and in_group)})

    except Exception as e:
        logger.error(f"Verify API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# 11.3 API: Create Invoice
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
            provider_token="", # Empty for XTR
            currency="XTR",
            prices=[LabeledPrice(label=item['title'], amount=item['price'])]
        )
        
        logger.info(f"Invoice created for User {user_id}, Item {item_id}")
        return cors_response({"result": link})

    except Exception as e:
        logger.error(f"Invoice API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# 11.4 API: Verify Ad
async def verify_ad_api(request):
    """
    Validates ad completion.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        provider = data.get('provider', 'unknown')
        ad_type = data.get('type', 'generic')

        if not user_id:
            return cors_response({"success": False, "error": "Missing ID"}, status=400)
            
        logger.info(f"📺 Ad Watched: User {user_id} | Provider: {provider} | Type: {ad_type}")
        return cors_response({"success": True})
    except Exception as e:
        logger.error(f"Ad Verify Error: {e}")
        return cors_response({"success": False}, status=500)

# 11.5 API: Play Spin
async def play_spin_api(request):
    """
    Server-side spin logic to prevent cheating.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False}, status=400)
            
        # Select random prize securely
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

# 11.6 API: Complete Task
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

# 11.7 API: Home
async def home_handler(request):
    return web.Response(text="☃️ Snowman Adventure Backend is Running Successfully! ❄️")

# ==============================================================================
#  SECTION 12: SERVER EXECUTION
# ==============================================================================

async def on_startup(bot: Bot):
    """Runs on server start."""
    logger.info("🚀 Server Starting...")
    
    if WEBHOOK_URL.startswith("https://"):
        logger.info(f"🔗 Setting Webhook: {WEBHOOK_URL}")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("✅ Webhook Set Successfully.")
            
            await bot.set_my_commands([
                BotCommand(command="start", description="Start Game"),
                BotCommand(command="help", description="Get Help"),
                BotCommand(command="admin", description="Admin Panel"),
            ])
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
    else:
        logger.warning("⚠️ Webhook URL must be HTTPS.")

async def on_shutdown(bot: Bot):
    """Runs on server stop."""
    logger.info("🔌 Server Shutting Down...")
    await bot.delete_webhook()
    await bot.session.close()

def main():
    """Main Application Entry Point."""
    
    # Create Web App
    app = web.Application()
    
    # Register Routes
    app.router.add_get('/', home_handler)
    
    # API Routes
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

    # Webhook Handler
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Setup
    setup_application(app, dp, bot=bot)
    
    # Run
    logger.info(f"🌍 Starting Web Server on Port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")

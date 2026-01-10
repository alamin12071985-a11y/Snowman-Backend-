import os
import sys
import logging
import asyncio
import json
import random
import time
import shutil
import hashlib
import hmac
from datetime import datetime
from typing import Dict, List, Union, Optional

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
    BotCommand,
    ChatMemberUpdated
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
#  SECTION 1: SYSTEM CONFIGURATION & LOGGING
# ==============================================================================

# 1.1 Logging Configuration
# Setting up a robust logging format to track every event in the system.
# This helps in debugging production issues effectively.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - [%(name)s] - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("SnowmanBackendCore")

# 1.2 Environment Variable Loading
# These variables must be present in the deployment environment (Render/Heroku/VPS).
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# 1.3 Admin & Community Settings
# Hardcoded IDs for administration and channel verification.
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# 1.4 Security & Validation
if not BOT_TOKEN:
    logger.critical("❌ FATAL ERROR: 'BOT_TOKEN' environment variable is missing!")
    sys.exit(1)

if not APP_URL:
    logger.critical("❌ FATAL ERROR: 'APP_URL' environment variable is missing!")
    sys.exit(1)

# 1.5 Webhook Path Construction
# Ensuring the URL is correctly formatted to avoid double slashes.
APP_URL = str(APP_URL).rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

logger.info("⚙️ System Configuration Loaded Successfully.")
logger.info(f"🔗 Webhook URL Configured: {WEBHOOK_URL}")

# ==============================================================================
#  SECTION 2: GAME LOGIC & CONFIGURATION CONSTANTS
# ==============================================================================

class GameConfig:
    """
    Central configuration for game mechanics, shop items, and rewards.
    This class manages all static data to keep the main logic clean.
    """
    
    # 2.1 Telegram Stars Shop Items
    # Structure: Item ID -> {Price, Amount, Title, Description}
    SHOP_ITEMS = {
        # --- Coin Packs ---
        'coin_starter': {
            'price': 10, 
            'amount': 5000, 
            'title': 'Starter Pack (5k)', 
            'desc': 'Get a quick start with 5,000 Coins!',
            'type': 'coin'
        },
        'coin_small': {
            'price': 50, 
            'amount': 30000, 
            'title': 'Small Pack (30k)', 
            'desc': 'A nice boost of 30,000 Coins.',
            'type': 'coin'
        },
        'coin_medium': {
            'price': 100, 
            'amount': 70000, 
            'title': 'Medium Pack (70k)', 
            'desc': 'Serious players need this. 70,000 Coins.',
            'type': 'coin'
        },
        'coin_large': {
            'price': 250, 
            'amount': 200000, 
            'title': 'Large Pack (200k)', 
            'desc': 'Huge amount! 200,000 Coins.',
            'type': 'coin'
        },
        'coin_mega': {
            'price': 500, 
            'amount': 500000, 
            'title': 'Mega Pack (500k)', 
            'desc': 'Ultimate power! 500,000 Coins.',
            'type': 'coin'
        },
        
        # --- Boosters ---
        'booster_3d': {
            'price': 20, 
            'amount': 3 * 24 * 3600, # Seconds
            'title': '3 Days Booster (x2)', 
            'desc': 'Double your tapping power for 3 days.',
            'type': 'booster'
        },
        'booster_15d': {
            'price': 70, 
            'amount': 15 * 24 * 3600, 
            'title': '15 Days Booster (x2)', 
            'desc': 'Double your tapping power for 15 days.',
            'type': 'booster'
        },
        'booster_30d': {
            'price': 120, 
            'amount': 30 * 24 * 3600, 
            'title': '30 Days Booster (x2)', 
            'desc': 'Double your tapping power for 30 days.',
            'type': 'booster'
        },
        
        # --- Auto Tap ---
        'autotap_1d': {
            'price': 20, 
            'amount': 1 * 24 * 3600, 
            'title': 'Auto Tap Bot (1 Day)', 
            'desc': 'Let the bot tap for you for 24 hours.',
            'type': 'autotap'
        },
        'autotap_7d': {
            'price': 80, 
            'amount': 7 * 24 * 3600, 
            'title': 'Auto Tap Bot (7 Days)', 
            'desc': 'Automated income for a whole week.',
            'type': 'autotap'
        },
        'autotap_30d': {
            'price': 200, 
            'amount': 30 * 24 * 3600, 
            'title': 'Auto Tap Bot (30 Days)', 
            'desc': 'Maximum automation for a month.',
            'type': 'autotap'
        },
    }

    # 2.2 Spin Game Prizes (TON Amounts)
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

    # 2.3 Gameplay Constants
    INITIAL_BALANCE = 500
    REFERRAL_BONUS = 5000
    MAX_DAILY_ADS = 50
    TASK_REWARD_DELAY = 5 # Seconds to wait before validating
    
    @staticmethod
    def get_item(item_id: str) -> dict:
        """Retrieves an item configuration safely."""
        return GameConfig.SHOP_ITEMS.get(item_id)

# ==============================================================================
#  SECTION 3: ROBUST DATABASE SYSTEM (JSON FILE BASED)
# ==============================================================================

DB_FILE = "users.json"
BACKUP_DIR = "backups"

class DatabaseManager:
    """
    Advanced JSON Database Manager.
    Handles User Data, Referrals, Analytics, and Backups.
    Structure:
    {
        "user_id_string": {
            "username": "str",
            "first_name": "str",
            "balance": float,
            "tonBalance": float,
            "level": int,
            "currentLevelScore": float,
            "tapCount": int,
            "referrals": [list_of_ids],
            "referredBy": "id" or None,
            "joined_date": timestamp,
            "last_active": timestamp
        }
    }
    """
    
    @staticmethod
    def _initialize_db():
        """Creates the DB file and backup directory if they don't exist."""
        if not os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "w", encoding='utf-8') as f:
                    json.dump({}, f)
                logger.info(f"📁 Database file '{DB_FILE}' created successfully.")
            except Exception as e:
                logger.error(f"❌ Failed to create DB file: {e}")
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    @staticmethod
    def load_db() -> Dict:
        """Reads the full database dictionary with error handling."""
        DatabaseManager._initialize_db()
        try:
            with open(DB_FILE, "r", encoding='utf-8') as f:
                content = f.read()
                if not content:
                    return {}
                data = json.loads(content)
                
                # Legacy Support: If DB was a list, convert to dict
                if isinstance(data, list):
                    logger.warning("⚠️ Legacy DB format detected. Migrating to Dictionary...")
                    new_data = {str(uid): DatabaseManager._get_default_schema() for uid in data}
                    DatabaseManager.save_full_db(new_data)
                    return new_data
                    
                return data
        except json.JSONDecodeError:
            logger.error("⚠️ JSON Decode Error. Returning empty DB.")
            return {}
        except Exception as e:
            logger.error(f"⚠️ Database Load Error: {e}")
            return {}

    @staticmethod
    def save_full_db(data: Dict):
        """Writes the full dictionary to file atomically."""
        try:
            temp_file = f"{DB_FILE}.tmp"
            with open(temp_file, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic replacement
            os.replace(temp_file, DB_FILE)
        except Exception as e:
            logger.error(f"❌ Failed to save DB: {e}")

    @staticmethod
    def create_backup():
        """Creates a timestamped backup of the database."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(BACKUP_DIR, f"users_{timestamp}.json")
            shutil.copy2(DB_FILE, backup_path)
            logger.info(f"📦 Database backup created: {backup_path}")
            
            # Cleanup old backups (keep last 5)
            backups = sorted(os.listdir(BACKUP_DIR))
            if len(backups) > 5:
                os.remove(os.path.join(BACKUP_DIR, backups[0]))
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")

    @staticmethod
    def _get_default_schema() -> Dict:
        """Returns the default user object structure."""
        return {
            "balance": GameConfig.INITIAL_BALANCE,
            "tonBalance": 0.0,
            "level": 1,
            "currentLevelScore": 0,
            "tapCount": 0,
            "referrals": [],
            "referredBy": None,
            "joined_date": time.time(),
            "last_active": time.time(),
            "is_blocked": False
        }

    @staticmethod
    def get_user(user_id: Union[int, str]) -> Optional[Dict]:
        """Gets data for a specific user."""
        db = DatabaseManager.load_db()
        return db.get(str(user_id))

    @staticmethod
    def register_user(user_id: int, username: str, first_name: str, referrer_id: Optional[str] = None):
        """Registers a new user and handles referral bonus."""
        db = DatabaseManager.load_db()
        uid_str = str(user_id)
        
        if uid_str in db:
            # User exists, just update info
            db[uid_str]["username"] = username
            db[uid_str]["first_name"] = first_name
            db[uid_str]["last_active"] = time.time()
            DatabaseManager.save_full_db(db)
            return False # Not a new user
        
        # New User
        new_user = DatabaseManager._get_default_schema()
        new_user["username"] = username
        new_user["first_name"] = first_name
        
        # Referral Logic
        if referrer_id and referrer_id != uid_str and referrer_id in db:
            new_user["referredBy"] = referrer_id
            # Bonus to Referrer
            db[referrer_id]["balance"] = db[referrer_id].get("balance", 0) + GameConfig.REFERRAL_BONUS
            if "referrals" not in db[referrer_id]:
                db[referrer_id]["referrals"] = []
            db[referrer_id]["referrals"].append(uid_str)
            logger.info(f"🤝 Referral: {uid_str} joined via {referrer_id}")
            
            # Bonus to New User
            new_user["balance"] += GameConfig.REFERRAL_BONUS

        db[uid_str] = new_user
        DatabaseManager.save_full_db(db)
        logger.info(f"🆕 New User Registered: {username} ({user_id})")
        return True

    @staticmethod
    def update_user_progress(user_id: int, data: dict):
        """Updates user game progress from frontend sync."""
        db = DatabaseManager.load_db()
        uid_str = str(user_id)
        
        if uid_str not in db:
            return False
        
        user = db[uid_str]
        
        # Validations could go here (Anti-Cheat)
        # e.g., if data['balance'] > user['balance'] + max_possible_gain: flag_user()
        
        if 'balance' in data: user['balance'] = data['balance']
        if 'tonBalance' in data: user['tonBalance'] = data['tonBalance']
        if 'level' in data: user['level'] = data['level']
        if 'currentLevelScore' in data: user['currentLevelScore'] = data['currentLevelScore']
        if 'tapCount' in data: user['tapCount'] = data['tapCount']
        
        user['last_active'] = time.time()
        
        db[uid_str] = user
        DatabaseManager.save_full_db(db)
        return True

    @staticmethod
    def get_all_user_ids() -> List[int]:
        """Returns a list of all user IDs for broadcasting."""
        db = DatabaseManager.load_db()
        return [int(uid) for uid in db.keys() if not db[uid].get('is_blocked', False)]

    @staticmethod
    def get_stats() -> Dict:
        """Calculates system-wide statistics."""
        db = DatabaseManager.load_db()
        total_users = len(db)
        total_balance = sum(u.get('balance', 0) for u in db.values())
        total_ton = sum(u.get('tonBalance', 0) for u in db.values())
        
        # Daily Active Users (last 24h)
        one_day_ago = time.time() - 86400
        dau = sum(1 for u in db.values() if u.get('last_active', 0) > one_day_ago)
        
        return {
            "total_users": total_users,
            "total_balance": total_balance,
            "total_ton": total_ton,
            "dau": dau
        }

# Initialize Database
DatabaseManager._initialize_db()

# ==============================================================================
#  SECTION 4: BOT SETUP, MIDDLEWARE & STATES
# ==============================================================================

# 4.1 FSM Storage
storage = MemoryStorage()

# 4.2 Bot & Dispatcher Initialization
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# 4.3 State Definitions
class BroadcastState(StatesGroup):
    """FSM States for the Admin Broadcast Wizard."""
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()
    confirm_send = State()

class MaintenanceState(StatesGroup):
    """FSM State for Maintenance Mode."""
    active = State()

# 4.4 Global Maintenance Mode Flag
MAINTENANCE_MODE = False

# ==============================================================================
#  SECTION 5: KEYBOARDS & UI HELPERS
# ==============================================================================

def get_main_keyboard():
    """Generates the primary menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❄️ Play Snowman Adventure ☃️", 
                url=f"https://t.me/{BOT_TOKEN.split(':')[0]}/app"
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 Announcement Channel", 
                url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Community Group", 
                url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}"
            )
        ],
        [
            InlineKeyboardButton(text="🏆 Leaderboard", callback_data="show_leaderboard"),
            InlineKeyboardButton(text="❓ Help", callback_data="show_help")
        ]
    ])

def get_admin_keyboard():
    """Generates the admin control panel keyboard."""
    status = "🔴 ON" if MAINTENANCE_MODE else "🟢 OFF"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 New Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 View Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💾 Force Backup", callback_data="admin_backup")],
        [InlineKeyboardButton(text=f"🔧 Maintenance: {status}", callback_data="admin_toggle_maint")]
    ])

def get_broadcast_type_kb():
    """Keyboard for selecting broadcast message type."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Photo + Text", callback_data="br_start_media_photo")],
        [InlineKeyboardButton(text="📹 Video + Text", callback_data="br_start_media_video")],
        [InlineKeyboardButton(text="📝 Text Message Only", callback_data="br_start_text")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="br_cancel")]
    ])

def get_nav_buttons(next_cb: str, back_cb: str):
    """Reusable navigation buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Next Step", callback_data=next_cb)],
        [InlineKeyboardButton(text="🔙 Go Back", callback_data=back_cb)]
    ])

def get_final_confirm_kb():
    """Confirmation keyboard for dangerous actions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 CONFIRM & SEND NOW", callback_data="br_final_send")],
        [InlineKeyboardButton(text="❌ CANCEL EVERYTHING", callback_data="br_cancel")]
    ])

def parse_buttons_text(text: str) -> Optional[InlineKeyboardMarkup]:
    """
    Parses a string into an Inline Keyboard.
    Format: "Button Text - URL"
    """
    if not text or text.lower() == 'skip': 
        return None
    try:
        kb_rows = []
        for line in text.split('\n'):
            line = line.strip()
            if '-' in line:
                parts = line.split('-', 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                if btn_text and btn_url.startswith('http'):
                    kb_rows.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        return InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    except Exception as e:
        logger.error(f"Button Parsing Failed: {e}")
        return None

# ==============================================================================
#  SECTION 6: BOT COMMAND HANDLERS
# ==============================================================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    """
    Handles the /start command.
    Registers the user and processes referrals.
    """
    if MAINTENANCE_MODE and message.from_user.id != ADMIN_ID:
        await message.answer("🚧 **System Under Maintenance**\nPlease try again later.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    first_name = message.from_user.first_name or "User"
    referrer_id = command.args

    # Register User
    is_new = DatabaseManager.register_user(user_id, username, first_name, referrer_id)
    
    welcome_text = (
        f"❄️☃️ <b>Welcome to Snowman Adventure, {first_name}!</b> ☃️❄️\n\n"
        "Embark on a frosty journey to build the ultimate snowman empire!\n\n"
        "🎮 <b>How to Play:</b>\n"
        "• Tap to earn Snow Coins\n"
        "• Level up your Snowman\n"
        "• Invite friends for massive bonuses\n"
        "• Withdraw real crypto rewards!\n\n"
        "👇 <b>Start your adventure now!</b>"
    )
    
    if is_new and referrer_id:
        welcome_text += f"\n\n🎁 <i>You received a {GameConfig.REFERRAL_BONUS} coin signup bonus!</i>"

    await message.answer(
        text=welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("help"))
@router.callback_query(F.data == "show_help")
async def cmd_help(event: Union[types.Message, CallbackQuery]):
    """Provides help instructions."""
    text = (
        "<b>🆘 Snowman Adventure Help Center</b>\n\n"
        "1. <b>Play Game:</b> Click the main menu button to open the web app.\n"
        "2. <b>Earnings:</b> Tap the snowman and complete tasks.\n"
        "3. <b>Withdraw:</b> Go to the 'Wallet' tab in the app.\n"
        "4. <b>Issues?</b> Join our Community Group for support.\n\n"
        f"Channel: {CHANNEL_USERNAME}\n"
        f"Group: {GROUP_USERNAME}"
    )
    
    if isinstance(event, types.Message):
        await event.answer(text, parse_mode="HTML")
    else:
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()

@router.callback_query(F.data == "show_leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    """Displays a mini leaderboard in the bot chat."""
    db = DatabaseManager.load_db()
    
    # Sort users by balance
    sorted_users = sorted(
        db.items(), 
        key=lambda item: item[1].get('balance', 0), 
        reverse=True
    )
    
    top_10 = sorted_users[:10]
    text = "🏆 <b>TOP 10 SNOWMEN</b> 🏆\n\n"
    
    for idx, (uid, data) in enumerate(top_10, 1):
        name = data.get('username', 'Unknown')
        bal = data.get('balance', 0)
        
        # Medals for top 3
        if idx == 1: icon = "🥇"
        elif idx == 2: icon = "🥈"
        elif idx == 3: icon = "🥉"
        else: icon = f"#{idx}"
        
        text += f"{icon} <b>{name}</b>: {int(bal):,} coins\n"
        
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# ==============================================================================
#  SECTION 7: ADMIN CONTROL PANEL & BROADCAST SYSTEM
# ==============================================================================

@router.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    """Entry point for the Admin Panel."""
    if message.from_user.id != ADMIN_ID:
        return # Silent ignore
    
    stats = DatabaseManager.get_stats()
    
    text = (
        "🔐 <b>ADMINISTRATION PANEL</b>\n"
        "---------------------------\n"
        f"👥 Total Users: <code>{stats['total_users']}</code>\n"
        f"⚡ Active Today: <code>{stats['dau']}</code>\n"
        f"💰 Total Coins: <code>{int(stats['total_balance']):,}</code>\n"
        f"💎 Total TON: <code>{stats['total_ton']:.4f}</code>\n"
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "admin_stats")
async def cb_refresh_stats(call: CallbackQuery):
    """Refreshes the admin stats view."""
    if call.from_user.id != ADMIN_ID: return
    
    stats = DatabaseManager.get_stats()
    text = (
        "🔐 <b>ADMINISTRATION PANEL (Refreshed)</b>\n"
        "---------------------------\n"
        f"👥 Total Users: <code>{stats['total_users']}</code>\n"
        f"⚡ Active Today: <code>{stats['dau']}</code>\n"
        f"💰 Total Coins: <code>{int(stats['total_balance']):,}</code>\n"
        f"💎 Total TON: <code>{stats['total_ton']:.4f}</code>\n"
        f"🕒 Server Time: {datetime.now().strftime('%H:%M:%S')}"
    )
    try:
        await call.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    except TelegramBadRequest:
        await call.answer("Already updated!", show_alert=True)

@router.callback_query(F.data == "admin_backup")
async def cb_force_backup(call: CallbackQuery):
    """Triggers an immediate database backup."""
    if call.from_user.id != ADMIN_ID: return
    DatabaseManager.create_backup()
    await call.answer("✅ Backup Created Successfully!", show_alert=True)

@router.callback_query(F.data == "admin_toggle_maint")
async def cb_toggle_maintenance(call: CallbackQuery):
    """Toggles maintenance mode."""
    global MAINTENANCE_MODE
    if call.from_user.id != ADMIN_ID: return
    
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    status = "ENABLED" if MAINTENANCE_MODE else "DISABLED"
    
    await call.answer(f"Maintenance Mode {status}", show_alert=True)
    
    # Update keyboard
    await call.message.edit_reply_markup(reply_markup=get_admin_keyboard())

# --- Broadcast Wizard Implementation ---

@router.callback_query(F.data == "admin_broadcast")
async def br_start(call: CallbackQuery, state: FSMContext):
    """Step 0: Start Broadcast"""
    if call.from_user.id != ADMIN_ID: return
    await state.clear()
    await call.message.edit_text(
        "📢 <b>Broadcast Wizard</b>\n\nSelect message type:",
        reply_markup=get_broadcast_type_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
@router.callback_query(F.data == "br_cancel", StateFilter(None))
async def br_cancel_handler(call: CallbackQuery, state: FSMContext):
    """Cancel Action"""
    await state.clear()
    await call.message.edit_text("❌ Operation Cancelled.", reply_markup=None)

@router.callback_query(F.data.startswith("br_start_"), StateFilter(None))
async def br_select_type(call: CallbackQuery, state: FSMContext):
    """Step 1: Type Selection"""
    m_type = call.data.replace("br_start_", "")
    
    if m_type == "text":
        await state.update_data(media_type="text", media_id=None)
        await state.set_state(BroadcastState.waiting_for_text)
        await call.message.edit_text("📝 <b>Send the message text now:</b>", parse_mode="HTML")
    else:
        # Photo or Video
        clean_type = m_type.replace("media_", "") # photo or video
        await state.update_data(media_type=clean_type)
        await state.set_state(BroadcastState.waiting_for_media)
        await call.message.edit_text(f"📤 <b>Please send the {clean_type.upper()} now:</b>", parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_media))
async def br_receive_media(message: types.Message, state: FSMContext):
    """Step 2: Receive Media"""
    data = await state.get_data()
    expected_type = data.get("media_type")
    
    file_id = None
    if expected_type == "photo" and message.photo:
        file_id = message.photo[-1].file_id
    elif expected_type == "video" and message.video:
        file_id = message.video.file_id
    
    if not file_id:
        await message.answer(f"⚠️ Invalid media! Please send a <b>{expected_type}</b>.", parse_mode="HTML")
        return

    await state.update_data(media_id=file_id)
    await state.set_state(BroadcastState.waiting_for_text)
    
    kb = get_nav_buttons("br_skip_caption", "br_cancel")
    await message.answer(
        "✅ <b>Media Saved!</b>\n\nNow send the <b>Caption/Text</b>.\nOr type /skip to send without text.",
        parse_mode="HTML"
    )

@router.message(StateFilter(BroadcastState.waiting_for_text))
async def br_receive_text(message: types.Message, state: FSMContext):
    """Step 3: Receive Text"""
    text = message.text
    if text == "/skip": text = ""
    
    await state.update_data(text=text)
    await state.set_state(BroadcastState.waiting_for_buttons)
    
    msg = (
        "✅ <b>Text Saved!</b>\n\n"
        "Now send <b>Buttons</b> (Optional).\n"
        "Format per line: <code>Text - URL</code>\n\n"
        "Type <b>skip</b> to proceed without buttons."
    )
    await message.answer(msg, parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_buttons))
async def br_receive_buttons(message: types.Message, state: FSMContext):
    """Step 4: Receive Buttons & Preview"""
    text = message.text
    
    if text.lower() == "skip":
        buttons = None
    else:
        kb = parse_buttons_text(text)
        if not kb:
            await message.answer("❌ Invalid Format. Try again or type 'skip'.")
            return
        buttons = text

    await state.update_data(buttons=buttons)
    await br_show_preview(message, state)

async def br_show_preview(message: types.Message, state: FSMContext):
    """Step 5: Preview"""
    data = await state.get_data()
    m_type = data.get("media_type")
    m_id = data.get("media_id")
    txt = data.get("text")
    btns = data.get("buttons")
    
    kb = parse_buttons_text(btns)
    
    await message.answer("➖➖➖➖ <b>PREVIEW START</b> ➖➖➖➖", parse_mode="HTML")
    
    try:
        if m_type == "text":
            await message.answer(txt, reply_markup=kb, parse_mode="HTML")
        elif m_type == "photo":
            await message.answer_photo(m_id, caption=txt, reply_markup=kb, parse_mode="HTML")
        elif m_type == "video":
            await message.answer_video(m_id, caption=txt, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"⚠️ Preview Error: {e}")
        
    await message.answer("➖➖➖➖ <b>PREVIEW END</b> ➖➖➖➖", parse_mode="HTML")
    
    await message.answer(
        "🚀 <b>Ready to Launch?</b>\nConfirming will send this to ALL users.",
        reply_markup=get_final_confirm_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastState.confirm_send)

@router.callback_query(F.data == "br_final_send", StateFilter(BroadcastState.confirm_send))
async def br_execute_broadcast(call: CallbackQuery, state: FSMContext):
    """Step 6: Execute Background Task"""
    data = await state.get_data()
    await state.clear()
    
    await call.message.edit_text("🚀 <b>Broadcast Initiated!</b>\nRunning in background...", parse_mode="HTML")
    
    # Run the heavy lifting in a separate async task
    asyncio.create_task(run_broadcast_task(call.message.chat.id, data))

async def run_broadcast_task(admin_chat_id: int, data: dict):
    """
    Background worker for broadcasting messages.
    Includes rate limiting and error tracking.
    """
    users = DatabaseManager.get_all_user_ids()
    total = len(users)
    sent = 0
    blocked = 0
    errors = 0
    start_time = time.time()
    
    m_type = data.get("media_type")
    m_id = data.get("media_id")
    text = data.get("text")
    kb = parse_buttons_text(data.get("buttons"))
    
    # Progress update interval (every 100 users)
    update_interval = 100
    
    for index, uid in enumerate(users):
        try:
            if m_type == "text":
                await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            elif m_type == "photo":
                await bot.send_photo(uid, m_id, caption=text, reply_markup=kb, parse_mode="HTML")
            elif m_type == "video":
                await bot.send_video(uid, m_id, caption=text, reply_markup=kb, parse_mode="HTML")
            
            sent += 1
            await asyncio.sleep(0.04) # 25 msg/sec limit (Safe side)
            
        except TelegramForbiddenError:
            blocked += 1
            # Mark user as blocked in DB to skip next time? Optional.
        except TelegramRetryAfter as e:
            logger.warning(f"Rate Limited! Sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            errors += 1
        except Exception as e:
            logger.error(f"Broadcast Fail for {uid}: {e}")
            errors += 1
            
        # Optional: Send progress report to admin periodically
        if (index + 1) % update_interval == 0:
            logger.info(f"Broadcast Progress: {index + 1}/{total}")

    duration = round(time.time() - start_time, 2)
    
    final_report = (
        "✅ <b>Broadcast Finished!</b>\n"
        "---------------------------\n"
        f"🎯 Target Users: {total}\n"
        f"📨 Sent: {sent}\n"
        f"🚫 Blocked: {blocked}\n"
        f"⚠️ Errors: {errors}\n"
        f"⏱️ Time Taken: {duration}s"
    )
    
    try:
        await bot.send_message(admin_chat_id, final_report, parse_mode="HTML")
    except:
        logger.error("Failed to send broadcast report.")

# ==============================================================================
#  SECTION 8: PAYMENT HANDLERS (TELEGRAM STARS)
# ==============================================================================

@router.pre_checkout_query()
async def on_pre_checkout(checkout_query: PreCheckoutQuery):
    """
    Validates the transaction before payment.
    Always returns True for digital goods in this context.
    """
    await bot.answer_pre_checkout_query(checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    """
    Handles successful payment payload.
    Updates the user's balance or applies boosters.
    """
    user_id = message.from_user.id
    payment_info = message.successful_payment
    payload = payment_info.invoice_payload # Format: "user_id_item_id"
    
    try:
        # Parse payload
        _, item_id = payload.split("_", 1)
        item = GameConfig.get_item(item_id)
        
        if not item:
            await message.answer("⚠️ Item Error: Please contact support.")
            return

        db = DatabaseManager.load_db()
        str_uid = str(user_id)
        
        if str_uid in db:
            user_data = db[str_uid]
            item_type = item.get('type')
            amount = item.get('amount')
            
            success_msg = ""
            
            if item_type == 'coin':
                user_data['balance'] += amount
                success_msg = f"✅ Added <b>{amount:,} Coins</b> to your balance!"
                
            elif item_type == 'booster':
                # Store end timestamp
                current_end = user_data.get('booster_end', time.time())
                if current_end < time.time(): current_end = time.time()
                user_data['booster_end'] = current_end + amount
                success_msg = f"⚡ <b>Booster Activated!</b> (x2 Tapping)"
                
            elif item_type == 'autotap':
                current_end = user_data.get('autotap_end', time.time())
                if current_end < time.time(): current_end = time.time()
                user_data['autotap_end'] = current_end + amount
                success_msg = f"🤖 <b>Auto-Tap Bot Activated!</b>"
            
            DatabaseManager.save_full_db(db)
            
            await message.answer(success_msg, parse_mode="HTML")
            logger.info(f"💰 Payment Processed: {user_id} bought {item_id}")
            
    except Exception as e:
        logger.error(f"Payment Processing Error: {e}")
        await message.answer("⚠️ An error occurred processing your reward. Admin notified.")

# ==============================================================================
#  SECTION 9: API BACKEND (AIOHTTP ROUTES)
# ==============================================================================

# 9.1 CORS & Response Helpers
def cors_response(data: Dict, status: int = 200) -> web.Response:
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
    """Handles CORS preflight requests."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# 9.2 API: User Data Synchronization
async def api_sync_user_data(request):
    """
    Endpoint: /sync-user-data
    Method: POST
    Description: Receives game progress from frontend and saves to DB.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False, "error": "Missing User ID"}, 400)
        
        # Validating numeric types to prevent injection
        clean_data = {}
        if 'balance' in data: 
            clean_data['balance'] = float(data['balance'])
        if 'currentLevelScore' in data: 
            clean_data['currentLevelScore'] = float(data['currentLevelScore'])
        if 'level' in data: 
            clean_data['level'] = int(data['level'])
        if 'tapCount' in data: 
            clean_data['tapCount'] = int(data['tapCount'])
        if 'tonBalance' in data:
            clean_data['tonBalance'] = float(data['tonBalance'])
            
        success = DatabaseManager.update_user_progress(user_id, clean_data)
        
        if success:
            return cors_response({"success": True})
        else:
            return cors_response({"success": False, "error": "User not found"}, 404)
            
    except Exception as e:
        logger.error(f"Sync API Error: {e}")
        return cors_response({"success": False, "error": str(e)}, 500)

# 9.3 API: Verify Membership
async def api_verify_join(request):
    """
    Endpoint: /verify_join
    Method: POST
    Description: Checks if user joined required channels.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "No ID"}, 400)

        # Helper to check membership
        async def is_member(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                return member.status in ['member', 'administrator', 'creator', 'restricted']
            except Exception as e:
                logger.warning(f"Bot cannot check member in {chat_id}: {e}")
                return False # Fail safe

        in_channel = await is_member(CHANNEL_USERNAME)
        in_group = await is_member(GROUP_USERNAME)
        
        is_joined = in_channel and in_group
        
        # Log activity if verified
        if is_joined:
            DatabaseManager.update_user_progress(user_id, {}) # Just updates last_active
            
        return cors_response({"joined": is_joined})

    except Exception as e:
        logger.error(f"Verify API Error: {e}")
        return cors_response({"error": str(e)}, 500)

# 9.4 API: Create Invoice
async def api_create_invoice(request):
    """
    Endpoint: /create_invoice
    Method: POST
    Description: Generates Telegram Star invoice link.
    """
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing params"}, 400)
        
        item = GameConfig.get_item(item_id)
        if not item:
            return cors_response({"error": "Invalid Item"}, 404)

        link = await bot.create_invoice_link(
            title=item['title'],
            description=item['desc'],
            payload=f"{user_id}_{item_id}",
            provider_token="", # Empty for Stars
            currency="XTR",
            prices=[LabeledPrice(label=item['title'], amount=item['price'])]
        )
        
        return cors_response({"result": link})

    except Exception as e:
        logger.error(f"Invoice API Error: {e}")
        return cors_response({"error": str(e)}, 500)

# 9.5 API: Verify Ad Watch
async def api_verify_ad(request):
    """
    Endpoint: /verify-ad
    Method: POST
    Description: Logs ad watch and could implement reward logic server-side.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False}, 400)
            
        # In a real app, verify server-side signatures here.
        logger.info(f"📺 Ad Watched by {user_id}")
        
        # Optionally update "dailyAdCount" in DB here if we trusted the client 100%
        # For now, we trust the sync endpoint to handle the incremented value.
        
        return cors_response({"success": True})
    except Exception as e:
        return cors_response({"success": False, "error": str(e)}, 500)

# 9.6 API: Play Spin (Server-Side Logic)
async def api_play_spin(request):
    """
    Endpoint: /play-spin
    Method: POST
    Description: Calculates spin result on server to prevent cheating.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False}, 400)
            
        # Determine prize securely
        prizes = GameConfig.SPIN_PRIZES
        index = random.randint(0, len(prizes) - 1)
        amount = prizes[index]
        
        # Log result
        logger.info(f"🎰 Spin: User {user_id} won {amount} TON")
        
        return cors_response({
            "success": True,
            "index": index,
            "amount": amount
        })
    except Exception as e:
        logger.error(f"Spin API Error: {e}")
        return cors_response({"success": False}, 500)

# 9.7 API: Complete Task
async def api_complete_task(request):
    """
    Endpoint: /complete-task
    Method: POST
    Description: Logs task completion.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        logger.info(f"✅ Task Completed: {task_id} by {user_id}")
        # Logic to save specific task state to DB could go here
        
        return cors_response({"success": True})
    except Exception as e:
        return cors_response({"success": False}, 500)

# 9.8 API: Get Referrals (Optional - if frontend needs to fetch dynamically)
async def api_get_referrals(request):
    """
    Endpoint: /get-referrals?user_id=123
    Method: GET
    """
    try:
        user_id = request.query.get('user_id')
        if not user_id: return cors_response({"error": "No ID"}, 400)
        
        user = DatabaseManager.get_user(user_id)
        if not user or 'referrals' not in user:
            return cors_response({"referrals": []})
            
        # Resolve referral IDs to Names/Balances
        ref_list = []
        db = DatabaseManager.load_db()
        for ref_id in user['referrals']:
            ref_data = db.get(ref_id)
            if ref_data:
                ref_list.append({
                    "username": ref_data.get('username', 'Unknown'),
                    "balance": ref_data.get('balance', 0),
                    "avatar": "https://alamin12071985-a11y.github.io/Snowman-Adventure/snowman.webp" # Placeholder
                })
        
        return cors_response({"referrals": ref_list})
    except Exception as e:
        return cors_response({"error": str(e)}, 500)

# 9.9 Root Health Check
async def home_handler(request):
    return web.Response(text=f"☃️ Snowman Backend Online v2.0 | {datetime.now()}")

# ==============================================================================
#  SECTION 10: APPLICATION LIFECYCLE & EXECUTION
# ==============================================================================

async def on_startup(bot: Bot):
    """Triggered when the server starts."""
    logger.info("🚀 Server Initiation Sequence Started...")
    
    if WEBHOOK_URL.startswith("https://"):
        logger.info(f"🔗 Setting Webhook to: {WEBHOOK_URL}")
        try:
            # Drop pending updates to prevent command flood on restart
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(WEBHOOK_URL)
            
            # Set Bot Commands Menu
            await bot.set_my_commands([
                BotCommand(command="start", description="☃️ Start Adventure"),
                BotCommand(command="help", description="❓ Get Help"),
                BotCommand(command="admin", description="🔒 Admin Panel")
            ])
            logger.info("✅ Webhook & Commands Configured.")
        except Exception as e:
            logger.error(f"❌ Webhook Configuration Failed: {e}")
    else:
        logger.warning("⚠️ Webhook not set: URL must be HTTPS (SSL).")

async def on_shutdown(bot: Bot):
    """Triggered when the server stops."""
    logger.info("🔌 Server Shutdown Sequence Initiated...")
    
    # Perform a final backup before dying
    DatabaseManager.create_backup()
    
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("👋 Goodbye!")

def main():
    """Main Entry Point."""
    
    # 1. Initialize Web App
    app = web.Application()
    
    # 2. Register Routes
    # Root
    app.router.add_get('/', home_handler)
    
    # API Routes
    app.router.add_post('/sync-user-data', api_sync_user_data)
    app.router.add_post('/verify_join', api_verify_join)
    app.router.add_post('/create_invoice', api_create_invoice)
    app.router.add_post('/verify-ad', api_verify_ad)
    app.router.add_post('/play-spin', api_play_spin)
    app.router.add_post('/complete-task', api_complete_task)
    app.router.add_get('/get-referrals', api_get_referrals)
    
    # CORS Preflight for all API routes
    for route in list(app.router.routes()):
        if route.method == "POST":
            app.router.add_options(route.resource.canonical, options_handler)

    # 3. Setup Aiogram Webhook Handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # 4. Attach Hooks - THIS WAS THE MISSING PART CAUSING THE ISSUES
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    setup_application(app, dp, bot=bot)
    
    # 5. Launch
    logger.info(f"🌍 Starting Web Server on 0.0.0.0:{PORT}")
    
    try:
        web.run_app(app, host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.critical(f"❌ Failed to start server: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Manually Stopped.")
    except Exception as e:
        logger.critical(f"🛑 Crash: {e}")

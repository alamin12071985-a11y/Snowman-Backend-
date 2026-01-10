--- START OF FILE main.py ---

import os
import sys
import logging
import asyncio
import json
import random
import time
import shutil
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
    BotCommand
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import (
    TelegramBadRequest, 
    TelegramForbiddenError, 
    TelegramRetryAfter
)

# ==============================================================================
#  SECTION 1: SYSTEM CONFIGURATION & LOGGING
# ==============================================================================

# 1.1 Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("SnowmanBackendCore")

# 1.2 Environment Variable Loading
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

# 1.3 Admin & Community Settings
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# 1.4 Security & Validation
if not BOT_TOKEN:
    logger.critical("❌ FATAL ERROR: 'BOT_TOKEN' is missing!")
    sys.exit(1)

if not APP_URL:
    logger.critical("❌ FATAL ERROR: 'APP_URL' is missing!")
    sys.exit(1)

# 1.5 Webhook Path Construction
# Removes trailing slash if present to avoid double slashes
APP_URL = str(APP_URL).rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

logger.info("⚙️ System Configuration Loaded.")
logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")

# ==============================================================================
#  SECTION 2: GAME CONFIGURATION
# ==============================================================================

class GameConfig:
    """Central configuration for game mechanics and shop."""
    
    SHOP_ITEMS = {
        # --- Coin Packs ---
        'coin_starter': {'price': 10, 'amount': 5000, 'title': 'Starter Pack (5k)', 'desc': 'Get a quick start!', 'type': 'coin'},
        'coin_small': {'price': 50, 'amount': 30000, 'title': 'Small Pack (30k)', 'desc': 'Nice boost.', 'type': 'coin'},
        'coin_medium': {'price': 100, 'amount': 70000, 'title': 'Medium Pack (70k)', 'desc': 'Serious players.', 'type': 'coin'},
        'coin_large': {'price': 250, 'amount': 200000, 'title': 'Large Pack (200k)', 'desc': 'Huge amount!', 'type': 'coin'},
        'coin_mega': {'price': 500, 'amount': 500000, 'title': 'Mega Pack (500k)', 'desc': 'Ultimate power!', 'type': 'coin'},
        
        # --- Boosters ---
        'booster_3d': {'price': 20, 'amount': 259200, 'title': '3 Days Booster (x2)', 'desc': 'Double tapping power.', 'type': 'booster'},
        'booster_15d': {'price': 70, 'amount': 1296000, 'title': '15 Days Booster (x2)', 'desc': 'Double tapping power.', 'type': 'booster'},
        'booster_30d': {'price': 120, 'amount': 2592000, 'title': '30 Days Booster (x2)', 'desc': 'Double tapping power.', 'type': 'booster'},
        
        # --- Auto Tap ---
        'autotap_1d': {'price': 20, 'amount': 86400, 'title': 'Auto Tap (1 Day)', 'desc': 'Bot works for 24h.', 'type': 'autotap'},
        'autotap_7d': {'price': 80, 'amount': 604800, 'title': 'Auto Tap (7 Days)', 'desc': 'Bot works for 7 days.', 'type': 'autotap'},
        'autotap_30d': {'price': 200, 'amount': 2592000, 'title': 'Auto Tap (30 Days)', 'desc': 'Bot works for 30 days.', 'type': 'autotap'},
    }

    SPIN_PRIZES = [0.00000048, 0.00000060, 0.00000080, 0.00000100, 0.00000050, 0.00000030, 0.00000020, 0.00000150]
    INITIAL_BALANCE = 500
    REFERRAL_BONUS = 5000
    
    @staticmethod
    def get_item(item_id: str) -> dict:
        return GameConfig.SHOP_ITEMS.get(item_id)

# ==============================================================================
#  SECTION 3: DATABASE SYSTEM
# ==============================================================================

# Use absolute path to ensure DB is created in the correct directory
BASE_DIR = os.getcwd()
DB_FILE = os.path.join(BASE_DIR, "users.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

class DatabaseManager:
    @staticmethod
    def _initialize_db():
        if not os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "w", encoding='utf-8') as f:
                    json.dump({}, f)
                logger.info(f"📁 Database created at: {DB_FILE}")
            except Exception as e:
                logger.error(f"❌ Failed to create DB file: {e}")
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    @staticmethod
    def load_db() -> Dict:
        DatabaseManager._initialize_db()
        try:
            with open(DB_FILE, "r", encoding='utf-8') as f:
                content = f.read().strip()
                if not content: return {}
                data = json.loads(content)
                
                # Legacy Support Migration
                if isinstance(data, list):
                    logger.warning("⚠️ Migrating legacy DB list to dict...")
                    new_data = {str(uid): DatabaseManager._get_default_schema() for uid in data}
                    DatabaseManager.save_full_db(new_data)
                    return new_data
                return data
        except Exception as e:
            logger.error(f"⚠️ Database Load Error: {e}")
            return {}

    @staticmethod
    def save_full_db(data: Dict):
        try:
            temp_file = f"{DB_FILE}.tmp"
            with open(temp_file, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, DB_FILE)
        except Exception as e:
            logger.error(f"❌ Failed to save DB: {e}")

    @staticmethod
    def create_backup():
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(BACKUP_DIR, f"users_{timestamp}.json")
            shutil.copy2(DB_FILE, backup_path)
            logger.info(f"📦 Backup created: {backup_path}")
            
            # Keep last 5 backups
            backups = sorted(os.listdir(BACKUP_DIR))
            if len(backups) > 5:
                os.remove(os.path.join(BACKUP_DIR, backups[0]))
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")

    @staticmethod
    def _get_default_schema() -> Dict:
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
        db = DatabaseManager.load_db()
        return db.get(str(user_id))

    @staticmethod
    def register_user(user_id: int, username: str, first_name: str, referrer_id: Optional[str] = None):
        db = DatabaseManager.load_db()
        uid_str = str(user_id)
        
        if uid_str in db:
            db[uid_str]["username"] = username
            db[uid_str]["first_name"] = first_name
            db[uid_str]["last_active"] = time.time()
            DatabaseManager.save_full_db(db)
            return False
        
        new_user = DatabaseManager._get_default_schema()
        new_user["username"] = username
        new_user["first_name"] = first_name
        
        if referrer_id and referrer_id != uid_str and referrer_id in db:
            new_user["referredBy"] = referrer_id
            db[referrer_id]["balance"] = db[referrer_id].get("balance", 0) + GameConfig.REFERRAL_BONUS
            if "referrals" not in db[referrer_id]:
                db[referrer_id]["referrals"] = []
            db[referrer_id]["referrals"].append(uid_str)
            new_user["balance"] += GameConfig.REFERRAL_BONUS

        db[uid_str] = new_user
        DatabaseManager.save_full_db(db)
        logger.info(f"🆕 Registered: {username} ({user_id})")
        return True

    @staticmethod
    def update_user_progress(user_id: int, data: dict):
        db = DatabaseManager.load_db()
        uid_str = str(user_id)
        if uid_str not in db: return False
        
        user = db[uid_str]
        for k, v in data.items():
            if k in user: user[k] = v
        
        user['last_active'] = time.time()
        db[uid_str] = user
        DatabaseManager.save_full_db(db)
        return True

    @staticmethod
    def get_all_user_ids() -> List[int]:
        db = DatabaseManager.load_db()
        return [int(uid) for uid in db.keys() if not db[uid].get('is_blocked', False)]

    @staticmethod
    def get_stats() -> Dict:
        db = DatabaseManager.load_db()
        dau = sum(1 for u in db.values() if u.get('last_active', 0) > time.time() - 86400)
        return {
            "total_users": len(db),
            "total_balance": sum(u.get('balance', 0) for u in db.values()),
            "total_ton": sum(u.get('tonBalance', 0) for u in db.values()),
            "dau": dau
        }

# Initialize DB on start
DatabaseManager._initialize_db()

# ==============================================================================
#  SECTION 4: BOT SETUP
# ==============================================================================

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# States
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()
    confirm_send = State()

MAINTENANCE_MODE = False

# ==============================================================================
#  SECTION 5: KEYBOARDS & UI
# ==============================================================================

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Play Snowman Adventure ☃️", url=f"https://t.me/{BOT_TOKEN.split(':')[0]}/app")],
        [InlineKeyboardButton(text="📢 Announcement Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="💬 Community Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="show_leaderboard"),
         InlineKeyboardButton(text="❓ Help", callback_data="show_help")]
    ])

def get_admin_keyboard():
    status = "🔴 ON" if MAINTENANCE_MODE else "🟢 OFF"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 New Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 View Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💾 Force Backup", callback_data="admin_backup")],
        [InlineKeyboardButton(text=f"🔧 Maintenance: {status}", callback_data="admin_toggle_maint")]
    ])

def get_broadcast_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Photo + Text", callback_data="br_start_media_photo")],
        [InlineKeyboardButton(text="📹 Video + Text", callback_data="br_start_media_video")],
        [InlineKeyboardButton(text="📝 Text Message Only", callback_data="br_start_text")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="br_cancel")]
    ])

def get_nav_buttons(next_cb: str, back_cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Next Step", callback_data=next_cb)],
        [InlineKeyboardButton(text="🔙 Go Back", callback_data=back_cb)]
    ])

def get_final_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 CONFIRM & SEND NOW", callback_data="br_final_send")],
        [InlineKeyboardButton(text="❌ CANCEL EVERYTHING", callback_data="br_cancel")]
    ])

def parse_buttons_text(text: str) -> Optional[InlineKeyboardMarkup]:
    if not text or text.lower() == 'skip': return None
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
    except Exception:
        return None

# ==============================================================================
#  SECTION 6: HANDLERS (COMMANDS & EVENTS)
# ==============================================================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    logger.info(f"📩 /start from {message.from_user.id}")
    
    if MAINTENANCE_MODE and message.from_user.id != ADMIN_ID:
        await message.answer("🚧 **System Under Maintenance**")
        return

    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    first_name = message.from_user.first_name or "User"
    referrer_id = command.args

    is_new = DatabaseManager.register_user(user_id, username, first_name, referrer_id)
    
    txt = (
        f"❄️☃️ <b>Welcome to Snowman Adventure, {first_name}!</b> ☃️❄️\n\n"
        "Embark on a frosty journey to build the ultimate snowman empire!\n\n"
        "🎮 <b>How to Play:</b>\n"
        "• Tap to earn Snow Coins\n"
        "• Level up your Snowman\n"
        "• Invite friends for bonuses\n\n"
        "👇 <b>Start your adventure now!</b>"
    )
    if is_new and referrer_id: txt += f"\n\n🎁 <b>Referral Bonus: +{GameConfig.REFERRAL_BONUS} Coins!</b>"

    await message.answer(txt, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(Command("help"))
@router.callback_query(F.data == "show_help")
async def cmd_help(event: Union[types.Message, CallbackQuery]):
    txt = "<b>🆘 Help Center</b>\n\nClick 'Play' to start earning!\nJoin our channels for updates."
    if isinstance(event, types.Message):
        await event.answer(txt, parse_mode="HTML")
    else:
        await event.message.answer(txt, parse_mode="HTML")
        await event.answer()

@router.callback_query(F.data == "show_leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    db = DatabaseManager.load_db()
    sorted_users = sorted(db.items(), key=lambda i: i[1].get('balance', 0), reverse=True)[:10]
    
    txt = "🏆 <b>TOP 10 SNOWMEN</b> 🏆\n\n"
    for idx, (uid, data) in enumerate(sorted_users, 1):
        txt += f"{idx}. <b>{data.get('username', 'Unknown')}</b>: {int(data.get('balance',0)):,}\n"
        
    await call.message.answer(txt, parse_mode="HTML")
    await call.answer()

# --- ADMIN PANEL HANDLERS ---

@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    s = DatabaseManager.get_stats()
    txt = (
        "🔐 <b>ADMIN PANEL</b>\n"
        f"👥 Users: {s['total_users']}\n"
        f"⚡ DAU: {s['dau']}\n"
        f"💰 Coins: {int(s['total_balance']):,}"
    )
    await message.answer(txt, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "admin_stats")
async def cb_refresh_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    s = DatabaseManager.get_stats()
    txt = f"🔐 <b>ADMIN PANEL</b>\n👥 Users: {s['total_users']}\n⚡ DAU: {s['dau']}\n💰 Coins: {int(s['total_balance']):,}"
    try: await call.message.edit_text(txt, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    except: await call.answer("Updated!")

@router.callback_query(F.data == "admin_backup")
async def cb_force_backup(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    DatabaseManager.create_backup()
    await call.answer("✅ Backup Created!", show_alert=True)

@router.callback_query(F.data == "admin_toggle_maint")
async def cb_toggle_maintenance(call: CallbackQuery):
    global MAINTENANCE_MODE
    if call.from_user.id != ADMIN_ID: return
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    await call.answer(f"Maintenance: {MAINTENANCE_MODE}", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=get_admin_keyboard())

# --- BROADCAST WIZARD ---

@router.callback_query(F.data == "admin_broadcast")
async def br_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.clear()
    await call.message.edit_text("📢 <b>Broadcast Type?</b>", reply_markup=get_broadcast_type_kb(), parse_mode="HTML")

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def br_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Cancelled.")

@router.callback_query(F.data.startswith("br_start_"))
async def br_type(call: CallbackQuery, state: FSMContext):
    m_type = call.data.replace("br_start_", "")
    if m_type == "text":
        await state.update_data(media_type="text")
        await state.set_state(BroadcastState.waiting_for_text)
        await call.message.edit_text("📝 <b>Send Message Text:</b>", parse_mode="HTML")
    else:
        await state.update_data(media_type=m_type.replace("media_", ""))
        await state.set_state(BroadcastState.waiting_for_media)
        await call.message.edit_text(f"📤 <b>Send {m_type.upper()}:</b>", parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_media))
async def br_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    expected = data.get("media_type")
    
    fid = None
    if expected == "photo" and message.photo: fid = message.photo[-1].file_id
    elif expected == "video" and message.video: fid = message.video.file_id
    
    if not fid:
        await message.answer(f"⚠️ Send a {expected}!")
        return

    await state.update_data(media_id=fid)
    await state.set_state(BroadcastState.waiting_for_text)
    await message.answer("✅ Saved. Now send <b>Caption</b> (or /skip).", parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_text))
async def br_text(message: types.Message, state: FSMContext):
    txt = message.text
    if txt == "/skip": txt = ""
    await state.update_data(text=txt)
    await state.set_state(BroadcastState.waiting_for_buttons)
    await message.answer("✅ Saved. Send <b>Buttons</b> (Text - URL) or type 'skip'.", parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_buttons))
async def br_buttons(message: types.Message, state: FSMContext):
    txt = message.text
    btns = None if txt.lower() == "skip" else txt
    
    await state.update_data(buttons=btns)
    await br_preview(message, state)

async def br_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    kb = parse_buttons_text(data.get("buttons"))
    
    await message.answer("➖➖ <b>PREVIEW</b> ➖➖", parse_mode="HTML")
    try:
        if data["media_type"] == "text":
            await message.answer(data["text"], reply_markup=kb, parse_mode="HTML")
        elif data["media_type"] == "photo":
            await message.answer_photo(data["media_id"], caption=data["text"], reply_markup=kb, parse_mode="HTML")
        elif data["media_type"] == "video":
            await message.answer_video(data["media_id"], caption=data["text"], reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")
        
    await message.answer("🚀 <b>Confirm Send?</b>", reply_markup=get_final_confirm_kb(), parse_mode="HTML")
    await state.set_state(BroadcastState.confirm_send)

@router.callback_query(F.data == "br_final_send", StateFilter(BroadcastState.confirm_send))
async def br_execute(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await call.message.edit_text("🚀 <b>Broadcasting...</b>", parse_mode="HTML")
    asyncio.create_task(run_broadcast(call.message.chat.id, data))

async def run_broadcast(admin_id: int, data: dict):
    users = DatabaseManager.get_all_user_ids()
    sent, blocked = 0, 0
    kb = parse_buttons_text(data.get("buttons"))
    
    for uid in users:
        try:
            if data["media_type"] == "text":
                await bot.send_message(uid, data["text"], reply_markup=kb, parse_mode="HTML")
            elif data["media_type"] == "photo":
                await bot.send_photo(uid, data["media_id"], caption=data["text"], reply_markup=kb, parse_mode="HTML")
            elif data["media_type"] == "video":
                await bot.send_video(uid, data["media_id"], caption=data["text"], reply_markup=kb, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.04)
        except TelegramForbiddenError: blocked += 1
        except Exception: pass
        
    await bot.send_message(admin_id, f"✅ Done!\nSent: {sent}\nBlocked: {blocked}")

# --- PAYMENT HANDLERS ---

@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@router.message(F.successful_payment)
async def on_payment(message: types.Message):
    try:
        payload = message.successful_payment.invoice_payload
        _, item_id = payload.split("_", 1)
        item = GameConfig.get_item(item_id)
        
        db = DatabaseManager.load_db()
        uid = str(message.from_user.id)
        
        if uid in db and item:
            if item['type'] == 'coin':
                db[uid]['balance'] += item['amount']
            elif item['type'] == 'booster':
                end = max(db[uid].get('booster_end', 0), time.time())
                db[uid]['booster_end'] = end + item['amount']
            elif item['type'] == 'autotap':
                end = max(db[uid].get('autotap_end', 0), time.time())
                db[uid]['autotap_end'] = end + item['amount']
            
            DatabaseManager.save_full_db(db)
            await message.answer(f"✅ Received: {item['title']}!")
    except Exception as e:
        logger.error(f"Payment Error: {e}")

# ==============================================================================
#  SECTION 7: API & SERVER
# ==============================================================================

def cors(data, status=200):
    return web.json_response(data, status=status, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })

async def options_handler(request):
    return web.Response(status=200, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "*", "Access-Control-Allow-Headers": "*"})

# --- API ENDPOINTS ---

async def api_sync(request):
    try:
        d = await request.json()
        uid = d.get('user_id')
        if not uid: return cors({"error": "No ID"}, 400)
        
        clean = {}
        if 'balance' in d: clean['balance'] = float(d['balance'])
        if 'level' in d: clean['level'] = int(d['level'])
        if 'tapCount' in d: clean['tapCount'] = int(d['tapCount'])
        if 'tonBalance' in d: clean['tonBalance'] = float(d['tonBalance'])
            
        if DatabaseManager.update_user_progress(uid, clean):
            return cors({"success": True})
        return cors({"error": "User missing"}, 404)
    except Exception as e: return cors({"error": str(e)}, 500)

async def api_verify_join(request):
    try:
        d = await request.json()
        uid = d.get('user_id')
        if not uid: return cors({"joined": False}, 400)

        async def check(cid):
            try:
                m = await bot.get_chat_member(cid, uid)
                return m.status in ['member', 'administrator', 'creator']
            except: return False

        joined = (await check(CHANNEL_USERNAME)) and (await check(GROUP_USERNAME))
        return cors({"joined": joined})
    except Exception as e: return cors({"error": str(e)}, 500)

async def api_create_invoice(request):
    try:
        d = await request.json()
        item = GameConfig.get_item(d.get('item_id'))
        if not item: return cors({"error": "Invalid"}, 400)
        
        link = await bot.create_invoice_link(
            title=item['title'], description=item['desc'], payload=f"{d['user_id']}_{d.get('item_id')}",
            provider_token="", currency="XTR", prices=[LabeledPrice(label=item['title'], amount=item['price'])]
        )
        return cors({"result": link})
    except Exception as e: return cors({"error": str(e)}, 500)

async def api_verify_ad(request):
    return cors({"success": True})

async def api_play_spin(request):
    try:
        uid = (await request.json()).get('user_id')
        if not uid: return cors({"success": False}, 400)
        prizes = GameConfig.SPIN_PRIZES
        idx = random.randint(0, len(prizes) - 1)
        return cors({"success": True, "index": idx, "amount": prizes[idx]})
    except: return cors({"success": False}, 500)

async def api_complete_task(request):
    return cors({"success": True})

async def api_get_referrals(request):
    try:
        uid = request.query.get('user_id')
        user = DatabaseManager.get_user(uid)
        if not user: return cors({"referrals": []})
        
        refs = []
        db = DatabaseManager.load_db()
        for rid in user.get('referrals', []):
            if rdata := db.get(rid):
                refs.append({"username": rdata.get('username'), "balance": rdata.get('balance')})
        return cors({"referrals": refs})
    except: return cors({"error": "Fail"}, 500)

# --- MANUAL WEBHOOK HANDLER (THE FIX) ---
async def handle_webhook(request):
    """Bypasses aiogram's default handler to ensure debugging visibility."""
    try:
        data = await request.json()
        # logger.info(f"📥 Update: {data.get('update_id')}")
        update = types.Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"⚠️ Webhook Error: {e}")
        # Return 200 to stop Telegram from retrying bad updates
        return web.Response(text="Error", status=200)

async def handle_home(request):
    return web.Response(text=f"☃️ Snowman Bot Online. {datetime.now()}")

# ==============================================================================
#  SECTION 8: LIFECYCLE & EXECUTION
# ==============================================================================

async def on_startup(app):
    logger.info("🚀 Server Starting...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)
        await bot.set_my_commands([BotCommand(command="start", description="Start Game"), BotCommand(command="admin", description="Admin Panel")])
        logger.info(f"✅ Webhook Set: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Webhook Failed: {e}")

async def on_shutdown(app):
    logger.info("🔌 Server Stopping...")
    await bot.delete_webhook()
    await bot.session.close()

def main():
    app = web.Application()
    
    # Routes
    app.router.add_get('/', handle_home)
    app.router.add_post(WEBHOOK_PATH, handle_webhook) # The Manual Fix
    
    # API Routes
    app.router.add_post('/sync-user-data', api_sync)
    app.router.add_post('/verify_join', api_verify_join)
    app.router.add_post('/create_invoice', api_create_invoice)
    app.router.add_post('/verify-ad', api_verify_ad)
    app.router.add_post('/play-spin', api_play_spin)
    app.router.add_post('/complete-task', api_complete_task)
    app.router.add_get('/get-referrals', api_get_referrals)
    
    # CORS Options
    for r in list(app.router.routes()):
        if r.method == "POST": app.router.add_options(r.resource.canonical, options_handler)

    # Register Lifecycle Hooks
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    
    logger.info(f"🌍 Running on PORT {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()

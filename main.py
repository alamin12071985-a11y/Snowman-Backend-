import os
import sys
import logging
import asyncio
import sqlite3
import html
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
# Render Environment এ ADMIN_IDS সেট করুন (যেমন: 12345678, 87654321)
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "0").split(",") if id.strip().isdigit()]

if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL: Environment variables missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE SETUP ---
DB_FILE = "snowman_users.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Init Error: {e}")

def add_user(user_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Add User Error: {e}")

def get_all_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except:
        return []

# --- STATES ---
class BroadcastState(StatesGroup):
    dashboard = State()
    waiting_media = State()
    waiting_text = State()
    waiting_buttons = State()

# --- BOT INIT ---
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

# --- KEYBOARDS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventurecommunity")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_dashboard_kb():
    kb = [
        [InlineKeyboardButton(text="🖼️ Set Media", callback_data="adm_media"), InlineKeyboardButton(text="📝 Set Text", callback_data="adm_text")],
        [InlineKeyboardButton(text="⌨️ Set Buttons", callback_data="adm_buttons")],
        [InlineKeyboardButton(text="👀 Full Preview", callback_data="adm_preview")],
        [InlineKeyboardButton(text="🚀 Send Broadcast", callback_data="adm_send")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="adm_back")]])

# --- USER HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id)
    first_name = html.escape(message.from_user.first_name)
    
    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome!</b> ☃️❄️
Tap the button below to start your adventure!
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- ADMIN PANEL HANDLERS ---

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    # Set Default Data
    await state.update_data(
        media_id=None,
        media_type=None,
        text="❄️ <b>Default Broadcast Message</b>\n\nThis is a test message. Edit me using the panel!",
        buttons=[]
    )
    await state.set_state(BroadcastState.dashboard)
    await message.answer("🛠 <b>Admin Broadcast Panel</b>\nSelect an option to configure:", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())

# --- DASHBOARD CALLBACKS ---

@router.callback_query(BroadcastState.dashboard, F.data == "adm_media")
async def cb_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_media)
    await call.message.edit_text("🖼️ <b>Send me a Photo or Video.</b>\n\n(Click Back to cancel)", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(BroadcastState.dashboard, F.data == "adm_text")
async def cb_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_text)
    await call.message.edit_text("📝 <b>Send me the Message Text.</b>\n\nHTML formatting is supported.", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(BroadcastState.dashboard, F.data == "adm_buttons")
async def cb_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_buttons)
    await call.message.edit_text(
        "⌨️ <b>Send Buttons in this format:</b>\n\n"
        "<code>Button Name - Link</code>\n"
        "<code>Join Channel - @channel_username</code>\n\n"
        "Send 'clear' to remove buttons.", 
        parse_mode="HTML", reply_markup=get_cancel_kb()
    )

@router.callback_query(F.data == "adm_back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.dashboard)
    await call.message.delete()
    await call.message.answer("🛠 <b>Admin Broadcast Panel</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())

# --- INPUT PROCESSING ---

@router.message(BroadcastState.waiting_media)
async def process_media(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(media_id=message.photo[-1].file_id, media_type='photo')
        await message.answer("✅ <b>Photo Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    elif message.video:
        await state.update_data(media_id=message.video.file_id, media_type='video')
        await message.answer("✅ <b>Video Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    else:
        await message.answer("⚠️ Please send a Photo or Video.", reply_markup=get_cancel_kb())
        return
    await state.set_state(BroadcastState.dashboard)

@router.message(BroadcastState.waiting_text)
async def process_text(message: types.Message, state: FSMContext):
    # Use html_text to preserve bold/italic from user input
    final_text = message.html_text if message.html_text else html.escape(message.text)
    await state.update_data(text=final_text)
    await message.answer("✅ <b>Text Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    await state.set_state(BroadcastState.dashboard)

@router.message(BroadcastState.waiting_buttons)
async def process_buttons(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if text.lower() == 'clear':
        await state.update_data(buttons=[])
        await message.answer("✅ Buttons Cleared!", reply_markup=get_admin_dashboard_kb())
        await state.set_state(BroadcastState.dashboard)
        return

    # Button Parser
    buttons = []
    lines = text.split('\n')
    for line in lines:
        if '-' in line:
            parts = line.split('-', 1)
            btn_txt = parts[0].strip()
            btn_url = parts[1].strip()
            
            # Handle @username links
            if btn_url.startswith('@'):
                btn_url = f"https://t.me/{btn_url[1:]}"
            elif not btn_url.startswith('http'):
                btn_url = f"https://{btn_url}"
                
            buttons.append([btn_txt, btn_url])
    
    if buttons:
        await state.update_data(buttons=buttons)
        await message.answer(f"✅ <b>{len(buttons)} Buttons Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
        await state.set_state(BroadcastState.dashboard)
    else:
        await message.answer("⚠️ Invalid Format. Try:\n<code>Click Me - https://google.com</code>", parse_mode="HTML", reply_markup=get_cancel_kb())

# --- PREVIEW & SEND ---

@router.callback_query(BroadcastState.dashboard, F.data == "adm_preview")
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Build Keyboard
    kb_rows = []
    for txt, url in data['buttons']:
        kb_rows.append([InlineKeyboardButton(text=txt, url=url)])
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    
    # Send Preview
    try:
        if data['media_id']:
            if data['media_type'] == 'photo':
                await call.message.answer_photo(photo=data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
            elif data['media_type'] == 'video':
                await call.message.answer_video(video=data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
        else:
            await call.message.answer(data['text'], parse_mode="HTML", reply_markup=markup)
            
        await call.message.answer("👆 <b>This is the Preview.</b>\nClick 'Send Broadcast' to publish.", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    except Exception as e:
        await call.message.answer(f"⚠️ Preview Error: {e}", reply_markup=get_admin_dashboard_kb())
    
    await call.answer()

@router.callback_query(BroadcastState.dashboard, F.data == "adm_send")
async def cb_send(call: CallbackQuery, state: FSMContext):
    users = get_all_users()
    data = await state.get_data()
    
    if not users:
        await call.answer("No users in database!", show_alert=True)
        return

    await call.message.edit_text(f"🚀 <b>Broadcasting to {len(users)} users...</b>", parse_mode="HTML")
    
    # Prepare Content
    kb_rows = []
    for txt, url in data['buttons']:
        kb_rows.append([InlineKeyboardButton(text=txt, url=url)])
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    
    success = 0
    blocked = 0
    
    for user_id in users:
        try:
            if data['media_id']:
                if data['media_type'] == 'photo':
                    await bot.send_photo(user_id, data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
                elif data['media_type'] == 'video':
                    await bot.send_video(user_id, data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(user_id, data['text'], parse_mode="HTML", reply_markup=markup)
            success += 1
            await asyncio.sleep(0.05) # Rate limit safety
        except Exception:
            blocked += 1
            
    await call.message.answer(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"🟢 Sent: {success}\n"
        f"🔴 Failed/Blocked: {blocked}",
        parse_mode="HTML"
    )
    await state.clear()

# --- AUTO BROADCAST (DAILY) ---
async def daily_broadcast_task():
    logging.info("⏰ Running Daily Auto-Broadcast...")
    users = get_all_users()
    if not users: return
    
    caption = """
❄️🚨 <b>HEY! Your Daily Rewards Are MELTING AWAY!</b> 🚨❄️
Snowman is waving at you right now ☃️👋
Today = <b>FREE rewards</b>, but only if you show up! 😱🎁

👉 <b>Open App Now!</b>
    """
    # Auto Broadcast এর জন্য একটি ডিফল্ট ফটো আইডি দিন
    photo_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"
    
    for user_id in users:
        try:
            await bot.send_photo(user_id, photo_id, caption=caption, parse_mode="HTML", reply_markup=get_main_keyboard())
            await asyncio.sleep(0.05)
        except: pass

# --- SERVER ---
async def home(request): return web.Response(text="Bot is Live")

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
    scheduler.add_job(daily_broadcast_task, 'cron', hour=8, minute=0)
    scheduler.start()

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    scheduler.shutdown()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    app = web.Application()
    app.router.add_get('/', home)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()

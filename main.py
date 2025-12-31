import os
import sys
import logging
import asyncio
import sqlite3
import html
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, LabeledPrice
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

# Admin IDs Setup
env_admin = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in env_admin.split(",") if id.strip().isdigit()]

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
        logging.error(f"DB Error: {e}")

def add_user(user_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Add Error: {e}")

def get_all_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventurecommunity")]
    ])

def get_admin_dashboard_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Set Media", callback_data="adm_media"), InlineKeyboardButton(text="📝 Set Text", callback_data="adm_text")],
        [InlineKeyboardButton(text="⌨️ Set Buttons", callback_data="adm_buttons")],
        [InlineKeyboardButton(text="👀 Full Preview", callback_data="adm_preview")],
        [InlineKeyboardButton(text="🚀 Send Broadcast", callback_data="adm_send")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="adm_back")]])

# ==========================================
# 👇 COMMAND HANDLERS (ADMIN FIXED) 👇
# ==========================================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    first_name = html.escape(message.from_user.first_name)
    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️
Brrrr… the snow is falling and your journey starts <b>RIGHT NOW!</b> 🌨️✨

<blockquote>👉 <b>Tap & Earn:</b> Collect coins instantly ❄️
👉 <b>Daily Tasks:</b> Complete and win 🔑
👉 <b>Invite Friends:</b> Earn MORE rewards 💫</blockquote>

👇 <b>Start Your Journey Below</b> 👇
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"Admin Access Requested by: {user_id}")
    
    # 🔴 ID CHECK & DEBUGGING
    if user_id not in ADMIN_IDS:
        await message.answer(
            f"🚫 <b>Access Denied!</b>\n\n"
            f"Bot does not recognize you as Admin.\n"
            f"<b>Your ID:</b> <code>{user_id}</code>\n\n"
            f"Please add this ID to Render Environment Variables under <b>ADMIN_IDS</b>.",
            parse_mode="HTML"
        )
        return

    # Admin Accepted
    await state.clear()
    await state.update_data(text="❄️ <b>Default Broadcast Message</b>", buttons=[])
    await state.set_state(BroadcastState.dashboard)
    await message.answer("🛠 <b>Admin Broadcast Panel</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())

# ==========================================
# 👇 ADMIN CALLBACKS 👇
# ==========================================

@router.callback_query(BroadcastState.dashboard, F.data == "adm_media")
async def cb_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_media)
    await call.message.edit_text("🖼️ <b>Send Photo/Video</b>", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(BroadcastState.dashboard, F.data == "adm_text")
async def cb_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_text)
    await call.message.edit_text("📝 <b>Send Message Text</b>", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(BroadcastState.dashboard, F.data == "adm_buttons")
async def cb_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_buttons)
    await call.message.edit_text("⌨️ <b>Send Buttons:</b>\n<code>Name - Link</code>", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(F.data == "adm_back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.dashboard)
    await call.message.delete()
    await call.message.answer("🛠 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())

# -- INPUT HANDLERS --
@router.message(BroadcastState.waiting_media)
async def process_media(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(media_id=message.photo[-1].file_id, media_type='photo')
        await message.answer("✅ Photo Set!", reply_markup=get_admin_dashboard_kb())
    elif message.video:
        await state.update_data(media_id=message.video.file_id, media_type='video')
        await message.answer("✅ Video Set!", reply_markup=get_admin_dashboard_kb())
    else:
        await message.answer("⚠️ Send Photo or Video only.", reply_markup=get_cancel_kb())
        return
    await state.set_state(BroadcastState.dashboard)

@router.message(BroadcastState.waiting_text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.html_text if message.html_text else html.escape(message.text))
    await message.answer("✅ Text Set!", reply_markup=get_admin_dashboard_kb())
    await state.set_state(BroadcastState.dashboard)

@router.message(BroadcastState.waiting_buttons)
async def process_buttons(message: types.Message, state: FSMContext):
    if message.text.lower() == 'clear':
        await state.update_data(buttons=[])
        await message.answer("✅ Buttons Cleared!", reply_markup=get_admin_dashboard_kb())
        await state.set_state(BroadcastState.dashboard)
        return
    
    buttons = []
    for line in message.text.split('\n'):
        if '-' in line:
            t, u = line.split('-', 1)
            u = u.strip()
            if u.startswith('@'): u = f"https://t.me/{u[1:]}"
            elif not u.startswith('http'): u = f"https://{u}"
            buttons.append([t.strip(), u])
    
    if buttons:
        await state.update_data(buttons=buttons)
        await message.answer(f"✅ {len(buttons)} Buttons Set!", reply_markup=get_admin_dashboard_kb())
        await state.set_state(BroadcastState.dashboard)
    else:
        await message.answer("⚠️ Invalid Format.", reply_markup=get_cancel_kb())

# -- SEND LOGIC --
@router.callback_query(BroadcastState.dashboard, F.data == "adm_preview")
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, url=u)] for t, u in data['buttons']]) if data['buttons'] else None
    try:
        if data.get('media_id'):
            method = call.message.answer_photo if data['media_type'] == 'photo' else call.message.answer_video
            await method(data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=kb)
        else:
            await call.message.answer(data['text'], parse_mode="HTML", reply_markup=kb)
        await call.message.answer("👆 Preview. Click Send to broadcast.", reply_markup=get_admin_dashboard_kb())
    except Exception as e:
        await call.message.answer(f"Error: {e}")
    await call.answer()

@router.callback_query(BroadcastState.dashboard, F.data == "adm_send")
async def cb_send(call: CallbackQuery, state: FSMContext):
    users = get_all_users()
    if not users: return await call.answer("No users!", show_alert=True)
    
    data = await state.get_data()
    await call.message.edit_text(f"🚀 Broadcasting to {len(users)} users...")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, url=u)] for t, u in data['buttons']]) if data['buttons'] else None
    success = 0
    
    for uid in users:
        try:
            if data.get('media_id'):
                method = bot.send_photo if data['media_type'] == 'photo' else bot.send_video
                await method(uid, data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=kb)
            else:
                await bot.send_message(uid, data['text'], parse_mode="HTML", reply_markup=kb)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
        
    await call.message.answer(f"✅ Sent to {success} users.")
    await state.clear()

# ==========================================
# 👇 GENERAL TEXT HANDLER (IGNORE COMMANDS FIX) 👇
# ==========================================

# ⚠️ এই লাইনটি গুরুত্বপূর্ণ: এটি / দিয়ে শুরু হওয়া মেসেজগুলো ইগনোর করবে
@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message):
    """
    Handles normal text messages but IGNORES commands like /admin
    """
    add_user(message.from_user.id)
    first_name = html.escape(message.from_user.first_name)
    
    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome Back!</b> ☃️❄️
Snowman heard you typing… and got excited! 😄💫

<blockquote>➡️ <b>Tap the Snowman:</b> Earn coins 💰
➡️ <b>Complete Tasks:</b> Get instant rewards 🎯
➡️ <b>Invite Friends:</b> Grow faster 👥</blockquote>

👇 <b>Continue Adventure</b> 👇
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- SERVER LIFECYCLE (FIXED UNCLOSED SESSION) ---
async def home(request): return web.Response(text="Bot Running")
async def create_invoice(request): return web.json_response({"result": "TODO"})

async def daily_task():
    # Auto Broadcast Code
    users = get_all_users()
    for uid in users:
        try:
            await bot.send_message(uid, "❄️ Daily Rewards Waiting! ☃️", reply_markup=get_main_keyboard())
            await asyncio.sleep(0.05)
        except: pass

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
    scheduler.add_job(daily_task, 'cron', hour=8, minute=0)
    scheduler.start()

async def on_shutdown(bot: Bot):
    logging.info("Shutting down bot...")
    await bot.delete_webhook()
    scheduler.shutdown()
    # 🔴 এই লাইনটি আপনার এরর ফিক্স করবে (Session Close)
    await bot.session.close()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    app = web.Application()
    app.router.add_get('/', home)
    app.router.add_post('/create_invoice', create_invoice)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()

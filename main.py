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

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# Admin IDs (Render Environment থেকে নেওয়া হবে)
# যদি সেট করা না থাকে তবে এরর দিবে না, কিন্তু /admin কাজ করবে না
env_admin = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in env_admin.split(",") if id.strip().isdigit()]

if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL: Environment variables missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE SETUP (SQLite) ---
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

# --- STATES FOR ADMIN PANEL ---
class BroadcastState(StatesGroup):
    dashboard = State()
    waiting_media = State()
    waiting_text = State()
    waiting_buttons = State()

# --- BOT INITIALIZATION ---
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

# --- SHOP CONFIG ---
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},
}

# --- KEYBOARDS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp")],
        [
            InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discuss 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
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
    add_user(user_id) # ডাটাবেসে ইউজার সেভ
    first_name = html.escape(message.from_user.first_name)
    
    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️

Brrrr… the snow is falling and your journey starts <b>RIGHT NOW!</b> 🌨️✨

<b>Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁</b>

<blockquote>👉 <b>Tap & Earn:</b> Collect coins instantly ❄️
👉 <b>Daily Tasks:</b> Complete and win 🔑
👉 <b>Lucky Spin:</b> Spin & win surprises 🎡
👉 <b>Invite Friends:</b> Earn MORE rewards 💫
👉 <b>Leaderboard:</b> Climb to the top 🏆</blockquote>

Every tap matters. Every coin counts.
And you are now part of the <b>Snowman family</b> 🤍☃️

👇 <b>Start Your Journey Below</b> 👇
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@router.message(F.text)
async def echo_all(message: types.Message):
    user_id = message.from_user.id
    first_name = html.escape(message.from_user.first_name)
    
    # ইউজার মেসেজ দিলেই তাকে ডাটাবেসে চেক করে সেভ করে নিবে (যদি আগে মিস হয়ে থাকে)
    add_user(user_id)

    text = f"""
❄️☃️ <b>Hey {first_name}, Welcome Back!</b> ☃️❄️

Snowman heard you typing… and got excited! 😄💫
That means it’s time to jump back into the icy fun ❄️🎮

<b>Here is your current status update:</b>

<blockquote>➡️ <b>Tap the Snowman:</b> Earn coins 💰
➡️ <b>Complete Tasks:</b> Get instant rewards 🎯
➡️ <b>Spin the Wheel:</b> Win surprises 🎡
➡️ <b>Invite Friends:</b> Grow faster 👥
➡️ <b>Rank Up:</b> Chase the top spot 🏆</blockquote>

Every click brings progress.
Every moment brings rewards. 🌟

<b>Choose your next move below and keep the adventure going ⬇️</b>

❄️ <i>Stay cool. Keep tapping. Snowman Adventure never sleeps!</i> ☃️🔥
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- ADMIN PANEL LOGIC ---

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # অ্যাডমিন ভেরিফিকেশন এবং আইডি ডিবাগিং
    if user_id not in ADMIN_IDS:
        await message.answer(
            f"🚫 <b>Access Denied!</b>\n\n"
            f"Your ID is: <code>{user_id}</code>\n\n"
            f"Copy this ID and put it in Render Environment Variables under <b>ADMIN_IDS</b>.",
            parse_mode="HTML"
        )
        return
    
    # ডিফল্ট ডাটা সেট করা
    await state.update_data(
        media_id=None,
        media_type=None,
        text="❄️ <b>Default Broadcast Message</b>\n\nEdit this text to send your announcement!",
        buttons=[]
    )
    await state.set_state(BroadcastState.dashboard)
    await message.answer("🛠 <b>Admin Broadcast Panel</b>\nSelect an option to configure:", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())

# -- Callbacks --
@router.callback_query(BroadcastState.dashboard, F.data == "adm_media")
async def cb_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_media)
    await call.message.edit_text("🖼️ <b>Send me a Photo or Video.</b>\n\n(Click Back to cancel)", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(BroadcastState.dashboard, F.data == "adm_text")
async def cb_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_text)
    await call.message.edit_text("📝 <b>Send me the Message Text.</b>\nHTML formatting supported.", parse_mode="HTML", reply_markup=get_cancel_kb())

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

# -- Input Handlers --
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

    buttons = []
    lines = text.split('\n')
    for line in lines:
        if '-' in line:
            parts = line.split('-', 1)
            btn_txt = parts[0].strip()
            btn_url = parts[1].strip()
            if btn_url.startswith('@'): btn_url = f"https://t.me/{btn_url[1:]}"
            elif not btn_url.startswith('http'): btn_url = f"https://{btn_url}"
            buttons.append([btn_txt, btn_url])
    
    if buttons:
        await state.update_data(buttons=buttons)
        await message.answer(f"✅ <b>{len(buttons)} Buttons Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
        await state.set_state(BroadcastState.dashboard)
    else:
        await message.answer("⚠️ Invalid Format. Try:\n<code>Click Me - https://google.com</code>", parse_mode="HTML", reply_markup=get_cancel_kb())

# -- Preview & Send --
@router.callback_query(BroadcastState.dashboard, F.data == "adm_preview")
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb_rows = [[InlineKeyboardButton(text=t, url=u)] for t, u in data['buttons']]
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    
    try:
        if data['media_id']:
            if data['media_type'] == 'photo':
                await call.message.answer_photo(data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
            elif data['media_type'] == 'video':
                await call.message.answer_video(data['media_id'], caption=data['text'], parse_mode="HTML", reply_markup=markup)
        else:
            await call.message.answer(data['text'], parse_mode="HTML", reply_markup=markup)
        await call.message.answer("👆 <b>Preview Shown.</b> Click Send to broadcast.", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    except Exception as e:
        await call.message.answer(f"⚠️ Preview Error: {e}", reply_markup=get_admin_dashboard_kb())
    await call.answer()

@router.callback_query(BroadcastState.dashboard, F.data == "adm_send")
async def cb_send(call: CallbackQuery, state: FSMContext):
    users = get_all_users()
    data = await state.get_data()
    if not users:
        await call.answer("No users found!", show_alert=True)
        return

    await call.message.edit_text(f"🚀 <b>Broadcasting to {len(users)} users...</b>", parse_mode="HTML")
    kb_rows = [[InlineKeyboardButton(text=t, url=u)] for t, u in data['buttons']]
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
            await asyncio.sleep(0.05)
        except:
            blocked += 1
            
    await call.message.answer(f"✅ <b>Done!</b>\nSent: {success}\nFailed: {blocked}", parse_mode="HTML")
    await state.clear()

# --- PAYMENT ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("<blockquote>❄️ <b>Payment Successful!</b>\nRestart game to see changes.</blockquote>", parse_mode="HTML")

# --- API FOR SHOP & AUTO BROADCAST ---
async def create_invoice_api(request):
    try:
        data = await request.json()
        item = SHOP_ITEMS.get(data.get('item_id'))
        if not item: return web.json_response({"error": "Item not found"}, status=404)
        
        link = await bot.create_invoice_link(
            title="Snowman Shop", description=f"Buy {data.get('item_id')}", payload=f"{data.get('user_id')}_{data.get('item_id')}",
            provider_token="", currency="XTR", prices=[LabeledPrice(label=data.get('item_id'), amount=item['price'])]
        )
        return web.json_response({"result": link})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- DAILY AUTO BROADCAST TASK ---
async def daily_task():
    users = get_all_users()
    if not users: return
    # অটো ব্রডকাস্টের মেসেজ
    caption = """
❄️🚨 <b>HEY! Your Daily Rewards Are MELTING AWAY!</b> 🚨❄️
Snowman is waving at you right now ☃️👋
Today = <b>FREE rewards</b>, but only if you show up! 😱🎁

<blockquote>➡️ 🎡 <b>Daily Spin is ACTIVE</b>
➡️ 🎯 <b>Daily Tasks are OPEN</b></blockquote>
    """
    # এখানে একটি ভ্যালিড ফটো আইডি বসাতে পারেন, আপাতত টেক্সট যাচ্ছে যদি ফটো না থাকে
    # photo_id = "YOUR_PHOTO_ID_HERE" 
    
    for user_id in users:
        try:
            # await bot.send_photo(user_id, photo_id, caption=caption, parse_mode="HTML", reply_markup=get_main_keyboard())
            await bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=get_main_keyboard())
            await asyncio.sleep(0.05)
        except: pass

# --- APP START ---
async def home(request): return web.Response(text="Bot Running")

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
    scheduler.add_job(daily_task, 'cron', hour=8, minute=0)
    scheduler.start()

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    scheduler.shutdown()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/', home)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()

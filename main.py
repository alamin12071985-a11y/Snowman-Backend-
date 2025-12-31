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
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, 
    CallbackQuery, Message
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
ADMIN_ID = 7605281774  # আপনার অ্যাডমিন আইডি

if not BOT_TOKEN:
    logging.error("❌ CRITICAL: BOT_TOKEN is missing!")
    sys.exit(1)

if not APP_URL:
    logging.error("❌ CRITICAL: APP_URL is missing!")
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
        logging.info("✅ Database initialized.")
    except Exception as e:
        logging.error(f"❌ Database Init Error: {e}")

def add_user(user_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"⚠️ Failed to add user: {e}")

def get_all_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logging.error(f"⚠️ Failed to fetch users: {e}")
        return []

# --- SHOP ITEMS ---
SHOP_ITEMS = {
    'coin_starter': {'price': 10, 'amount': 100},
    'coin_small': {'price': 50, 'amount': 1},
    'coin_medium': {'price': 100, 'amount': 1},
    'coin_large': {'price': 250, 'amount': 1},
    'coin_mega': {'price': 500, 'amount': 1},
}

# --- STATES FOR BROADCAST (FSM) ---
class BroadcastState(StatesGroup):
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# --- BOT INIT ---
# মেমোরি স্টোরেজ ব্যবহার করা হচ্ছে ডাটা সাময়িক সেভ রাখার জন্য
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
        [
            InlineKeyboardButton(text="❄️ Join Channel 🎯", url="https://t.me/snowmanadventurecommunity"),
            InlineKeyboardButton(text="❄️ Discussion 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_dashboard_kb():
    """আপনার দেওয়া ইমেজের মত হুবহু ড্যাশবোর্ড"""
    kb = [
        [
            InlineKeyboardButton(text="🖼 Media", callback_data="panel_media"),
            InlineKeyboardButton(text="👀 See", callback_data="view_media")
        ],
        [
            InlineKeyboardButton(text="abc Text", callback_data="panel_text"),
            InlineKeyboardButton(text="👀 See", callback_data="view_text")
        ],
        [
            InlineKeyboardButton(text="⌨ Buttons", callback_data="panel_buttons"),
            InlineKeyboardButton(text="👀 See", callback_data="view_buttons")
        ],
        [
            InlineKeyboardButton(text="👀 Full preview", callback_data="view_full")
        ],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="panel_close"),
            InlineKeyboardButton(text="Next ➡", callback_data="panel_next")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel Input", callback_data="cancel_input")]])

# --- ADMIN PANEL HANDLERS ---

@router.message(Command("panel"), F.from_user.id == ADMIN_ID)
async def open_panel(message: types.Message, state: FSMContext):
    """অ্যাডমিন প্যানেল ওপেন করার কমান্ড"""
    await state.clear()
    # ডিফল্ট ডাটা সেট
    await state.update_data(
        bc_photo=None,
        bc_text="<b>📢 Broadcast Message</b>\n\nThis is a default text. Click 'Text' to change it.",
        bc_buttons=None
    )
    await message.answer(
        "<b>📢 Broadcast Control Panel</b>\n\nConfigure your post below:",
        reply_markup=get_admin_dashboard_kb(),
        parse_mode="HTML"
    )

# --- CALLBACK HANDLERS (Dashboard Actions) ---

@router.callback_query(F.data == "panel_media", F.from_user.id == ADMIN_ID)
async def ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📤 <b>Please send the PHOTO now.</b>", parse_mode="HTML", reply_markup=get_cancel_kb())
    await state.set_state(BroadcastState.waiting_for_media)

@router.callback_query(F.data == "panel_text", F.from_user.id == ADMIN_ID)
async def ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 <b>Please send the TEXT now.</b>\n(HTML Tags Supported)", parse_mode="HTML", reply_markup=get_cancel_kb())
    await state.set_state(BroadcastState.waiting_for_text)

@router.callback_query(F.data == "panel_buttons", F.from_user.id == ADMIN_ID)
async def ask_buttons(call: CallbackQuery, state: FSMContext):
    info = (
        "⌨ <b>Send Buttons in this format:</b>\n\n"
        "<code>Button Name - Link</code>\n"
        "<code>BOOMB - @Moneys_Factory1Bot</code>\n\n"
        "<i>Send multiple buttons line by line.</i>"
    )
    await call.message.edit_text(info, parse_mode="HTML", reply_markup=get_cancel_kb())
    await state.set_state(BroadcastState.waiting_for_buttons)

@router.callback_query(F.data == "cancel_input", F.from_user.id == ADMIN_ID)
async def cancel_input(call: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await call.message.delete()
    await call.message.answer("<b>📢 Broadcast Control Panel</b>", reply_markup=get_admin_dashboard_kb(), parse_mode="HTML")

# --- VIEW/PREVIEW HANDLERS ---

@router.callback_query(F.data == "view_media", F.from_user.id == ADMIN_ID)
async def view_media(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("bc_photo"):
        await call.message.answer_photo(photo=data["bc_photo"], caption="🖼 <b>Current Media Saved</b>", parse_mode="HTML")
    else:
        await call.answer("⚠️ No media set yet!", show_alert=True)

@router.callback_query(F.data == "view_text", F.from_user.id == ADMIN_ID)
async def view_text(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.answer(f"📝 <b>Current Text:</b>\n\n{data.get('bc_text')}", parse_mode="HTML")

@router.callback_query(F.data == "view_buttons", F.from_user.id == ADMIN_ID)
async def view_buttons(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("bc_buttons"):
        await call.message.answer("⌨ <b>Current Buttons:</b>", reply_markup=data["bc_buttons"], parse_mode="HTML")
    else:
        await call.answer("⚠️ No buttons set yet!", show_alert=True)

@router.callback_query(F.data == "view_full", F.from_user.id == ADMIN_ID)
async def view_full(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photo = data.get("bc_photo")
    text = data.get("bc_text")
    kb = data.get("bc_buttons")

    try:
        if photo:
            await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await call.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Preview Error: {e}")

# --- INPUT PROCESSING HANDLERS ---

@router.message(BroadcastState.waiting_for_media, F.from_user.id == ADMIN_ID)
async def process_media(message: Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        await state.update_data(bc_photo=file_id)
        await message.answer("✅ <b>Media Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
        await state.set_state(None)
    else:
        await message.answer("❌ Invalid Media. Please send a Photo.", reply_markup=get_cancel_kb())

@router.message(BroadcastState.waiting_for_text, F.from_user.id == ADMIN_ID)
async def process_text(message: Message, state: FSMContext):
    # message.html_text ব্যবহার করা হয়েছে যাতে ফরম্যাটিং নষ্ট না হয়
    await state.update_data(bc_text=message.html_text)
    await message.answer("✅ <b>Text Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
    await state.set_state(None)

@router.message(BroadcastState.waiting_for_buttons, F.from_user.id == ADMIN_ID)
async def process_buttons(message: Message, state: FSMContext):
    text_lines = message.text.split('\n')
    rows = []
    
    try:
        for line in text_lines:
            if '-' in line:
                # Button - Link আলাদা করা
                parts = line.split('-', 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                # Telegram username (@) হ্যান্ডেল করা
                if btn_url.startswith('@'):
                    btn_url = f"https://t.me/{btn_url[1:]}"
                elif not btn_url.startswith('http'):
                    btn_url = f"https://t.me/{btn_url}"
                
                rows.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        
        if rows:
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            await state.update_data(bc_buttons=kb)
            await message.answer("✅ <b>Buttons Saved!</b>", parse_mode="HTML", reply_markup=get_admin_dashboard_kb())
            await state.set_state(None)
        else:
            await message.answer("❌ No valid buttons found. Use format: `Name - Link`", parse_mode="HTML", reply_markup=get_cancel_kb())
            
    except Exception as e:
        await message.answer(f"❌ Error parsing buttons: {e}", reply_markup=get_cancel_kb())

# --- BROADCAST EXECUTION ---

@router.callback_query(F.data == "panel_next", F.from_user.id == ADMIN_ID)
async def confirm_broadcast(call: CallbackQuery):
    # কনফার্মেশন বাটন
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 START BROADCAST", callback_data="start_broadcast_now")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="panel_close")]
    ])
    users = get_all_users()
    await call.message.edit_text(f"⚠️ <b>Ready to send?</b>\n\nTarget Users: {len(users)}", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "start_broadcast_now", F.from_user.id == ADMIN_ID)
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.edit_text("⏳ <b>Broadcast Started! You will get a report soon.</b>", parse_mode="HTML")
    
    # ব্যাকগ্রাউন্ডে ব্রডকাস্ট রান করা
    asyncio.create_task(run_broadcast_background(data, call.from_user.id))
    await state.clear()

async def run_broadcast_background(data, admin_id):
    users = get_all_users()
    photo = data.get("bc_photo")
    text = data.get("bc_text")
    kb = data.get("bc_buttons")
    
    success = 0
    blocked = 0
    
    for user_id in users:
        try:
            if photo:
                await bot.send_photo(chat_id=user_id, photo=photo, caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=kb, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05) # FloodWait এড়াতে ডিলে
        except Exception:
            blocked += 1
            
    report = f"""
✅ <b>Broadcast Finished!</b>

📢 Total Sent: {success}
🚫 Blocked/Failed: {blocked}
    """
    await bot.send_message(chat_id=admin_id, text=report, parse_mode="HTML")

@router.callback_query(F.data == "panel_close")
async def close_panel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()

# --- STANDARD USER HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id)
    first_name = html.escape(message.from_user.first_name)
    
    text = f"❄️ <b>Welcome {first_name}!</b> ☃️\n\nTap the buttons below to start!"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message):
    # ইউজার কিছু লিখলে সাধারণ রিপ্লাই
    await message.answer("❄️ Use the buttons to interact!", reply_markup=get_main_keyboard())

# --- PAYMENT ---
@router.pre_checkout_query()
async def on_pre_checkout(query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("❄️ <b>Payment Received!</b>", parse_mode="HTML")

# --- SERVER ---
async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')
        if item_id in SHOP_ITEMS:
            item = SHOP_ITEMS[item_id]
            prices = [LabeledPrice(label=item_id, amount=item['price'])]
            link = await bot.create_invoice_link(
                title="Shop", description=item_id, payload=f"{user_id}_{item_id}",
                provider_token="", currency="XTR", prices=prices
            )
            return web.json_response({"result": link})
        return web.json_response({"error": "Item not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def home(request):
    return web.Response(text="Bot is Running!")

# --- LIFECYCLE ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
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
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()

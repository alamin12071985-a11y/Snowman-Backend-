import os
import sys
import logging
import asyncio
import sqlite3
import html
from datetime import datetime

# --- AIOGRAM IMPORTS ---
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, 
    CallbackQuery, Message, FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# --- OTHER IMPORTS ---
from aiohttp import web
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
ADMIN_ID = 7605281774  # আপনার নির্দিষ্ট অ্যাডমিন আইডি

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
        logging.info("✅ Database initialized successfully.")
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
        logging.error(f"⚠️ Failed to add user to DB: {e}")

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

# --- FSM STATES FOR BROADCAST ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_media = State()
    waiting_text = State()
    waiting_buttons = State()
    confirm_send = State()

# --- BOT INIT ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
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
            InlineKeyboardButton(text="❄️ Discussion Group 🥶", url="https://t.me/snowmanadventurediscuss")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_panel_kb():
    """আপনার স্ক্রিনশটের মত প্যানেল"""
    kb = [
        [
            InlineKeyboardButton(text="🖼 Media", callback_data="bd_set_media"),
            InlineKeyboardButton(text="👀 See", callback_data="bd_see_media")
        ],
        [
            InlineKeyboardButton(text="abc Text", callback_data="bd_set_text"),
            InlineKeyboardButton(text="👀 See", callback_data="bd_see_text")
        ],
        [
            InlineKeyboardButton(text="⌨ Buttons", callback_data="bd_set_buttons"),
            InlineKeyboardButton(text="👀 See", callback_data="bd_see_buttons")
        ],
        [
            InlineKeyboardButton(text="👀 Full preview", callback_data="bd_full_preview")
        ],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="bd_cancel"),
            InlineKeyboardButton(text="Next ➡️", callback_data="bd_start_send")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="bd_back_menu")]])

# --- USER HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    first_name = html.escape(message.from_user.first_name)
    add_user(user_id)
    
    text = f"❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️\n\nTap the Snowman, earn coins & enjoy! 🌨️"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- BROADCAST SYSTEM HANDLERS (ADMIN ONLY) ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return 
    
    # Reset state and init default data
    await state.clear()
    await state.update_data(media_id=None, media_type=None, text=None, buttons=[])
    
    await message.answer(
        "<b>📢 Broadcast Panel</b>\n\nSelect an option to configure your post:",
        reply_markup=get_broadcast_panel_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastState.menu)

# -- Navigation Handlers --

@router.callback_query(F.data == "bd_back_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.menu)
    await callback.message.edit_text(
        "<b>📢 Broadcast Panel</b>\n\nSelect an option to configure your post:",
        reply_markup=get_broadcast_panel_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "bd_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")

# -- Media Handlers --

@router.callback_query(F.data == "bd_set_media")
async def ask_media(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_media)
    await callback.message.edit_text(
        "🖼 <b>Send me an Image or Video</b> for the broadcast.\nOr click Back to cancel.",
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )

@router.message(StateFilter(BroadcastState.waiting_media), F.photo | F.video)
async def set_media(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        m_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        m_type = "video"
    else:
        return await message.answer("⚠️ Only Photo or Video supported.")

    await state.update_data(media_id=file_id, media_type=m_type)
    await message.answer("✅ Media set!", reply_markup=get_back_kb())

@router.callback_query(F.data == "bd_see_media")
async def see_media(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("media_id"):
        return await callback.answer("❌ No media set yet!", show_alert=True)
    
    if data['media_type'] == 'photo':
        await callback.message.answer_photo(data['media_id'], caption="🖼 Your Media")
    else:
        await callback.message.answer_video(data['media_id'], caption="📹 Your Media")

# -- Text Handlers --

@router.callback_query(F.data == "bd_set_text")
async def ask_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_text)
    await callback.message.edit_text(
        "📝 <b>Send the Text/Caption</b> for the broadcast.\nYou can use HTML tags.",
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )

@router.message(StateFilter(BroadcastState.waiting_text), F.text)
async def set_text_msg(message: types.Message, state: FSMContext):
    await state.update_data(text=message.html_text) # html_text preserves formatting
    await message.answer("✅ Text set!", reply_markup=get_back_kb())

@router.callback_query(F.data == "bd_see_text")
async def see_text(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("text", "❌ No text set yet.")
    await callback.message.answer(f"📝 <b>Current Text:</b>\n\n{text}", parse_mode="HTML")

# -- Button Handlers --

@router.callback_query(F.data == "bd_set_buttons")
async def ask_buttons(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_buttons)
    text = (
        "⌨ <b>Send Buttons in this format:</b>\n\n"
        "<code>Button Name-URL</code>\n\n"
        "Example:\n"
        "<code>Join Channel-https://t.me/channel</code>\n"
        "<code>My Bot-@MyBot</code>\n\n"
        "Send multiple lines for multiple buttons."
    )
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_buttons), F.text)
async def set_buttons_msg(message: types.Message, state: FSMContext):
    raw_lines = message.text.split('\n')
    buttons = []
    
    for line in raw_lines:
        if '-' in line:
            parts = line.split('-', 1)
            name = parts[0].strip()
            url = parts[1].strip()
            # Fix t.me short links if needed
            if url.startswith('@'):
                url = f"https://t.me/{url[1:]}"
            buttons.append({'text': name, 'url': url})
    
    if not buttons:
        return await message.answer("⚠️ Format incorrect. Try: Name-Link")
        
    await state.update_data(buttons=buttons)
    await message.answer(f"✅ {len(buttons)} Buttons set!", reply_markup=get_back_kb())

@router.callback_query(F.data == "bd_see_buttons")
async def see_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    buttons_data = data.get("buttons", [])
    
    if not buttons_data:
        return await callback.answer("❌ No buttons set!", show_alert=True)

    kb_rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons_data]
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    await callback.message.answer("⌨ <b>Buttons Preview:</b>", reply_markup=markup, parse_mode="HTML")

# -- Preview & Send --

@router.callback_query(F.data == "bd_full_preview")
async def full_preview(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get("media_id")
    text = data.get("text", "")
    buttons_data = data.get("buttons", [])
    
    kb_rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons_data]
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if buttons_data else None

    try:
        if media_id:
            if data['media_type'] == 'photo':
                await callback.message.answer_photo(media_id, caption=text, parse_mode="HTML", reply_markup=markup)
            else:
                await callback.message.answer_video(media_id, caption=text, parse_mode="HTML", reply_markup=markup)
        elif text:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)
        else:
            await callback.answer("⚠️ Nothing to preview (No Media or Text)", show_alert=True)
    except Exception as e:
        await callback.message.answer(f"⚠️ Preview Error: {e}")

@router.callback_query(F.data == "bd_start_send")
async def start_broadcasting(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if not data.get("text") and not data.get("media_id"):
        return await callback.answer("⚠️ Content is empty! Set text or media.", show_alert=True)
    
    users = get_all_users()
    total_users = len(users)
    await callback.message.edit_text(f"🚀 <b>Starting Broadcast to {total_users} users...</b>", parse_mode="HTML")
    
    # Run in background
    asyncio.create_task(run_broadcast(users, data, callback.from_user.id))
    await state.clear()

async def run_broadcast(users, data, admin_id):
    media_id = data.get("media_id")
    media_type = data.get("media_type")
    text = data.get("text", "")
    buttons_data = data.get("buttons", [])
    
    kb_rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons_data]
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if buttons_data else None
    
    sent = 0
    blocked = 0
    
    for user_id in users:
        try:
            if media_id:
                if media_type == 'photo':
                    await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, parse_mode="HTML", reply_markup=markup)
                else:
                    await bot.send_video(chat_id=user_id, video=media_id, caption=text, parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML", reply_markup=markup)
            
            sent += 1
            await asyncio.sleep(0.05) # Safe limit
            
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logging.error(f"Broadcast fail for {user_id}: {e}")
    
    await bot.send_message(admin_id, f"✅ <b>Broadcast Complete!</b>\n\nSent: {sent}\nBlocked: {blocked}\nTotal: {len(users)}", parse_mode="HTML")

# --- PAYMENT ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("❄️ <b>Payment Successful!</b>", parse_mode="HTML")

# --- SERVER ROUTES ---
async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')
        if item_id not in SHOP_ITEMS: return web.json_response({"error": "Item not found"}, status=404)
        item = SHOP_ITEMS[item_id]
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        link = await bot.create_invoice_link(title="Snowman Shop", description=item_id, payload=f"{user_id}_{item_id}", currency="XTR", prices=prices)
        return web.json_response({"result": link})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def home(request):
    return web.Response(text="⛄ Snowman Bot is Running! ❄️")

# --- LIFECYCLE ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    init_db()
    logging.info(f"✅ Webhook set: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    scheduler.shutdown()
    logging.info("🛑 Bot Stopped")

# --- MAIN ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/', home)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

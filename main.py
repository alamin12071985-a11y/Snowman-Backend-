import os
import sys
import logging
import asyncio
import json
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# --- ADMIN CONFIGURATION ---
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# Validation
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)
if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (Simple JSON) ---
DB_FILE = "users.json"

def load_users():
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        with open(DB_FILE, "w") as f:
            json.dump(list(users), f)

users_db = load_users()

# --- SHOP ITEMS (Stars XTR) ---
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

# --- FSM STATES ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# --- KEYBOARDS ---
def get_main_keyboard():
    # Update your bot username correctly in the URL if needed
    kb = [
        [InlineKeyboardButton(text="❄️ Play Game ☃️", url="https://t.me/snowmanadventurebot/SnowmanAdventure")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_menu(data):
    has_media = "✅ Set" if data.get('media_id') else "❌ Empty"
    has_text = "✅ Set" if data.get('text') else "❌ Empty"
    has_btn = "✅ Set" if data.get('buttons') else "❌ Empty"

    kb = [
        [
            InlineKeyboardButton(text=f"🖼️ Media", callback_data="br_media"),
            InlineKeyboardButton(text=f"👀 {has_media}", callback_data="br_dummy_media")
        ],
        [
            InlineKeyboardButton(text=f"📝 Text", callback_data="br_text"),
            InlineKeyboardButton(text=f"👀 {has_text}", callback_data="br_dummy_text")
        ],
        [
            InlineKeyboardButton(text=f"🔘 Buttons", callback_data="br_buttons"),
            InlineKeyboardButton(text=f"👀 {has_btn}", callback_data="br_dummy_btn")
        ],
        [InlineKeyboardButton(text="👀 Full Preview", callback_data="br_preview")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="br_cancel"),
            InlineKeyboardButton(text="Next ➡️", callback_data="br_send")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def parse_buttons(button_text):
    if not button_text:
        return None
    try:
        kb = []
        lines = button_text.split('\n')
        for line in lines:
            parts = line.split('-')
            if len(parts) >= 2:
                text = parts[0].strip()
                url = parts[1].strip()
                if url.startswith('@'):
                    url = f"https://t.me/{url[1:]}"
                elif not url.startswith('http'):
                    url = f"https://{url}"
                kb.append([InlineKeyboardButton(text=text, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except:
        return None

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    users_db.add(user_id)
    
    first_name = message.from_user.first_name
    
    # New Start Message
    text = f"""
❄️☃️ Hey {first_name}, Welcome to Snowman Adventure! ☃️❄️

Brrrr… the snow is falling and your journey starts RIGHT NOW! 🌨️✨

Tap the Snowman, earn shiny coins 💰, level up 🚀 and unlock cool rewards 🎁

Here’s what’s waiting for you 👇
➡️ Tap & earn coins ❄️
➡️ Complete daily tasks 🔑
➡️ Spin & win surprises 🎡
➡️ Invite friends and earn MORE 💫
➡️ Climb the leaderboard 🏆

Every tap matters.
Every coin counts.
And you are now part of the Snowman family 🤍☃️

So don’t wait…
👉 Start tapping, start winning, and enjoy the adventure! 🎮❄️
    """
    await message.answer(text, reply_markup=get_main_keyboard())

# Handler for generic text (Reply Message)
@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    users_db.add(user_id)
    
    first_name = message.from_user.first_name
    
    # New Reply Message
    text = f"""
❄️☃️ Hey {first_name}, Welcome Back to Snowman Adventure! ☃️❄️

Snowman heard you typing… and got excited! 😄💫
That means it’s time to jump back into the icy fun ❄️🎮

What’s waiting for you right now 👇
➡️ Tap the Snowman & earn coins 💰
➡️ Complete tasks for instant rewards 🎯
➡️ Spin and win surprises 🎡
➡️ Invite friends & grow faster 👥
➡️ Chase the top of the leaderboard 🏆

Every click brings progress.
Every moment brings rewards. 🌟

Choose your next move below and keep the adventure going ⬇️

❄️ Stay cool. Keep tapping.
Snowman Adventure never sleeps! ☃️🔥
    """
    await message.answer(text, reply_markup=get_main_keyboard())

# --- BROADCAST HANDLERS ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.update_data(media_id=None, text=None, buttons=None)
    await message.answer("📢 **Broadcast Menu**", reply_markup=get_broadcast_menu({}), parse_mode="Markdown")
    await state.set_state(BroadcastState.menu)

@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼️ **Send photo** (or send text to cancel)", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_media)

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 **Send caption/text**", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_text)

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    msg = "🔘 **Send buttons format:**\n`Text-URL`\n\nExample:\n`Play-https://t.me/bot`"
    await call.message.edit_text(msg, parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_buttons)

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState.menu))
async def cb_cancel_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast setup cancelled.")

@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text') or "No text set."
    btn_markup = parse_buttons(data.get('buttons'))
    try:
        if media_id:
            await call.message.answer_photo(photo=media_id, caption=text, reply_markup=btn_markup)
        else:
            await call.message.answer(text=text, reply_markup=btn_markup)
        await call.message.answer("☝️ Preview. Edit or Send.", reply_markup=get_broadcast_menu(data))
    except Exception as e:
        await call.answer(f"Error: {str(e)}", show_alert=True)

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text')
    buttons_raw = data.get('buttons')
    
    if not text and not media_id:
        await call.answer("❌ Set Text or Media first!", show_alert=True)
        return

    await call.message.edit_text("⏳ Sending broadcast... This may take time.")
    markup = parse_buttons(buttons_raw)
    count = 0
    blocked = 0
    users_list = list(users_db)

    for user_id in users_list:
        try:
            if media_id:
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
            count += 1
            await asyncio.sleep(0.05) 
        except Exception:
            blocked += 1
    
    await call.message.answer(f"✅ Broadcast Complete!\n\n👥 Sent: {count}\n🚫 Failed: {blocked}")
    await state.clear()

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def input_media(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(media_id=photo_id)
    data = await state.get_data()
    await message.answer("✅ Image Set!", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def input_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    data = await state.get_data()
    await message.answer("✅ Text Set!", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def input_buttons(message: types.Message, state: FSMContext):
    if parse_buttons(message.text) is None:
        await message.answer("❌ Invalid format! Try `Text-URL`")
        return
    await state.update_data(buttons=message.text)
    data = await state.get_data()
    await message.answer("✅ Buttons Set!", reply_markup=get_broadcast_menu(data))
    await state.set_state(BroadcastState.menu)

# --- PAYMENT HANDLERS ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("✅ Payment Successful! Item added.")

# --- WEBHOOK ---
async def on_startup(bot: Bot):
    logging.info(f"🔗 Setting webhook to: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    logging.info("🔌 Deleting webhook...")
    await bot.delete_webhook()

# --- CORS HELPER ---
def cors_response(data, status=200):
    return web.json_response(
        data,
        status=status,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

async def options_handler(request):
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# --- API ENDPOINTS ---

async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if item_id not in SHOP_ITEMS:
            return cors_response({"error": "Item not found"}, status=404)

        item = SHOP_ITEMS[item_id]
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", 
            currency="XTR",
            prices=prices,
        )
        return cors_response({"result": link})
    except Exception as e:
        logging.error(f"Invoice Error: {e}")
        return cors_response({"error": str(e)}, status=500)

async def verify_join_api(request):
    """
    Checks if a user has joined the required Channel and Group with detailed logging.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "No user ID"}, status=400)

        # Ensure user_id is an integer
        try:
            user_id = int(user_id)
        except ValueError:
            return cors_response({"joined": False, "error": "Invalid User ID"})

        # Valid statuses including 'restricted'
        valid_statuses = ['member', 'administrator', 'creator', 'restricted']

        # --- CHECK CHANNEL ---
        channel_joined = False
        try:
            chat_member_ch = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
            status_ch = chat_member_ch.status
            logging.info(f"👤 User {user_id} Channel Status: {status_ch}") 
            
            if status_ch in valid_statuses:
                channel_joined = True
            elif status_ch == 'left':
                logging.warning(f"❌ User {user_id} has LEFT the channel.")
            elif status_ch == 'kicked':
                logging.warning(f"🚫 User {user_id} is BANNED from channel.")
                
        except TelegramBadRequest as e:
            logging.error(f"⚠️ Channel Check Failed (Bot Admin?): {e}")
            channel_joined = False
        except Exception as e:
            logging.error(f"⚠️ Channel Error: {e}")
            channel_joined = False

        # --- CHECK GROUP ---
        group_joined = False
        try:
            chat_member_gr = await bot.get_chat_member(chat_id=GROUP_USERNAME, user_id=user_id)
            status_gr = chat_member_gr.status
            logging.info(f"👤 User {user_id} Group Status: {status_gr}") 
            
            if status_gr in valid_statuses:
                group_joined = True
            elif status_gr == 'left':
                logging.warning(f"❌ User {user_id} has LEFT the group.")
                
        except TelegramBadRequest as e:
            logging.error(f"⚠️ Group Check Failed (Bot Admin?): {e}")
            group_joined = False
        except Exception as e:
            logging.error(f"⚠️ Group Error: {e}")
            group_joined = False

        # --- FINAL DECISION ---
        if channel_joined and group_joined:
            logging.info(f"✅ User {user_id} verified successfully!")
            return cors_response({"joined": True})
        else:
            logging.info(f"⛔ Verification Failed for {user_id}. Ch: {channel_joined}, Gr: {group_joined}")
            return cors_response({"joined": False})
            
    except Exception as e:
        logging.error(f"🔥 Verify API Critical Error: {e}")
        return cors_response({"error": str(e)}, status=500)

async def home(request):
    return web.Response(text="⛄ Snowman Adventure Backend is Running! ❄️")

# --- APP EXECUTION ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)
    
    app.router.add_get('/', home)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

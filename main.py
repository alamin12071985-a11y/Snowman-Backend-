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
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# --- ADMIN CONFIGURATION ---
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# --- VALIDATION ---
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)
if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing!")
    sys.exit(1)

APP_URL = APP_URL.rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (Simple JSON) ---
DB_FILE = "users.json"

def load_users():
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r") as f:
            content = f.read()
            if not content: return set()
            return set(json.loads(content))
    except Exception as e:
        logging.error(f"⚠️ Error loading DB: {e}")
        return set()

def save_user(user_id):
    """Saves user only if new to avoid blocking IO."""
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                json.dump(list(users), f)
            logging.info(f"🆕 New user saved: {user_id}")
    except Exception as e:
        logging.error(f"❌ Error saving user: {e}")

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
    kb = [
        [InlineKeyboardButton(text="❄️ Play Game ☃️", url=f"https://t.me/snowmanadventurebot/app")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_menu(data):
    """Admin Broadcast Menu."""
    has_media = "✅ Set" if data.get('media_id') else "❌ Empty"
    has_text = "✅ Set" if data.get('text') else "❌ Empty"
    has_btn = "✅ Set" if data.get('buttons') else "❌ Empty"

    kb = [
        [
            InlineKeyboardButton(text=f"🖼️ Media ({has_media})", callback_data="br_media"),
            InlineKeyboardButton(text=f"📝 Text ({has_text})", callback_data="br_text")
        ],
        [
            InlineKeyboardButton(text=f"🔘 Buttons ({has_btn})", callback_data="br_buttons")
        ],
        [
            InlineKeyboardButton(text="👀 Preview", callback_data="br_preview"),
            InlineKeyboardButton(text="🚀 Send Broadcast", callback_data="br_send")
        ],
        [InlineKeyboardButton(text="🔙 Cancel / Close", callback_data="br_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="br_back")]])

def parse_buttons(button_text):
    if not button_text: return None
    try:
        kb = []
        lines = button_text.split('\n')
        for line in lines:
            if '-' in line:
                text, url = line.split('-', 1)
                kb.append([InlineKeyboardButton(text=text.strip(), url=url.strip())])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except:
        return None

# ==========================================
#  HANDLERS
# ==========================================

# --- START & USER ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    first_name = message.from_user.first_name
    
    text = f"❄️☃️ <b>Hey {first_name}, Welcome to Snowman Adventure!</b> ☃️❄️\n\nTap the Snowman, earn coins, and unlock rewards! 🎁"
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# --- ADMIN BROADCAST (STANDARDIZED) ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.set_state(BroadcastState.menu)
    await message.answer("📢 **Broadcast Panel**\nSelect an option to configure:", reply_markup=get_broadcast_menu({}), parse_mode="Markdown")

@router.callback_query(F.data == "br_back", StateFilter(BroadcastState))
async def cb_back_to_menu(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await call.message.edit_text("📢 **Broadcast Panel**\nSelect an option to configure:", reply_markup=get_broadcast_menu(data), parse_mode="Markdown")

@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast cancelled.")

# -- Media Input --
@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_media)
    await call.message.edit_text("🖼️ **Send me the photo now.**", reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def input_media(message: types.Message, state: FSMContext):
    await state.update_data(media_id=message.photo[-1].file_id)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ **Media Saved!**", reply_markup=get_broadcast_menu(data), parse_mode="Markdown")

# -- Text Input --
@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    await call.message.edit_text("📝 **Send the text/caption now.**", reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def input_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ **Text Saved!**", reply_markup=get_broadcast_menu(data), parse_mode="Markdown")

# -- Buttons Input --
@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_buttons)
    await call.message.edit_text("🔘 **Send buttons:** `Name-URL`\nExample: `Play-https://t.me/bot`", reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def input_buttons(message: types.Message, state: FSMContext):
    if parse_buttons(message.text) is None:
        await message.answer("❌ Invalid format. Try again or Cancel.")
        return
    await state.update_data(buttons=message.text)
    data = await state.get_data()
    await state.set_state(BroadcastState.menu)
    await message.answer("✅ **Buttons Saved!**", reply_markup=get_broadcast_menu(data), parse_mode="Markdown")

# -- Preview --
@router.callback_query(F.data == "br_preview", StateFilter(BroadcastState.menu))
async def cb_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media, text, btns = data.get('media_id'), data.get('text'), parse_buttons(data.get('buttons'))
    
    try:
        if media:
            await call.message.answer_photo(photo=media, caption=text or "No text", reply_markup=btns)
        elif text:
            await call.message.answer(text=text, reply_markup=btns)
        else:
            await call.answer("Nothing to preview!", show_alert=True)
            return
        # Re-show menu
        await call.message.answer("👆 **Preview above.** Ready?", reply_markup=get_broadcast_menu(data), parse_mode="Markdown")
    except Exception as e:
        await call.answer(f"Preview Error: {e}", show_alert=True)

# -- SEND (Background Task) --
async def run_broadcast_task(chat_id, data):
    """Background function to send messages."""
    media, text, btns_raw = data.get('media_id'), data.get('text'), data.get('buttons')
    markup = parse_buttons(btns_raw)
    users = load_users()
    count, blocked = 0, 0
    
    await bot.send_message(chat_id, "🚀 Broadcast started in background...")
    
    for uid in users:
        try:
            if media:
                await bot.send_photo(uid, photo=media, caption=text, reply_markup=markup)
            elif text:
                await bot.send_message(uid, text=text, reply_markup=markup)
            count += 1
            await asyncio.sleep(0.05) # Prevent flood wait
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            pass
            
    await bot.send_message(chat_id, f"✅ **Broadcast Finished!**\n\nSent: {count}\nBlocked: {blocked}", parse_mode="Markdown")

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('text') and not data.get('media_id'):
        await call.answer("Empty broadcast! Set text or media.", show_alert=True)
        return

    await call.message.edit_text("⏳ Processing request...")
    # Run in background to prevent bot Timeout/Freezing
    asyncio.create_task(run_broadcast_task(call.message.chat.id, data))
    await state.clear()

# --- PAYMENTS ---
@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    await message.answer("✅ Payment Successful! Reward added in-game.")

# --- API ENDPOINTS ---
async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id, user_id = data.get('item_id'), data.get('user_id')
        if item_id not in SHOP_ITEMS: return web.json_response({"error": "Item not found"}, status=404)
        
        item = SHOP_ITEMS[item_id]
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        link = await bot.create_invoice_link(
            title="Snowman Shop", description=f"Buy {item_id}", payload=f"{user_id}_{item_id}",
            provider_token="", currency="XTR", prices=prices
        )
        return web.json_response({"result": link})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def verify_join_api(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id'))
        # Check Channel & Group
        m1 = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        m2 = await bot.get_chat_member(GROUP_USERNAME, user_id)
        valid = ['member', 'administrator', 'creator']
        if m1.status in valid and m2.status in valid:
            return web.json_response({"joined": True})
        return web.json_response({"joined": False})
    except:
        return web.json_response({"joined": False})

async def home(request):
    return web.Response(text="Bot is running!")

async def cors_options(request):
    return web.Response(headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})

# --- LIFECYCLE ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"✅ Webhook set: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

# --- MAIN ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    app = web.Application()
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/create_invoice', cors_options)
    app.router.add_options('/verify_join', cors_options)
    app.router.add_get('/', home)

    # Attach Dispatcher
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()

import os
import sys
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- CONFIGURATION (ENV VARS) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# --- ADMIN CONFIGURATION ---
ADMIN_ID = 7605281774  # আপনার অ্যাডমিন আইডি

# ভেরিয়েবল চেক
if not BOT_TOKEN:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)
if not APP_URL:
    logging.error("❌ CRITICAL ERROR: APP_URL is missing!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# --- DATABASE (SIMPLE MEMORY SET) ---
# নোট: সার্ভার রিস্টার্ট দিলে এই ডাটা মুছে যাবে। পার্মানেন্ট করার জন্য SQL Database প্রয়োজন।
users_db = set()

# --- SHOP CONFIGURATION ---
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

# --- FSM STATES FOR BROADCAST ---
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()

# --- BOT INITIALIZATION ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# --- KEYBOARDS ---
def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="❄️ Start App ☃️", url="https://t.me/snowmanadventurebot?startapp=8244641590")],
        [
            InlineKeyboardButton(text="❄️ Channel 🎯", url="https://t.me/snowmanadventureannouncement"),
            InlineKeyboardButton(text="❄️ Group 🥶", url="https://t.me/snowmanadventuregroup")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_menu(data):
    """ব্রডকাস্ট কন্ট্রোল প্যানেল তৈরি করে"""
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
    """টেক্সট থেকে ইনলাইন বাটন তৈরি করে (Format: Text-URL)"""
    if not button_text:
        return None
    try:
        kb = []
        # কমা বা নতুন লাইন দিয়ে একাধিক বাটন হ্যান্ডেল করা যাবে
        lines = button_text.split('\n')
        for line in lines:
            parts = line.split('-')
            if len(parts) >= 2:
                text = parts[0].strip()
                url = parts[1].strip()
                # ইউজারনেম থাকলে লিংক ঠিক করা
                if url.startswith('@'):
                    url = f"https://t.me/{url[1:]}"
                elif not url.startswith('http'):
                    url = f"https://{url}"
                kb.append([InlineKeyboardButton(text=text, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except:
        return None

# --- BASIC HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # ইউজার ডাটাবেসে সেভ করা (মেমোরি)
    users_db.add(message.from_user.id)
    
    first_name = message.from_user.first_name
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

Every tap matters. Every coin counts.
And you are now part of the Snowman family 🤍☃️
So don’t wait…
👉 Start tapping, start winning, and enjoy the adventure! 🎮❄️
    """
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(F.text & ~F.text.startswith("/"))
async def echo_all(message: types.Message, state: FSMContext):
    # যদি ব্রডকাস্ট মোডে থাকে তবে এই হ্যান্ডলার কাজ করবে না
    current_state = await state.get_state()
    if current_state:
        return

    users_db.add(message.from_user.id)
    first_name = message.from_user.first_name
    text = f"""
❄️☃️ Hey {first_name}, Welcome Back to Snowman Adventure! ☃️❄️
Snowman heard you typing… and got excited! 😄💫
Click below to start playing!
    """
    await message.answer(text, reply_markup=get_main_keyboard())

# --- BROADCAST SYSTEM HANDLERS ---

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return # সাইলেন্ট রিজেক্ট
    
    # স্টেট ক্লিয়ার এবং ডিফল্ট ডাটা সেট
    await state.clear()
    await state.update_data(media_id=None, text=None, buttons=None)
    
    text = "📢 **Broadcast Menu**\n\nConfigure your broadcast below using the buttons."
    await message.answer(text, reply_markup=get_broadcast_menu({}), parse_mode="Markdown")
    await state.set_state(BroadcastState.menu)

# -- Menu Callback Handlers --

@router.callback_query(F.data == "br_media", StateFilter(BroadcastState.menu))
async def cb_ask_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼️ **Send me the photo/image** you want to attach.\n(Send text to cancel)", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_media)

@router.callback_query(F.data == "br_text", StateFilter(BroadcastState.menu))
async def cb_ask_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 **Send me the caption/text** for the post.", parse_mode="Markdown")
    await state.set_state(BroadcastState.waiting_for_text)

@router.callback_query(F.data == "br_buttons", StateFilter(BroadcastState.menu))
async def cb_ask_buttons(call: CallbackQuery, state: FSMContext):
    msg = """
🔘 **Send me the button in this format:**
`Text-URL`

Example:
`BOOMB-@Moneys_Factory1Bot`
or
`Join Channel-https://t.me/example`

(Send one line per button)
    """
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
        
        # প্রিভিউ দেখানোর পর আবার মেনু শো করা
        await call.message.answer("☝️ Here is the preview. Use the menu above to edit or send.", reply_markup=get_broadcast_menu(data))
    except Exception as e:
        await call.answer(f"Error in preview: {str(e)}", show_alert=True)

@router.callback_query(F.data == "br_send", StateFilter(BroadcastState.menu))
async def cb_send_broadcast(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text')
    buttons_raw = data.get('buttons')
    
    if not text and not media_id:
        await call.answer("❌ Nothing to send! Set Text or Media.", show_alert=True)
        return

    # কনফার্মেশন শুরু
    await call.message.edit_text("⏳ Sending broadcast... Do not touch anything.")
    
    markup = parse_buttons(buttons_raw)
    count = 0
    blocked = 0
    
    # ব্রডকাস্ট লুপ
    for user_id in users_db:
        try:
            if media_id:
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=markup)
            else:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
            count += 1
            await asyncio.sleep(0.05) # ফ্লাড লিমিট এড়াতে
        except Exception as e:
            blocked += 1
    
    await call.message.answer(f"✅ Broadcast Complete!\n\n👥 Sent to: {count}\n🚫 Blocked/Failed: {blocked}")
    await state.clear()

# -- Input Listeners --

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
    # ভ্যালিডেশন চেক
    if parse_buttons(message.text) is None:
        await message.answer("❌ Invalid format! Please use `Text-URL` format.\nTry again:")
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
    await message.answer("❄️ Payment Successful! Your items have been added. Restart the game to see changes! ☃️")

# --- WEBHOOK TRIGGERS ---
async def on_startup(bot: Bot):
    logging.info(f"🔗 Setting webhook to: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    logging.info("🔌 Deleting webhook...")
    await bot.delete_webhook()

# --- API ROUTES ---

async def create_invoice_api(request):
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if item_id not in SHOP_ITEMS:
            return web.json_response({"error": "Item not found"}, status=404)

        item = SHOP_ITEMS[item_id]
        prices = [LabeledPrice(label=item_id, amount=item['price'])]
        
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id}",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Stars currency
            currency="XTR",
            prices=prices,
        )
        return web.json_response({"result": link})
    except Exception as e:
        logging.error(f"Invoice Error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def trigger_broadcast_api(request):
    # API দিয়ে ব্রডকাস্ট (Legacy support)
    chat_id = request.rel_url.query.get('chat_id')
    caption = "❄️🚨 Daily Rewards are waiting! Log in now! 🚨❄️"
    photo_file_id = "AgACAgUAAxkBAAE_9f1pVL83a2yTeglyOW1P3rQRmcT0iwACpwtrGxjJmVYBpQKTP5TwDQEAAwIAA3kAAzgE"
    
    try:
        if chat_id:
            await bot.send_photo(chat_id=chat_id, photo=photo_file_id, caption=caption, reply_markup=get_main_keyboard())
            return web.Response(text=f"Broadcast sent to {chat_id}")
        else:
            return web.Response(text="API Broadcast Active. Use /broadcast in bot for mass sending.")
    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)

async def home(request):
    return web.Response(text="⛄ Snowman Adventure Backend is Running Successfully! ❄️")

# --- MAIN APP EXECUTION ---
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_get('/broadcast', trigger_broadcast_api)
    app.router.add_get('/', home)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

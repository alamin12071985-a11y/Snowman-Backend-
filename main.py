import os
import sys
import logging
import asyncio
import json
import random
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, StateFilter, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    LabeledPrice, 
    CallbackQuery, 
    PreCheckoutQuery, 
    Message,
    FSInputFile
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ==============================================================================
#  1. LOGGING & CONFIGURATION & ENVIRONMENT VARIABLES
# ==============================================================================

# Configure logging to see detailed output in console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Load Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

# Admin & Channel Configuration
# Replace these with your actual IDs
ADMIN_ID = 7605281774  
CHANNEL_USERNAME = "@snowmanadventureannouncement" 
GROUP_USERNAME = "@snowmanadventuregroup" 

# Critical Validation: Stop server if config is missing
if not BOT_TOKEN or not APP_URL:
    logging.error("❌ CRITICAL ERROR: BOT_TOKEN or APP_URL is missing! Please set them in Environment Variables.")
    # In a real production environment, you might want to exit here:
    # sys.exit(1) 

# URL Formatting for Webhook
# Removes trailing slash if present to avoid double slashes like https://url.com//webhook
APP_URL = str(APP_URL).rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

# ==============================================================================
#  2. DATABASE SYSTEM (JSON FILE BASED)
# ==============================================================================

DB_FILE = "users.json"

def load_users():
    """
    Loads user IDs from the JSON file safely.
    Returns a set of user IDs.
    """
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r") as f:
            content = f.read()
            if not content:
                return set()
            data = json.loads(content)
            # Ensure we return a set for unique IDs
            return set(data)
    except Exception as e:
        logging.error(f"⚠️ Database Load Error: {e}")
        return set()

def save_user(user_id):
    """
    Saves a new user ID to the database if it doesn't exist.
    """
    try:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(DB_FILE, "w") as f:
                # Convert set back to list for JSON serialization
                json.dump(list(users), f)
            logging.info(f"🆕 New User Added to Database: {user_id}")
    except Exception as e:
        logging.error(f"❌ Database Save Error: {e}")

# ==============================================================================
#  3. GAME DATA & SHOP CONFIGURATION
# ==============================================================================

# Shop Items for Telegram Stars (XTR)
# Used for generating invoices
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

# Spin Prizes (Backend Controlled Logic)
# These values are sent to the frontend when a user spins
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

# ==============================================================================
#  4. STATES & BOT INITIALIZATION
# ==============================================================================

# Finite State Machine for Broadcast Wizard
class BroadcastState(StatesGroup):
    menu = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_buttons = State()
    confirm_send = State()

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Register the router to the dispatcher
dp.include_router(router)

# ==============================================================================
#  5. KEYBOARD & UI HELPERS
# ==============================================================================

def get_main_keyboard():
    """Returns the main menu keyboard for /start"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Play Snowman Adventure ☃️", url="https://t.me/snowmanadventurebot/app")],
        [
            InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="💬 Group", url=f"https://t.me/{GROUP_USERNAME.replace('@', '')}")
        ]
    ])

def get_broadcast_start_kb():
    """Initial menu for Broadcast Wizard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Start with Image/Media", callback_data="br_start_media")],
        [InlineKeyboardButton(text="📝 Start with Text Only", callback_data="br_start_text")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="br_cancel")]
    ])

def get_nav_buttons(next_callback, back_callback):
    """Generic navigation buttons (Next / Back)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Next", callback_data=next_callback)],
        [InlineKeyboardButton(text="🔙 Back", callback_data=back_callback)]
    ])

def get_final_confirm_kb():
    """Confirmation buttons before sending broadcast"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Broadcast to All Users", callback_data="br_final_send")],
        [InlineKeyboardButton(text="🔙 Edit / Restart", callback_data="br_restart")]
    ])

def parse_buttons(text):
    """
    Parses a string of text to create inline buttons.
    Format expected: Button Text - URL
    """
    if not text: 
        return None
    try:
        kb = []
        for line in text.split('\n'):
            if '-' in line:
                parts = line.split('-', 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                if btn_text and btn_url:
                    kb.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        if not kb:
            return None
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except Exception as e:
        logging.error(f"Button Parsing Error: {e}")
        return None

# ==============================================================================
#  6. BOT HANDLERS (TELEGRAM COMMANDS & EVENTS)
# ==============================================================================

# --- /start Command Handler (Corrected) ---
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """
    Handles the /start command.
    1. Logs the user interaction.
    2. Saves the user to the JSON database.
    3. Sends a welcome message with the Web App button.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    logging.info(f"🟢 Start command received from User ID: {user_id} ({first_name})")
    
    try:
        # Save user logic
        save_user(user_id)
        
        welcome_text = (
            f"❄️☃️ <b>Hello, {first_name}!</b> ☃️❄️\n\n"
            "Welcome to <b>Snowman Adventure!</b> 🌨️\n"
            "Tap, earn coins, upgrade levels and invite friends!\n\n"
            "👇 <b>Click below to start playing:</b>"
        )
        
        await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    except Exception as e:
        logging.error(f"🔴 Error in /start handler: {e}")

# --- PAYMENT HANDLERS (Telegram Stars) ---

@router.pre_checkout_query()
async def checkout_handler(checkout_query: PreCheckoutQuery):
    """
    Validates the checkout before payment is processed.
    Always returns True for digital goods in this context.
    """
    await bot.answer_pre_checkout_query(checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    """
    Triggered when a payment is successful.
    Sends a confirmation to the user.
    """
    logging.info(f"💰 Payment Successful by User: {message.from_user.id}")
    await message.answer("✅ <b>Payment Successful!</b>\nYour items have been added to your account.", parse_mode="HTML")


# ==============================================================================
#  7. BROADCAST SYSTEM (ADMIN WIZARD)
# ==============================================================================

@router.message(Command("broadcast"))
async def broadcast_command(message: types.Message, state: FSMContext):
    """
    Initiates the broadcast wizard. Only accessible by ADMIN_ID.
    """
    if message.from_user.id != ADMIN_ID:
        # Silently ignore if not admin
        return 
    
    # Clear any previous state
    await state.clear()
    
    await message.answer(
        "📢 <b>Broadcast Wizard</b>\n\nChoose how you want to start your post:", 
        reply_markup=get_broadcast_start_kb(), 
        parse_mode="HTML"
    )

# -- Cancel Broadcast --
@router.callback_query(F.data == "br_cancel", StateFilter(BroadcastState))
async def cancel_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Broadcast operation cancelled.")

# -- Restart Broadcast --
@router.callback_query(F.data == "br_restart", StateFilter(BroadcastState))
async def restart_broadcast(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "📢 <b>Broadcast Wizard (Restarted)</b>\n\nChoose start option:", 
        reply_markup=get_broadcast_start_kb(), 
        parse_mode="HTML"
    )

# --- STEP 1: MEDIA SELECTION ---

@router.callback_query(F.data == "br_start_media")
async def start_with_media(call: CallbackQuery, state: FSMContext):
    """Admin chose to send media first."""
    await state.set_state(BroadcastState.waiting_for_media)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="br_restart")]])
    await call.message.edit_text("1️⃣ <b>Step 1: Send your Image/Video</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "br_start_text")
async def start_with_text(call: CallbackQuery, state: FSMContext):
    """Admin chose to send text only."""
    # Set media_id to None in state
    await state.update_data(media_id=None)
    await state.set_state(BroadcastState.waiting_for_text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="br_restart")]])
    await call.message.edit_text("2️⃣ <b>Step 2: Enter your Caption/Text</b>", reply_markup=kb, parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_media), F.photo)
async def media_received(message: types.Message, state: FSMContext):
    """Handles receiving the image."""
    # Get the highest quality photo file_id
    file_id = message.photo[-1].file_id
    await state.update_data(media_id=file_id)
    
    kb = get_nav_buttons(next_callback="goto_text", back_callback="br_restart")
    await message.answer("✅ Media Received!\n\n👇 Click <b>Next</b> to set text/caption, or Back to change media.", reply_markup=kb, parse_mode="HTML")

# --- STEP 2: TEXT/CAPTION SELECTION ---

@router.callback_query(F.data == "goto_text", StateFilter(BroadcastState))
async def step_text_prompt(call: CallbackQuery, state: FSMContext):
    """Prompt for text input."""
    await state.set_state(BroadcastState.waiting_for_text)
    
    # Determine back button behavior based on whether media was uploaded
    data = await state.get_data()
    back_cb = "br_start_media" if data.get('media_id') else "br_restart"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data=back_cb)]])
    await call.message.edit_text("2️⃣ <b>Step 2: Enter your Caption/Text</b>", reply_markup=kb, parse_mode="HTML")

@router.message(StateFilter(BroadcastState.waiting_for_text), F.text)
async def text_received(message: types.Message, state: FSMContext):
    """Handles receiving the caption or message text."""
    await state.update_data(text=message.text)
    
    kb = get_nav_buttons(next_callback="goto_buttons", back_callback="goto_text_retry")
    await message.answer("✅ Text Saved!\n\n👇 Click <b>Next</b> to set buttons.", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "goto_text_retry", StateFilter(BroadcastState))
async def text_retry(call: CallbackQuery, state: FSMContext):
    """Go back to text input step."""
    await step_text_prompt(call, state)

# --- STEP 3: BUTTONS SELECTION ---

@router.callback_query(F.data == "goto_buttons", StateFilter(BroadcastState))
async def step_buttons_prompt(call: CallbackQuery, state: FSMContext):
    """Prompt for buttons input."""
    await state.set_state(BroadcastState.waiting_for_buttons)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Skip (No Buttons)", callback_data="goto_preview")],
        [InlineKeyboardButton(text="🔙 Back to Text", callback_data="goto_text_retry")]
    ])
    
    msg = (
        "3️⃣ <b>Step 3: Add Buttons (Optional)</b>\n\n"
        "Send buttons in this exact format:\n"
        "`Button Text - https://link.com`\n\n"
        "Multiple buttons on new lines:\n"
        "`Play Now - https://t.me/mybot/app`\n"
        "`Join Channel - https://t.me/channel`"
    )
    await call.message.edit_text(msg, reply_markup=kb, parse_mode="Markdown")

@router.message(StateFilter(BroadcastState.waiting_for_buttons), F.text)
async def buttons_received(message: types.Message, state: FSMContext):
    """Handles parsing and saving buttons."""
    parsed = parse_buttons(message.text)
    if not parsed:
        await message.answer("❌ <b>Invalid Format!</b>\nPlease use: `Text - URL`", parse_mode="HTML")
        return

    await state.update_data(buttons=message.text)
    
    kb = get_nav_buttons(next_callback="goto_preview", back_callback="goto_buttons")
    await message.answer("✅ Buttons Saved!\n\n👇 Click <b>Next</b> to Preview.", reply_markup=kb, parse_mode="HTML")

# --- STEP 4: PREVIEW ---

@router.callback_query(F.data == "goto_preview", StateFilter(BroadcastState))
async def step_preview(call: CallbackQuery, state: FSMContext):
    """Generates a preview of the message."""
    data = await state.get_data()
    media_id = data.get('media_id')
    text = data.get('text')
    buttons_raw = data.get('buttons')
    
    kb = parse_buttons(buttons_raw)
    
    await call.message.answer("---------- PREVIEW START ----------")
    
    try:
        if media_id:
            await call.message.answer_photo(photo=media_id, caption=text, reply_markup=kb)
        elif text:
            await call.message.answer(text=text, reply_markup=kb)
        else:
            await call.message.answer("⚠️ Empty Message Error! No text and no media.")
    except Exception as e:
        await call.message.answer(f"⚠️ Preview Failed: {e}")
        
    await call.message.answer("---------- PREVIEW END ----------")
    
    # Show Final Confirmation
    await call.message.answer("👆 <b>Preview is above.</b> Ready to send to all users?", reply_markup=get_final_confirm_kb(), parse_mode="HTML")

# --- STEP 5: EXECUTE BROADCAST ---

async def perform_broadcast_task(admin_chat_id, data):
    """
    Background Async Task to loop through users and send messages.
    Handles rate limiting and blocked users.
    """
    media_id = data.get('media_id')
    text = data.get('text')
    kb = parse_buttons(data.get('buttons'))
    users = load_users()
    
    sent_count = 0
    blocked_count = 0
    error_count = 0
    
    await bot.send_message(admin_chat_id, f"🚀 <b>Broadcast Started!</b>\nTarget Users: {len(users)}", parse_mode="HTML")
    
    for user_id in users:
        try:
            if media_id:
                await bot.send_photo(chat_id=user_id, photo=media_id, caption=text, reply_markup=kb)
            elif text:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            
            sent_count += 1
            # Rate limit to avoid flooding (approx 25 messages/sec)
            await asyncio.sleep(0.04) 
            
        except TelegramForbiddenError:
            # User blocked the bot
            blocked_count += 1
        except TelegramBadRequest as e:
            error_count += 1
            logging.warning(f"Bad Request for {user_id}: {e}")
        except Exception as e:
            error_count += 1
            logging.error(f"Broadcast Error for {user_id}: {e}")
            
    # Final Report to Admin
    await bot.send_message(
        admin_chat_id, 
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"📨 Sent: {sent_count}\n"
        f"🚫 Blocked: {blocked_count}\n"
        f"⚠️ Errors: {error_count}", 
        parse_mode="HTML"
    )

@router.callback_query(F.data == "br_final_send", StateFilter(BroadcastState))
async def execute_broadcast(call: CallbackQuery, state: FSMContext):
    """Triggers the background broadcast task."""
    data = await state.get_data()
    
    if not data.get('text') and not data.get('media_id'):
        await call.answer("⚠️ Message cannot be empty!", show_alert=True)
        return

    await call.message.edit_text("⏳ <b>Sending broadcast in background...</b>\nYou will receive a detailed report soon.", parse_mode="HTML")
    
    # Launch background task
    asyncio.create_task(perform_broadcast_task(call.message.chat.id, data))
    
    # Clear state
    await state.clear()


# ==============================================================================
#  8. API ENDPOINTS (BACKEND LOGIC FOR MINI APP)
# ==============================================================================

def cors_response(data, status=200):
    """Helper to return JSON with correct CORS headers to avoid browser errors."""
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
    """Handles Preflight (OPTIONS) requests for CORS."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# -- Join Verify API --
async def verify_join_api(request):
    """
    Checks if a user has joined the required Telegram Channel and Group.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"joined": False, "error": "Missing user_id"}, status=400)

        try:
            user_id = int(user_id)
        except ValueError:
            return cors_response({"joined": False, "error": "Invalid ID format"}, status=400)

        # Helper to check membership
        async def check_member(chat_id):
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                # Considered joined if member, admin, or creator
                return member.status in ['member', 'administrator', 'creator', 'restricted']
            except Exception as e:
                logging.error(f"Membership Check Error ({chat_id}): {e}")
                # If bot isn't admin in channel, this fails. Return False safely.
                return False

        in_channel = await check_member(CHANNEL_USERNAME)
        in_group = await check_member(GROUP_USERNAME)
        
        if in_channel and in_group:
            return cors_response({"joined": True})
        else:
            return cors_response({"joined": False})

    except Exception as e:
        logging.error(f"API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# -- Invoice API --
async def create_invoice_api(request):
    """
    Creates a Telegram Invoice Link for Stars Payment.
    """
    try:
        data = await request.json()
        item_id = data.get('item_id')
        user_id = data.get('user_id')

        if not item_id or not user_id:
            return cors_response({"error": "Missing data"}, status=400)
        
        item = SHOP_ITEMS.get(item_id)
        if not item:
            return cors_response({"error": "Item not found"}, status=404)

        # Create price object
        prices = [LabeledPrice(label=f"Buy {item_id}", amount=item['price'])]
        
        # Generate Link
        link = await bot.create_invoice_link(
            title="Snowman Shop",
            description=f"Purchase {item_id} for Snowman Adventure",
            payload=f"{user_id}_{item_id}",
            provider_token="", # Empty string for Telegram Stars
            currency="XTR",
            prices=prices,
        )
        return cors_response({"result": link})

    except Exception as e:
        logging.error(f"Invoice API Error: {e}")
        return cors_response({"error": str(e)}, status=500)

# -- Ad Verification API --
async def verify_ad_api(request):
    """
    Verifies ad views from frontend (Adsgram/Gigapub).
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        provider = data.get('provider', 'unknown') 

        if not user_id:
            return cors_response({"success": False, "error": "Missing user_id"}, status=400)
        
        logging.info(f"📺 Ad watched: User {user_id} via {provider}")
        
        # In a real app, you might want to validate a token from the ad provider here.
        # For now, we trust the frontend call.
        
        return cors_response({"success": True})

    except Exception as e:
        logging.error(f"Ad Verify API Error: {e}")
        return cors_response({"success": False, "error": str(e)}, status=500)

# -- Play Spin API --
async def play_spin_api(request):
    """
    Determines spin result server-side to prevent cheating.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return cors_response({"success": False, "error": "Missing user_id"}, status=400)
            
        # Randomly select a prize index
        idx = random.randint(0, len(SPIN_PRIZES) - 1)
        amount = SPIN_PRIZES[idx]
        
        logging.info(f"🎰 User {user_id} spun: Index {idx}, Amount {amount}")
        
        return cors_response({
            "success": True,
            "index": idx,
            "amount": amount
        })
    except Exception as e:
        logging.error(f"Spin API Error: {e}")
        return cors_response({"success": False}, status=500)

# -- Complete Task API --
async def complete_task_api(request):
    """
    Records task completion.
    """
    try:
        data = await request.json()
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        if not user_id or not task_id:
            return cors_response({"success": False}, status=400)
            
        logging.info(f"✅ User {user_id} completed task {task_id}")
        
        # In a more advanced DB, you would store this completion to prevent duplicates.
        # Currently, the frontend handles the immediate state, and we log it here.
        
        return cors_response({"success": True})
    except Exception as e:
        logging.error(f"Task API Error: {e}")
        return cors_response({"success": False}, status=500)

async def home_handler(request):
    """Simple health check endpoint."""
    return web.Response(text="☃️ Snowman Adventure Backend Running... ❄️")

# ==============================================================================
#  9. APPLICATION LIFECYCLE & EXECUTION
# ==============================================================================

async def on_startup(bot: Bot):
    """Triggered when the application starts."""
    logging.info("🚀 Bot Starting up...")
    
    # Configure Webhook
    if WEBHOOK_URL.startswith("https://"):
        logging.info(f"🔗 Setting Webhook to: {WEBHOOK_URL}")
        try:
            # Drop pending updates to avoid flooding on restart
            await bot.delete_webhook(drop_pending_updates=True) 
            # Set the new webhook
            await bot.set_webhook(WEBHOOK_URL)
            logging.info("✅ Webhook Set Successfully")
        except Exception as e:
            logging.error(f"❌ Failed to set webhook: {e}")
    else:
        logging.warning("⚠️ WEBHOOK_URL not set or invalid (Must start with https://). Bot may not respond to commands.")

async def on_shutdown(bot: Bot):
    """Triggered when the application stops."""
    logging.info("🔌 Removing Webhook...")
    await bot.delete_webhook()
    await bot.session.close()

def main():
    """Main entry point."""
    
    # Register Startup/Shutdown callbacks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Setup aiohttp Web App
    app = web.Application()
    
    # Register API Routes (with CORS OPTIONS handling)
    app.router.add_post('/verify_join', verify_join_api)
    app.router.add_options('/verify_join', options_handler)
    
    app.router.add_post('/create_invoice', create_invoice_api)
    app.router.add_options('/create_invoice', options_handler)
    
    app.router.add_post('/verify-ad', verify_ad_api)
    app.router.add_options('/verify-ad', options_handler)
    
    app.router.add_post('/play-spin', play_spin_api)
    app.router.add_options('/play-spin', options_handler)
    
    app.router.add_post('/complete-task', complete_task_api)
    app.router.add_options('/complete-task', options_handler)

    # Root route
    app.router.add_get('/', home_handler)

    # Register Webhook Handler from Aiogram
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Run the application
    setup_application(app, dp, bot=bot)
    
    # Port configuration (Render uses PORT env var)
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🌍 Starting Web Server on Port {port}")
    
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

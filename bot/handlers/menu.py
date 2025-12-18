"""Menu button handlers for ReplyKeyboardMarkup."""

from aiogram import Router, types
from aiogram.enums import ParseMode
import redis
import json

from config.settings import REDIS_URL, WEBAPP_URL
from bot.handlers import start, api_keys, balance, help
from bot.keyboards.main_menu import get_main_menu

router = Router()
redis_client = redis.from_url(REDIS_URL)


async def get_user(user_id: int) -> dict:
    """Get user data from Redis."""
    user_key = f"user:{user_id}"
    user_data = redis_client.get(user_key)
    if not user_data:
        return None
    return json.loads(user_data)


@router.message(lambda m: m.text == "🔑 API Key")
async def handle_api_key_button(message: types.Message):
    """Handle API Key button."""
    await api_keys.cmd_api_key(message)


@router.message(lambda m: m.text == "💰 Balance")
async def handle_balance_button(message: types.Message):
    """Handle Balance button."""
    await balance.cmd_balance(message)


@router.message(lambda m: m.text == "📊 Usage")
async def handle_usage_button(message: types.Message):
    """Handle Usage button."""
    await balance.cmd_usage(message)


@router.message(lambda m: m.text == "📦 Products")
async def handle_products_button(message: types.Message):
    """Handle Products button."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer(
            "❌ You need to start the bot first. Use /start",
            reply_markup=get_main_menu(),
        )
        return
    
    text = (
        "📦 <b>KikuAI Products</b>\n\n"
        "<b>Available APIs:</b>\n\n"
        "🔹 <b>ReliAPI</b>\n"
        "Reliable LLM API with automatic retries and fallbacks.\n"
        "• Multiple providers (OpenAI, Anthropic, etc.)\n"
        "• Automatic retry logic\n"
        "• Cost optimization\n\n"
        "More products coming soon!\n\n"
        "Visit https://kikuai.dev for details."
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())


@router.message(lambda m: m.text == "❓ Help")
async def handle_help_button(message: types.Message):
    """Handle Help button."""
    await help.cmd_help(message)











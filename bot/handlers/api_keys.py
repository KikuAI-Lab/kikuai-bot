"""API key management handlers."""

import json
import secrets
from datetime import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import redis

from config.settings import REDIS_URL, WEBAPP_URL
from bot.keyboards.main_menu import get_main_menu

router = Router()
redis_client = redis.from_url(REDIS_URL)


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"kikuai_{secrets.token_urlsafe(32)}"


async def get_user(user_id: int) -> dict:
    """Get user data from Redis."""
    user_key = f"user:{user_id}"
    user_data = redis_client.get(user_key)
    if not user_data:
        return None
    return json.loads(user_data)


async def regenerate_api_key(user_id: int) -> str:
    """Regenerate API key for user."""
    user = await get_user(user_id)
    if not user:
        return None
    
    # Get old key
    old_key = user.get("api_key")
    
    # Generate new key
    new_key = generate_api_key()
    
    # Update user
    user["api_key"] = new_key
    user_key = f"user:{user_id}"
    redis_client.set(user_key, json.dumps(user))
    
    # Remove old API key mapping
    if old_key:
        old_api_key_key = f"api_key:{old_key}"
        redis_client.delete(old_api_key_key)
    
    # Save new API key mapping
    api_key_key = f"api_key:{new_key}"
    redis_client.set(api_key_key, json.dumps({
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
    }))
    
    return new_key


@router.message(Command("api_key"))
async def cmd_api_key(message: types.Message):
    """Handle /api_key command."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer(
            "❌ You need to start the bot first. Use /start",
            reply_markup=get_main_menu(),
        )
        return
    
    api_key = user.get("api_key", "Not found")
    
    text = (
        "🔑 <b>Your API Key</b>\n\n"
        f"<code>{api_key}</code>\n\n"
        "Use this key to authenticate your API requests.\n\n"
        "⚠️ Keep it secret and don't share it with anyone!"
    )
    
    # Add Web App button
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🔧 Manage Keys",
                    web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/manage_keys.html"),
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text="🔄 Regenerate",
                    callback_data="regenerate_key",
                ),
            ],
        ],
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("regenerate_key"))
async def cmd_regenerate_key(message: types.Message):
    """Handle /regenerate_key command."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer(
            "❌ You need to start the bot first. Use /start",
            reply_markup=get_main_menu(),
        )
        return
    
    text = (
        "⚠️ <b>Regenerate API Key?</b>\n\n"
        "This will invalidate your current API key.\n"
        "All requests using the old key will fail.\n\n"
        "Are you sure?"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Yes, regenerate",
                    callback_data="confirm_regenerate",
                ),
                types.InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="cancel_regenerate",
                ),
            ],
        ],
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "regenerate_key")
async def callback_regenerate_key(callback: types.CallbackQuery):
    """Handle regenerate key callback."""
    await cmd_regenerate_key(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "confirm_regenerate")
async def callback_confirm_regenerate(callback: types.CallbackQuery):
    """Handle confirm regenerate callback."""
    user_id = callback.from_user.id
    new_key = await regenerate_api_key(user_id)
    
    if not new_key:
        await callback.answer("❌ Error regenerating key", show_alert=True)
        return
    
    text = (
        "✅ <b>API Key Regenerated</b>\n\n"
        f"<code>{new_key}</code>\n\n"
        "⚠️ Your old key is now invalid. Update your applications!"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    await callback.answer("✅ Key regenerated")


@router.callback_query(lambda c: c.data == "cancel_regenerate")
async def callback_cancel_regenerate(callback: types.CallbackQuery):
    """Handle cancel regenerate callback."""
    await callback.answer("Cancelled")
    await callback.message.delete()


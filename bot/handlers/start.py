"""Start command handler."""

import json
import secrets
from datetime import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import redis

from config.settings import REDIS_URL
from bot.keyboards.main_menu import get_main_menu

router = Router()
redis_client = redis.from_url(REDIS_URL)


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"kikuai_{secrets.token_urlsafe(32)}"


async def get_or_create_user(user_id: int, username: str = None) -> dict:
    """Get existing user or create new one."""
    user_key = f"user:{user_id}"
    
    # Check if user exists
    user_data = redis_client.get(user_key)
    if user_data:
        return json.loads(user_data)
    
    # Create new user
    api_key = generate_api_key()
    user = {
        "user_id": user_id,
        "telegram_username": username,
        "api_key": api_key,
        "created_at": datetime.now().isoformat(),
        "balance_usd": 0.0,
        "status": "active",
    }
    
    # Save user
    redis_client.set(user_key, json.dumps(user))
    
    # Save API key mapping
    api_key_key = f"api_key:{api_key}"
    redis_client.set(api_key_key, json.dumps({
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
    }))
    
    return user


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Get or create user
    user = await get_or_create_user(user_id, username)
    
    # Check if new user
    is_new = "created_at" in user and (
        datetime.now() - datetime.fromisoformat(user["created_at"])
    ).total_seconds() < 5
    
    welcome_text = (
        "👋 <b>Welcome to KikuAI Bot!</b>\n\n"
        if is_new else
        "👋 <b>Welcome back!</b>\n\n"
    )
    
    welcome_text += (
        "Manage all your KikuAI API products through Telegram.\n\n"
        f"🔑 <b>Your API Key:</b>\n<code>{user['api_key']}</code>\n\n"
        f"💰 <b>Balance:</b> ${user['balance_usd']:.2f}\n\n"
        "Use the menu below to get started."
    )
    
    await message.answer(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu(),
    )


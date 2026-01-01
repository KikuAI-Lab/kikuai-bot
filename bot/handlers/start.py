"""Start command handler."""

import json
import secrets
from datetime import datetime, timedelta
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
import redis

from config.settings import REDIS_URL, FRONTEND_URL
from bot.keyboards.main_menu import get_main_menu

router = Router()
redis_client = redis.from_url(REDIS_URL)

# Magic link token expiry (15 minutes)
MAGIC_LINK_EXPIRY_SECONDS = 900


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"kikuai_{secrets.token_urlsafe(32)}"


def generate_magic_token() -> str:
    """Generate a secure magic link token."""
    return secrets.token_urlsafe(32)


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
async def cmd_start(message: types.Message, command: CommandObject):
    """Handle /start command with optional deep link parameter."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Get or create user
    user = await get_or_create_user(user_id, username)
    
    # Check for login deep link: /start login
    if command.args and command.args.strip().lower() == "login":
        await handle_web_login(message, user_id, username)
        return
    
    # Regular /start flow
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


async def handle_web_login(message: types.Message, user_id: int, username: str):
    """Generate magic link for web login and send to user."""
    # Generate magic token
    token = generate_magic_token()
    
    # Store token in Redis with user info
    token_key = f"magic_link:{token}"
    token_data = {
        "telegram_id": user_id,
        "telegram_username": username,
        "created_at": datetime.now().isoformat(),
    }
    redis_client.setex(
        token_key, 
        MAGIC_LINK_EXPIRY_SECONDS, 
        json.dumps(token_data)
    )
    
    # Build magic link URL
    frontend_url = FRONTEND_URL or "https://kikuai.dev"
    magic_link = f"{frontend_url}/auth/telegram-callback?token={token}"
    
    login_text = (
        "🔐 <b>Web Login</b>\n\n"
        "Click the button below to login to KikuAI Dashboard:\n\n"
        f"⏱ Link expires in 15 minutes."
    )
    
    # Create inline keyboard with magic link button
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Login to Dashboard", url=magic_link)]
    ])
    
    await message.answer(
        login_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

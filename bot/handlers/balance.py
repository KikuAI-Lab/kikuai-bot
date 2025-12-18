"""Balance and usage handlers."""

import json
from datetime import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import redis

from config.settings import REDIS_URL, WEBAPP_URL
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


def get_usage(user_id: int, month: str = None) -> dict:
    """Get usage statistics."""
    if not month:
        month = datetime.now().strftime("%Y-%m")
    
    usage_key = f"usage:{user_id}:{month}"
    cost_key = f"cost:{user_id}:{month}"
    
    requests = int(redis_client.get(usage_key) or 0)
    cost = float(redis_client.get(cost_key) or 0)
    
    return {
        "month": month,
        "requests": requests,
        "cost_usd": cost,
    }


@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Handle /balance command."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer(
            "❌ You need to start the bot first. Use /start",
            reply_markup=get_main_menu(),
        )
        return
    
    balance = user.get("balance_usd", 0.0)
    usage = get_usage(user_id)
    
    text = (
        "💰 <b>Your Balance</b>\n\n"
        f"<b>Current Balance:</b> ${balance:.2f}\n\n"
        f"<b>This Month:</b>\n"
        f"• Requests: {usage['requests']:,}\n"
        f"• Cost: ${usage['cost_usd']:.4f}\n\n"
    )
    
    if balance < 5.0:
        text += "⚠️ <b>Low balance!</b> Top up to continue using APIs.\n\n"
    
    text += "Use /topup to add funds (coming soon)"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 View Dashboard",
                    web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/dashboard.html"),
                ),
            ],
        ],
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("usage"))
async def cmd_usage(message: types.Message):
    """Handle /usage command."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer(
            "❌ You need to start the bot first. Use /start",
            reply_markup=get_main_menu(),
        )
        return
    
    usage = get_usage(user_id)
    
    # Get endpoint usage
    month = datetime.now().strftime("%Y-%m")
    pattern = f"usage:{user_id}:{month}:*"
    endpoint_keys = redis_client.keys(pattern)
    
    endpoint_usage = {}
    for key in endpoint_keys:
        endpoint = key.decode().split(":")[-1]
        count = int(redis_client.get(key) or 0)
        endpoint_usage[endpoint] = count
    
    text = (
        "📊 <b>Usage Statistics</b>\n\n"
        f"<b>Month:</b> {usage['month']}\n"
        f"<b>Total Requests:</b> {usage['requests']:,}\n"
        f"<b>Total Cost:</b> ${usage['cost_usd']:.4f}\n\n"
    )
    
    if endpoint_usage:
        text += "<b>By Endpoint:</b>\n"
        for endpoint, count in endpoint_usage.items():
            text += f"• {endpoint}: {count:,}\n"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 Full Dashboard",
                    web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/dashboard.html"),
                ),
            ],
        ],
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


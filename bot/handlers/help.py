"""Help command handler."""

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command."""
    help_text = (
        "📚 <b>KikuAI Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Start bot and get your API key\n"
        "/help - Show this help message\n"
        "/api_key - Show your API key\n"
        "/balance - Check your balance\n"
        "/usage - View usage statistics\n\n"
        "<b>Features:</b>\n"
        "🔑 Manage API keys\n"
        "💰 Pay-as-you-go pricing\n"
        "📊 Track usage\n"
        "📦 Access all KikuAI products\n\n"
        "<b>Get Started:</b>\n"
        "1. Use /start to get your API key\n"
        "2. Use your API key to make requests\n"
        "3. Top up your balance when needed\n\n"
        "For more info, visit: https://kikuai.dev"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)


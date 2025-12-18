"""Main menu keyboard."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """Get main menu keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔑 API Key"),
                KeyboardButton(text="💰 Balance"),
            ],
            [
                KeyboardButton(text="📊 Usage"),
                KeyboardButton(text="📦 Products"),
            ],
            [
                KeyboardButton(text="❓ Help"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Choose an option...",
    )
    return keyboard


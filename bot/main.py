"""Main entry point for Telegram bot."""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config.settings import TELEGRAM_BOT_TOKEN
from bot.handlers import start, help, api_keys, balance, payment, menu
from api.dependencies import get_payment_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    # Initialize bot and dispatcher
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Attach bot instance to notification service so payment engine can send messages
    payment_engine = get_payment_engine()
    if hasattr(payment_engine, "notifications"):
        try:
            payment_engine.notifications.set_bot(bot)
        except Exception as e:
            logger.warning(f"Failed to attach bot to notification service: {e}")
    
    # Register routers
    # IMPORTANT: menu.router must be registered BEFORE other routers
    # to catch button clicks before they're handled by command handlers
    dp.include_router(menu.router)  # Menu button handlers (FIRST!)
    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(api_keys.router)
    dp.include_router(balance.router)
    dp.include_router(payment.router)  # Payment handlers
    
    logger.info("Starting bot...")
    
    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)


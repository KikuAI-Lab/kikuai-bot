"""Telegram-based NotificationService implementation."""

from decimal import Decimal
from typing import Optional
import logging

from api.services.payment_engine import NotificationService
from config.settings import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


class TelegramNotificationService(NotificationService):
    """Telegram bot notification service."""
    
    def __init__(self, bot_instance: Optional[object] = None):
        """
        Initialize notification service.
        
        Args:
            bot_instance: aiogram Bot instance (will be set later if None)
        """
        self.bot_instance = bot_instance
        self.bot_token = TELEGRAM_BOT_TOKEN
    
    def set_bot(self, bot_instance: object):
        """Set bot instance after initialization."""
        self.bot_instance = bot_instance
    
    async def notify_payment_success(
        self,
        user_id: int,
        amount: Decimal,
        new_balance: Decimal,
    ) -> None:
        """Send payment success notification."""
        if not self.bot_instance:
            logger.warning(f"Bot instance not set, cannot notify user {user_id}")
            return
        
        try:
            message = (
                f"✅ <b>Payment Successful!</b>\n\n"
                f"💰 Amount added: <b>${amount:.2f}</b>\n"
                f"📈 New balance: <b>${new_balance:.2f}</b>\n\n"
                f"Thank you for your purchase!"
            )
            
            await self.bot_instance.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send payment success notification to {user_id}: {e}")
    
    async def notify_payment_failed(
        self,
        user_id: int,
        reason: str,
    ) -> None:
        """Send payment failure notification."""
        if not self.bot_instance:
            logger.warning(f"Bot instance not set, cannot notify user {user_id}")
            return
        
        try:
            message = (
                f"❌ <b>Payment Failed</b>\n\n"
                f"{reason}\n\n"
                f"Please try again or contact support."
            )
            
            await self.bot_instance.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send payment failure notification to {user_id}: {e}")
    
    async def notify_low_balance(
        self,
        user_id: int,
        current_balance: Decimal,
    ) -> None:
        """Send low balance warning."""
        if not self.bot_instance:
            logger.warning(f"Bot instance not set, cannot notify user {user_id}")
            return
        
        try:
            message = (
                f"⚠️ <b>Low Balance Warning</b>\n\n"
                f"Your current balance is <b>${current_balance:.2f}</b>.\n"
                f"Please top up to continue using our services.\n\n"
                f"Use /topup to add funds."
            )
            
            await self.bot_instance.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send low balance notification to {user_id}: {e}")





"""
Payment handlers for Telegram bot.

Implements:
- /topup command with amount selection
- Payment method selection (Paddle / Stars)
- Telegram Stars pre_checkout_query and successful_payment handlers
"""

import logging
import json
from decimal import Decimal
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command

from config.settings import WEBAPP_URL

logger = logging.getLogger(__name__)

router = Router()

# Top-up amounts in USD
TOPUP_AMOUNTS = [5, 10, 25, 50, 100]

# Stars packages (matching TelegramStarsProvider)
STARS_PACKAGES = [
    {"stars": 50, "usd": 1, "label": "50 ⭐ (~$1)"},
    {"stars": 250, "usd": 5, "label": "250 ⭐ (~$5)"},
    {"stars": 500, "usd": 10, "label": "500 ⭐ (~$10)"},
    {"stars": 1000, "usd": 20, "label": "1000 ⭐ (~$20)"},
    {"stars": 2500, "usd": 50, "label": "2500 ⭐ (~$50)"},
]


# ============================================================================
# /topup Command
# ============================================================================

@router.message(Command("topup"))
async def cmd_topup(message: Message):
    """Show top-up options."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"${amount}",
                callback_data=f"topup_amount:{amount}"
            )
            for amount in TOPUP_AMOUNTS[:3]  # First row: $5, $10, $25
        ],
        [
            InlineKeyboardButton(
                text=f"${amount}",
                callback_data=f"topup_amount:{amount}"
            )
            for amount in TOPUP_AMOUNTS[3:]  # Second row: $50, $100
        ],
    ])
    
    await message.answer(
        "💰 **Add Funds to Your Balance**\n\n"
        "Choose the amount to add:\n\n"
        "• Pay with card via Paddle\n"
        "• Or use Telegram Stars ⭐",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("topup_amount:"))
async def select_payment_method(callback: CallbackQuery):
    """Show payment method selection after amount chosen."""
    amount = int(callback.data.split(":")[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💳 Card (Paddle)",
                callback_data=f"pay_paddle:{amount}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ Telegram Stars",
                callback_data=f"pay_stars:{amount}"
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Back",
                callback_data="topup_back"
            )
        ],
    ])
    
    await callback.message.edit_text(
        f"💰 **Top-up ${amount}**\n\n"
        "Choose payment method:\n\n"
        "💳 **Card** - Visa, Mastercard, PayPal via Paddle\n"
        "⭐ **Stars** - Pay with Telegram Stars (instant, no fees)",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "topup_back")
async def back_to_amount_selection(callback: CallbackQuery):
    """Go back to amount selection."""
    await cmd_topup(callback.message)


# ============================================================================
# Paddle Payment
# ============================================================================

@router.callback_query(F.data.startswith("pay_paddle:"))
async def initiate_paddle_payment(callback: CallbackQuery):
    """Create Paddle checkout and show payment button."""
    from api.dependencies import get_payment_engine
    from api.services.payment_engine import PaymentRequest, PaymentMethod
    
    amount = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    try:
        # Get payment engine
        engine = get_payment_engine()
        
        # Create payment request
        request = PaymentRequest(
            user_id=user_id,
            amount_usd=Decimal(str(amount)),
            method=PaymentMethod.PADDLE,
        )
        
        # Create checkout
        success_url = f"{WEBAPP_URL}/payment/success"
        cancel_url = f"{WEBAPP_URL}/payment/cancel"
        
        result = await engine.create_payment(request, success_url, cancel_url)
        
        if not result.is_success or not result.checkout_url:
            await callback.message.edit_text(
                "❌ Failed to create payment.\n\n"
                f"Error: {result.error or 'Unknown error'}\n\n"
                "Please try again later.",
                parse_mode="Markdown"
            )
            return
        
        # Show payment button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Open Checkout",
                    web_app={"url": result.checkout_url}
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Back",
                    callback_data="topup_back"
                )
            ],
        ])
        
        await callback.message.edit_text(
            f"💳 **Paddle Checkout**\n\n"
            f"Amount: ${amount}\n\n"
            "Click the button below to complete your payment.\n"
            "After payment, your balance will be updated automatically.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info(f"Paddle checkout created for user {user_id}: ${amount}")
        
    except Exception as e:
        logger.error(f"Failed to create Paddle checkout: {e}")
        await callback.message.edit_text(
            "❌ Payment Error\n\n"
            "Something went wrong. Please try again later.",
            parse_mode="Markdown"
        )


# ============================================================================
# Telegram Stars Payment
# ============================================================================

@router.callback_query(F.data.startswith("pay_stars:"))
async def initiate_stars_payment(callback: CallbackQuery):
    """Show Stars packages for the selected amount."""
    amount = int(callback.data.split(":")[1])
    
    # Find matching or closest Stars package
    matching_packages = [p for p in STARS_PACKAGES if p["usd"] == amount]
    
    if not matching_packages:
        # Find closest packages
        available = [p for p in STARS_PACKAGES if p["usd"] >= amount]
        if available:
            matching_packages = [available[0]]
        else:
            matching_packages = [STARS_PACKAGES[-1]]  # Largest package
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Pay {pkg['stars']} ⭐ (${pkg['usd']})",
                callback_data=f"stars_invoice:{pkg['stars']}:{pkg['usd']}"
            )
        ]
        for pkg in matching_packages
    ] + [
        [
            InlineKeyboardButton(
                text="◀️ Back",
                callback_data=f"topup_amount:{amount}"
            )
        ],
    ])
    
    await callback.message.edit_text(
        f"⭐ **Pay with Telegram Stars**\n\n"
        f"Selected amount: ${amount}\n\n"
        "Choose a Stars package:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("stars_invoice:"))
async def create_stars_invoice(callback: CallbackQuery):
    """Create and send Stars invoice."""
    import time
    import redis
    from config.settings import REDIS_URL
    
    parts = callback.data.split(":")
    stars = int(parts[1])
    usd = int(parts[2])
    user_id = callback.from_user.id
    
    try:
        # Generate payload
        timestamp = int(time.time())
        payload = f"topup:{user_id}:{timestamp}"
        
        # Store pending payment in Redis
        redis_client = redis.from_url(REDIS_URL)
        pending_data = json.dumps({
            "user_id": user_id,
            "stars": stars,
            "usd": str(usd),
            "created_at": timestamp,
        })
        redis_client.setex(f"pending_stars:{payload}", 3600, pending_data)
        
        # Create invoice
        prices = [
            LabeledPrice(
                label=f"Balance top-up ${usd}",
                amount=stars  # Amount in Stars
            )
        ]
        
        await callback.bot.send_invoice(
            chat_id=callback.message.chat.id,
            title="KikuAI Balance Top-up",
            description=f"Add ${usd} to your KikuAI balance",
            payload=payload,
            currency="XTR",  # Telegram Stars currency code
            prices=prices,
            provider_token="",  # Empty for Stars
        )
        
        # Delete the selection message
        await callback.message.delete()
        
        logger.info(f"Stars invoice created for user {user_id}: {stars} stars (${usd})")
        
    except Exception as e:
        logger.error(f"Failed to create Stars invoice: {e}")
        await callback.message.edit_text(
            "❌ Failed to create Stars invoice.\n\n"
            "Please try again later.",
            parse_mode="Markdown"
        )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Validate Stars payment before processing."""
    import redis
    from config.settings import REDIS_URL
    
    payload = pre_checkout.invoice_payload
    user_id = pre_checkout.from_user.id
    
    logger.info(f"Pre-checkout query for user {user_id}: {payload}")
    
    try:
        # Validate payload format
        if not payload.startswith("topup:"):
            await pre_checkout.answer(
                ok=False,
                error_message="Invalid payment. Please try again."
            )
            return
        
        # Check pending payment exists
        redis_client = redis.from_url(REDIS_URL)
        pending_key = f"pending_stars:{payload}"
        pending_data = redis_client.get(pending_key)
        
        if not pending_data:
            await pre_checkout.answer(
                ok=False,
                error_message="Payment session expired. Please create a new payment."
            )
            return
        
        # Validate user matches
        pending = json.loads(pending_data)
        if int(pending.get("user_id")) != user_id:
            logger.warning(f"User mismatch in pre_checkout: {user_id} vs {pending.get('user_id')}")
            await pre_checkout.answer(
                ok=False,
                error_message="Invalid payment. User mismatch."
            )
            return
        
        # All good
        await pre_checkout.answer(ok=True)
        
    except Exception as e:
        logger.error(f"Error in pre_checkout_query: {e}")
        await pre_checkout.answer(
            ok=False,
            error_message="Payment validation failed. Please try again."
        )


@router.message(F.successful_payment)
async def process_successful_stars_payment(message: Message):
    """Process successful Stars payment."""
    import redis
    from config.settings import REDIS_URL
    from api.dependencies import get_payment_engine
    from api.services.payment_engine import (
        WebhookEvent,
        PaymentMethod,
    )
    
    payment = message.successful_payment
    user_id = message.from_user.id
    payload = payment.invoice_payload
    stars = payment.total_amount
    charge_id = payment.telegram_payment_charge_id
    
    logger.info(f"Successful Stars payment for user {user_id}: {stars} stars")
    
    try:
        # Check idempotency
        redis_client = redis.from_url(REDIS_URL)
        processed_key = f"stars_processed:{charge_id}"
        
        if redis_client.exists(processed_key):
            logger.info(f"Stars payment already processed: {charge_id}")
            return
        
        # Get pending payment data
        pending_key = f"pending_stars:{payload}"
        pending_data = redis_client.get(pending_key)
        
        usd = Decimal("0")
        if pending_data:
            pending = json.loads(pending_data)
            usd = Decimal(pending.get("usd", "0"))
            redis_client.delete(pending_key)
        else:
            # Calculate from stars
            usd = Decimal(str(stars)) / 50  # Approximate rate
        
        # Create webhook event for payment engine
        event = WebhookEvent(
            provider=PaymentMethod.TELEGRAM_STARS,
            event_type="successful_payment",
            event_id=charge_id,
            data={
                "user_id": user_id,
                "payload": payload,
                "telegram_payment_charge_id": charge_id,
                "total_amount": stars,
            },
            raw_body=b"",
            signature="",
        )
        
        # Process payment
        engine = get_payment_engine()
        transaction = await engine.process_webhook(event)
        
        if transaction:
            # Mark as processed
            redis_client.setex(processed_key, 604800, "1")  # 7 days
            
            # Get new balance
            from api.services.balance_manager import RedisBalanceManager
            balance_manager = RedisBalanceManager()
            new_balance = await balance_manager.get_balance(user_id)
            
            await message.answer(
                f"✅ **Payment Successful!**\n\n"
                f"⭐ Stars paid: {stars}\n"
                f"💵 Added: ${usd}\n"
                f"📈 New balance: ${new_balance:.2f}\n\n"
                "Thank you for your purchase!",
                parse_mode="Markdown"
            )
        else:
            logger.error(f"Payment engine returned no transaction for {charge_id}")
            await message.answer(
                "⚠️ Payment received but processing failed.\n\n"
                "Don't worry, your payment is safe. "
                "Please contact support if your balance wasn't updated.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error processing successful Stars payment: {e}")
        await message.answer(
            "⚠️ Payment processing error.\n\n"
            "Your payment was received. If your balance wasn't updated, "
            "please contact support.",
            parse_mode="Markdown"
        )

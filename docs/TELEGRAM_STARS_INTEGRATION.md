# Telegram Stars Integration

Guide for integrating Telegram Stars payments in KikuAI Bot.

## Overview

Telegram Stars is a native Telegram payment method - instant, no fees.

## Configuration

```bash
# .env
TELEGRAM_BOT_TOKEN=your_bot_token
```

No additional API keys required - Stars uses the Bot API.

## Stars/USD Conversion

| Stars | USD |
|-------|-----|
| 50 | $1 |
| 100 | $2 |
| 250 | $5 |
| 500 | $10 |
| 1000 | $20 |
| 2500 | $50 |
| 5000 | $100 |

Rate: **1 USD ≈ 50 Stars**

## User Flow

1. User sends `/topup`
2. Bot shows amount selection
3. User selects "⭐ Telegram Stars"
4. Bot sends invoice via `send_invoice`
5. User pays in Telegram UI
6. Bot receives `pre_checkout_query` - validates
7. Telegram processes payment
8. Bot receives `successful_payment` - credits balance

## Implementation

### Bot Handlers

Located in `bot/handlers/payment.py`:

```python
@router.callback_query(F.data.startswith("stars_invoice:"))
async def create_stars_invoice(callback):
    await callback.bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="KikuAI Balance Top-up",
        description=f"Add ${usd} to your balance",
        payload=f"topup:{user_id}:{timestamp}",
        currency="XTR",  # Stars currency code
        prices=[LabeledPrice(label="Top-up", amount=stars)],
        provider_token="",  # Empty for Stars
    )

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout):
    # Validate pending payment exists
    # Check user matches
    await pre_checkout.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message):
    # Extract payment data
    # Call PaymentEngine.process_webhook()
    # Update balance
    # Notify user
```

### TelegramStarsProvider

Located in `api/services/payment_engine.py`:

```python
class TelegramStarsProvider(PaymentProvider):
    @classmethod
    def usd_to_stars(cls, usd: Decimal) -> int:
        return int(usd * 50)
    
    async def create_checkout(...) -> PaymentResult:
        # Returns invoice data (not URL)
        # Stores pending payment in Redis
        
    async def process_webhook(event) -> Transaction:
        # Processes successful_payment callback
        # Creates Transaction for balance update
```

## Testing

### Unit Tests

```bash
pytest tests/test_telegram_stars_provider.py -v
```

### Manual Testing

1. Start bot locally
2. Send `/topup`
3. Select amount and "Telegram Stars"
4. Complete payment in Telegram
5. Verify balance updated

## Important Notes

- Stars payments are **instant**
- No traditional webhooks - handled via Bot API
- `provider_token` must be **empty string** for Stars
- Currency code is `XTR`
- Payload format: `topup:{user_id}:{timestamp}:{key}`

## Pending Payment Storage

```python
# Redis key: pending_stars:topup:12345:1234567890
{
    "user_id": 12345,
    "stars": 250,
    "usd": "5.00",
    "idempotency_key": "...",
    "created_at": 1234567890
}
# TTL: 1 hour
```

## Error Handling

| Error | Action |
|-------|--------|
| Missing pending data | Use calculated amount |
| User mismatch | Log warning, still process |
| Duplicate payment | Return 200, skip processing |

## Security

- ✅ Validate payload in pre_checkout_query
- ✅ Check user_id matches pending payment
- ✅ Idempotency via telegram_payment_charge_id
- ✅ Clean up pending data after processing

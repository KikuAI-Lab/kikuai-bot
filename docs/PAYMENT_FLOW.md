# Payment Flow - @kikuai_bot

## Overview

This document describes detailed payment flows for:
- Paddle checkout flow
- Paddle webhook processing
- Telegram Stars payment flow
- Balance update flow
- Edge cases handling

## Payment Methods

| Method | Minimum | Maximum | Fees | Use Case |
|--------|---------|---------|------|----------|
| Paddle | $5 | $1000 | ~5% | Card, PayPal |
| Telegram Stars | 50 stars (~$1) | 10000 stars | 0% | Quick payments |

## Paddle Payment Flow

### 1. Checkout Flow

```
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
│  User   │      │Telegram │      │   Bot   │      │ Backend │      │ Paddle  │
└────┬────┘      └────┬────┘      └────┬────┘      └────┬────┘      └────┬────┘
     │                │                │                │                │
     │  /topup        │                │                │                │
     │───────────────────────────────>│                │                │
     │                │                │                │                │
     │                │                │  "Choose amount"│               │
     │<───────────────────────────────│                │                │
     │                │                │  [Inline buttons]              │
     │                │                │  [$5] [$10] [$25] [$50]        │
     │                │                │                │                │
     │  Click [$10]   │                │                │                │
     │───────────────────────────────>│                │                │
     │                │                │                │                │
     │                │                │  POST /payment/topup           │
     │                │                │  {amount: 10, method: paddle} │
     │                │                │───────────────>│                │
     │                │                │                │                │
     │                │                │                │  POST /checkout│
     │                │                │                │───────────────>│
     │                │                │                │                │
     │                │                │                │  {checkout_url}│
     │                │                │                │<───────────────│
     │                │                │                │                │
     │                │                │  {checkout_url}│                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │  [Open Payment]│                │                │                │
     │  Web App Button│                │                │                │
     │<───────────────────────────────│                │                │
     │                │                │                │                │
     │  User opens Web App             │                │                │
     │──────────────>│                │                │                │
     │                │                │                │                │
     │                │  Redirect to Paddle Checkout   │                │
     │                │────────────────────────────────────────────────>│
     │                │                │                │                │
     │  ════════════════════════════════════════════════════════════════│
     │                    USER COMPLETES PAYMENT AT PADDLE               │
     │  ════════════════════════════════════════════════════════════════│
     │                │                │                │                │
```

### 2. Create Checkout Request

**Backend endpoint:** `POST /api/v1/payment/topup`

```python
@router.post("/payment/topup")
async def create_topup(
    request: TopupRequest,
    user: User = Depends(get_current_user)
):
    """Create payment checkout session."""
    
    # Validate amount
    if request.amount_usd < 5 or request.amount_usd > 1000:
        raise HTTPException(400, "Amount must be between $5 and $1000")
    
    # Generate idempotency key
    idempotency_key = f"topup:{user.user_id}:{int(time.time())}"
    
    # Create Paddle checkout
    checkout = await paddle_service.create_checkout(
        price_id=get_price_id_for_amount(request.amount_usd),
        customer_email=user.email,
        custom_data={
            "user_id": str(user.user_id),
            "idempotency_key": idempotency_key,
            "amount_usd": str(request.amount_usd)
        },
        success_url=f"{WEBAPP_URL}/payment/success?session={{checkout_id}}",
        cancel_url=f"{WEBAPP_URL}/payment/cancel"
    )
    
    # Store pending payment
    await redis.setex(
        f"pending_payment:{checkout.id}",
        3600,  # 1 hour expiry
        json.dumps({
            "user_id": user.user_id,
            "amount_usd": request.amount_usd,
            "status": "pending"
        })
    )
    
    return {
        "payment_id": checkout.id,
        "checkout_url": checkout.checkout_url,
        "expires_at": checkout.expires_at
    }
```

### 3. Webhook Processing Flow

```
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
│ Paddle  │      │ Backend │      │  Redis  │      │   Bot   │
└────┬────┘      └────┬────┘      └────┬────┘      └────┬────┘
     │                │                │                │
     │  POST /webhook │                │                │
     │  "transaction. │                │                │
     │   completed"   │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │                │  Verify signature               │
     │                │  (HMAC-SHA256)│                │
     │                │                │                │
     │                │  Check idempotency             │
     │                │───────────────>│                │
     │                │                │                │
     │                │  If not processed:              │
     │                │                │                │
     │                │  ┌─────────────────────────┐   │
     │                │  │ 1. Get user from        │   │
     │                │  │    custom_data          │   │
     │                │  │ 2. Validate amount      │   │
     │                │  │ 3. Update balance       │   │
     │                │  │ 4. Record transaction   │   │
     │                │  │ 5. Mark as processed    │   │
     │                │  └─────────────────────────┘   │
     │                │                │                │
     │                │  (atomic Lua script)           │
     │                │───────────────>│                │
     │                │                │                │
     │                │                │                │  Send notification
     │                │────────────────────────────────>│
     │                │                │                │
     │                │                │                │  "✅ $10 added"
     │                │                │                │───> User
     │                │                │                │
     │  200 OK        │                │                │
     │<───────────────│                │                │
     │                │                │                │
```

### 4. Webhook Handler Implementation

```python
@router.post("/webhooks/paddle")
async def handle_paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature")
):
    """Handle Paddle webhook events."""
    
    body = await request.body()
    
    # 1. Verify signature
    if not verify_paddle_signature(body, paddle_signature):
        logger.warning("Invalid Paddle webhook signature")
        raise HTTPException(401, "Invalid signature")
    
    event = await request.json()
    event_type = event.get("event_type")
    data = event.get("data", {})
    
    # 2. Get idempotency key
    custom_data = json.loads(data.get("custom_data", "{}"))
    idempotency_key = custom_data.get("idempotency_key")
    
    # 3. Check if already processed
    if idempotency_key:
        already_processed = await redis.get(f"webhook:paddle:{idempotency_key}")
        if already_processed:
            logger.info(f"Webhook already processed: {idempotency_key}")
            return {"status": "already_processed"}
    
    # 4. Process event
    if event_type == "transaction.completed":
        await process_successful_payment(data, custom_data)
    
    elif event_type == "transaction.payment_failed":
        await process_failed_payment(data, custom_data)
    
    elif event_type == "transaction.refunded":
        await process_refund(data, custom_data)
    
    # 5. Mark as processed
    if idempotency_key:
        await redis.setex(
            f"webhook:paddle:{idempotency_key}",
            604800,  # 7 days
            "processed"
        )
    
    return {"status": "processed"}


async def process_successful_payment(data: dict, custom_data: dict):
    """Process successful payment."""
    
    user_id = int(custom_data.get("user_id"))
    amount_usd = float(custom_data.get("amount_usd"))
    transaction_id = data.get("id")
    
    # Validate amount matches
    actual_amount = float(data.get("details", {}).get("totals", {}).get("total", 0))
    if abs(actual_amount - amount_usd) > 0.01:
        logger.error(f"Amount mismatch: expected {amount_usd}, got {actual_amount}")
        # Still process, but log discrepancy
        amount_usd = actual_amount
    
    # Update balance atomically
    await update_balance_atomic(
        user_id=user_id,
        amount=amount_usd,
        transaction={
            "id": f"txn_{transaction_id}",
            "type": "topup",
            "amount_usd": amount_usd,
            "source": "paddle",
            "paddle_transaction_id": transaction_id,
            "created_at": datetime.utcnow().isoformat()
        }
    )
    
    # Send notification to user
    await send_payment_notification(
        user_id=user_id,
        message=f"✅ Payment received!\n\n"
                f"💰 Amount: ${amount_usd:.2f}\n"
                f"📈 New balance: ${await get_balance(user_id):.2f}"
    )
```

## Telegram Stars Payment Flow

### 1. Stars Checkout Flow

```
┌─────────┐      ┌─────────┐      ┌─────────┐
│  User   │      │   Bot   │      │Telegram │
└────┬────┘      └────┬────┘      └────┬────┘
     │                │                │
     │  /topup        │                │
     │───────────────>│                │
     │                │                │
     │  Choose method:│                │
     │  [💳 Card]     │                │
     │  [⭐ Stars]    │                │
     │<───────────────│                │
     │                │                │
     │  Click [Stars] │                │
     │───────────────>│                │
     │                │                │
     │                │  createInvoiceLink
     │                │───────────────>│
     │                │                │
     │                │  {invoice_url} │
     │                │<───────────────│
     │                │                │
     │  Choose stars: │                │
     │  [50⭐ ~$1]    │                │
     │  [250⭐ ~$5]   │                │
     │  [500⭐ ~$10]  │                │
     │<───────────────│                │
     │                │                │
     │  Click [250⭐] │                │
     │───────────────>│                │
     │                │                │
     │  Invoice message                │
     │  [Pay 250⭐]   │                │
     │<───────────────────────────────│
     │                │                │
     │  User pays     │                │
     │  via Telegram  │                │
     │───────────────────────────────>│
     │                │                │
     │                │ pre_checkout_query
     │                │<───────────────│
     │                │                │
     │                │ answer: OK     │
     │                │───────────────>│
     │                │                │
     │                │ successful_payment
     │                │<───────────────│
     │                │                │
     │                │ [Update balance]
     │                │ [Send receipt] │
     │                │                │
     │  ✅ $5 added!  │                │
     │<───────────────│                │
     │                │                │
```

### 2. Stars Implementation

```python
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message

# Stars to USD conversion (approximate)
STARS_PACKAGES = [
    {"stars": 50, "usd": 1.00, "label": "50 ⭐ (~$1)"},
    {"stars": 250, "usd": 5.00, "label": "250 ⭐ (~$5)"},
    {"stars": 500, "usd": 10.00, "label": "500 ⭐ (~$10)"},
    {"stars": 1000, "usd": 20.00, "label": "1000 ⭐ (~$20)"},
]


@router.message(F.text == "⭐ Telegram Stars")
async def stars_payment_menu(message: Message):
    """Show Stars payment options."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=pkg["label"],
            callback_data=f"stars_pay:{pkg['stars']}"
        )]
        for pkg in STARS_PACKAGES
    ])
    
    await message.answer(
        "Choose amount to add:\n\n"
        "⭐ Telegram Stars - instant, no fees!",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("stars_pay:"))
async def create_stars_invoice(callback: CallbackQuery):
    """Create Stars invoice."""
    stars = int(callback.data.split(":")[1])
    package = next(p for p in STARS_PACKAGES if p["stars"] == stars)
    
    # Generate unique payload
    payload = f"topup:{callback.from_user.id}:{int(time.time())}"
    
    # Store pending payment
    await redis.setex(
        f"pending_stars:{payload}",
        3600,
        json.dumps({
            "user_id": callback.from_user.id,
            "stars": stars,
            "usd": package["usd"]
        })
    )
    
    # Create invoice
    prices = [LabeledPrice(
        label=f"Balance top-up ${package['usd']:.2f}",
        amount=stars  # In Stars
    )]
    
    await callback.message.answer_invoice(
        title="KikuAI Balance Top-up",
        description=f"Add ${package['usd']:.2f} to your KikuAI balance",
        payload=payload,
        currency="XTR",  # Telegram Stars currency code
        prices=prices,
        provider_token=""  # Empty for Stars
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Validate payment before processing."""
    
    # Get pending payment data
    pending = await redis.get(f"pending_stars:{pre_checkout.invoice_payload}")
    
    if not pending:
        await pre_checkout.answer(
            ok=False,
            error_message="Payment session expired. Please try again."
        )
        return
    
    # All good - confirm
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_stars_payment(message: Message):
    """Process successful Stars payment."""
    
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    # Get payment data
    pending = await redis.get(f"pending_stars:{payload}")
    if not pending:
        logger.error(f"No pending payment for {payload}")
        return
    
    data = json.loads(pending)
    user_id = data["user_id"]
    amount_usd = data["usd"]
    stars = data["stars"]
    
    # Check idempotency
    if await redis.get(f"stars_processed:{payload}"):
        return
    
    # Update balance
    await update_balance_atomic(
        user_id=user_id,
        amount=amount_usd,
        transaction={
            "id": f"txn_stars_{payment.telegram_payment_charge_id}",
            "type": "topup",
            "amount_usd": amount_usd,
            "source": "telegram_stars",
            "stars_amount": stars,
            "created_at": datetime.utcnow().isoformat()
        }
    )
    
    # Mark as processed
    await redis.setex(f"stars_processed:{payload}", 604800, "1")
    
    # Clean up pending
    await redis.delete(f"pending_stars:{payload}")
    
    # Send confirmation
    balance = await get_balance(user_id)
    await message.answer(
        f"✅ Payment successful!\n\n"
        f"⭐ Stars spent: {stars}\n"
        f"💰 Added: ${amount_usd:.2f}\n"
        f"📈 New balance: ${balance:.2f}\n\n"
        f"Thank you for your purchase!"
    )
```

## Balance Update Flow

### Atomic Balance Update

```python
async def update_balance_atomic(
    user_id: int,
    amount: float,
    transaction: dict
) -> float:
    """
    Atomically update user balance and record transaction.
    Uses Lua script for atomicity.
    """
    
    lua_script = """
    -- Keys: user_key, transactions_key
    -- Args: amount, transaction_json
    
    local user_key = KEYS[1]
    local transactions_key = KEYS[2]
    local amount = tonumber(ARGV[1])
    local transaction = ARGV[2]
    
    -- Get current balance
    local current = redis.call('HGET', user_key, 'balance_usd')
    if not current then current = '0' end
    
    local new_balance = tonumber(current) + amount
    
    -- Prevent negative balance
    if new_balance < 0 then
        return {err = 'insufficient_balance', balance = current}
    end
    
    -- Update balance
    redis.call('HSET', user_key, 'balance_usd', tostring(new_balance))
    
    -- Add transaction to list
    redis.call('RPUSH', transactions_key, transaction)
    
    -- Keep only last 1000 transactions
    redis.call('LTRIM', transactions_key, -1000, -1)
    
    -- Update last_active
    redis.call('HSET', user_key, 'last_active_at', ARGV[3])
    
    return {ok = 'success', balance = tostring(new_balance)}
    """
    
    # Add balance before/after to transaction
    current_balance = await get_balance(user_id)
    transaction["balance_before"] = current_balance
    transaction["balance_after"] = current_balance + amount
    
    result = await redis.eval(
        lua_script,
        2,
        f"user:{user_id}",
        f"transactions:{user_id}",
        str(amount),
        json.dumps(transaction),
        datetime.utcnow().isoformat()
    )
    
    if result.get("err"):
        raise InsufficientBalanceError(result["balance"])
    
    new_balance = float(result["balance"])
    
    # Check for low balance warning
    if new_balance < 5.0:
        await check_low_balance_notification(user_id, new_balance)
    
    return new_balance
```

## Edge Cases

### 1. Duplicate Webhooks

**Problem:** Paddle may send the same webhook multiple times.

**Solution:** Idempotency keys

```python
async def is_duplicate_webhook(event_id: str) -> bool:
    """Check if webhook was already processed."""
    key = f"webhook:processed:{event_id}"
    
    # SETNX returns True only if key didn't exist
    was_new = await redis.setnx(key, "1")
    if was_new:
        await redis.expire(key, 604800)  # 7 days
    
    return not was_new
```

### 2. Failed Payments

**Problem:** User's card is declined.

**Solution:** Clear pending state, notify user

```python
async def process_failed_payment(data: dict, custom_data: dict):
    """Handle failed payment."""
    
    user_id = int(custom_data.get("user_id"))
    error_code = data.get("error", {}).get("code")
    
    # Clear any pending state
    checkout_id = data.get("checkout_id")
    await redis.delete(f"pending_payment:{checkout_id}")
    
    # Map error codes to user-friendly messages
    error_messages = {
        "card_declined": "Your card was declined. Please try another payment method.",
        "insufficient_funds": "Insufficient funds. Please try a different card.",
        "expired_card": "Your card has expired. Please update your payment method.",
    }
    
    message = error_messages.get(
        error_code,
        "Payment failed. Please try again or contact support."
    )
    
    await send_notification(user_id, f"❌ Payment failed\n\n{message}")
```

### 3. Refunds

**Problem:** User requests refund or chargeback.

**Solution:** Deduct balance, handle negative balance

```python
async def process_refund(data: dict, custom_data: dict):
    """Handle payment refund."""
    
    user_id = int(custom_data.get("user_id"))
    refund_amount = float(data.get("amount", 0))
    original_transaction_id = data.get("original_transaction_id")
    
    # Check if refund already processed
    if await redis.get(f"refund:{original_transaction_id}"):
        return
    
    # Get current balance
    current_balance = await get_balance(user_id)
    
    # Deduct refund amount (may go negative)
    new_balance = await update_balance_atomic(
        user_id=user_id,
        amount=-refund_amount,
        transaction={
            "id": f"txn_refund_{original_transaction_id}",
            "type": "refund",
            "amount_usd": -refund_amount,
            "source": "paddle",
            "original_transaction_id": original_transaction_id,
            "created_at": datetime.utcnow().isoformat()
        }
    )
    
    # Mark processed
    await redis.setex(f"refund:{original_transaction_id}", 604800, "1")
    
    # Notify user
    await send_notification(
        user_id,
        f"ℹ️ Refund processed\n\n"
        f"💸 Refunded: ${refund_amount:.2f}\n"
        f"📉 New balance: ${new_balance:.2f}"
    )
    
    # If balance is negative, suspend API access
    if new_balance < 0:
        await suspend_api_access(user_id, reason="negative_balance")
```

### 4. Partial Payments

**Problem:** User paid less than expected (shouldn't happen with Paddle, but handle it).

**Solution:** Credit whatever was paid

```python
async def validate_payment_amount(expected: float, received: float) -> float:
    """Validate payment amount."""
    
    # Allow small rounding differences
    if abs(expected - received) < 0.10:
        return received
    
    # If received less, log warning but credit what was paid
    if received < expected:
        logger.warning(f"Partial payment: expected {expected}, got {received}")
        return received
    
    # If received more (unlikely), credit full amount
    if received > expected:
        logger.info(f"Overpayment: expected {expected}, got {received}")
        return received
    
    return received
```

### 5. Webhook Timeout

**Problem:** Webhook processing takes too long, Paddle retries.

**Solution:** Quick acknowledgment, async processing

```python
from asyncio import create_task

@router.post("/webhooks/paddle")
async def paddle_webhook_fast(request: Request):
    """Acknowledge webhook immediately, process async."""
    
    body = await request.body()
    
    # Verify signature synchronously (fast)
    if not verify_signature_quick(body):
        raise HTTPException(401)
    
    # Schedule async processing
    create_task(process_webhook_async(body))
    
    # Return immediately
    return {"status": "accepted"}


async def process_webhook_async(body: bytes):
    """Process webhook in background."""
    try:
        event = json.loads(body)
        await process_event(event)
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        # Will be retried by Paddle
```

### 6. Race Conditions

**Problem:** User makes two payments simultaneously.

**Solution:** Redis atomic operations + idempotency

```python
# All balance operations use Lua scripts for atomicity
# Each payment has unique idempotency key
# Duplicate webhooks are rejected

async def acquire_payment_lock(user_id: int, payment_id: str) -> bool:
    """Acquire lock for payment processing."""
    lock_key = f"payment_lock:{user_id}:{payment_id}"
    
    # SETNX with TTL
    acquired = await redis.set(lock_key, "1", nx=True, ex=60)
    return acquired


async def release_payment_lock(user_id: int, payment_id: str):
    """Release payment lock."""
    lock_key = f"payment_lock:{user_id}:{payment_id}"
    await redis.delete(lock_key)
```

## Payment Reconciliation

### Daily Reconciliation

```python
async def reconcile_payments():
    """Daily job to reconcile payments with Paddle."""
    
    # Get all payments from last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    # From Paddle
    paddle_transactions = await paddle_service.list_transactions(
        after=yesterday.isoformat()
    )
    
    # From our database
    our_transactions = await get_transactions_since(yesterday)
    
    # Compare
    paddle_ids = {t["id"] for t in paddle_transactions if t["status"] == "completed"}
    our_ids = {t["paddle_transaction_id"] for t in our_transactions if t.get("paddle_transaction_id")}
    
    # Missing in our system
    missing = paddle_ids - our_ids
    if missing:
        logger.error(f"Missing transactions: {missing}")
        for txn_id in missing:
            await reprocess_missing_transaction(txn_id)
    
    # Extra in our system (shouldn't happen)
    extra = our_ids - paddle_ids
    if extra:
        logger.error(f"Extra transactions in our system: {extra}")
```

## Summary

### Critical Points

1. **Always verify webhooks** - HMAC signature check
2. **Always use idempotency** - Prevent duplicate processing
3. **Atomic balance updates** - Use Lua scripts
4. **Log everything** - Full audit trail
5. **Handle edge cases** - Refunds, failures, partials
6. **Notify users** - Keep them informed

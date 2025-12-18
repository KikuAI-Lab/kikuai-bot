# Payment Security - @kikuai_bot

## Overview

This document covers security measures specific to payment processing:
- Webhook signature validation
- Idempotency implementation
- Transaction isolation
- Race condition handling
- Audit logging

## Webhook Signature Validation

### Paddle Signature Verification

Paddle uses HMAC-SHA256 signatures with timestamp to prevent replay attacks.

```python
import hmac
import hashlib
import time
from fastapi import HTTPException, Header

PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET")
MAX_WEBHOOK_AGE = 300  # 5 minutes


def verify_paddle_signature(
    body: bytes,
    signature_header: str
) -> bool:
    """
    Verify Paddle webhook signature.
    
    Signature format: ts=1234567890;h1=abc123...
    """
    
    # Parse signature header
    parts = {}
    for item in signature_header.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key] = value
    
    timestamp = parts.get("ts")
    received_sig = parts.get("h1")
    
    if not timestamp or not received_sig:
        return False
    
    # Check timestamp freshness (replay attack protection)
    try:
        ts = int(timestamp)
        age = abs(int(time.time()) - ts)
        if age > MAX_WEBHOOK_AGE:
            logger.warning(f"Webhook too old: {age}s")
            return False
    except ValueError:
        return False
    
    # Compute expected signature
    # Format: timestamp:body
    signed_payload = f"{timestamp}:{body.decode('utf-8')}"
    
    expected_sig = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison (timing attack protection)
    return hmac.compare_digest(expected_sig, received_sig)


# FastAPI dependency
async def validate_paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature")
):
    """Dependency to validate Paddle webhooks."""
    
    body = await request.body()
    
    if not verify_paddle_signature(body, paddle_signature):
        # Log failed attempt
        logger.warning(
            "Invalid Paddle signature",
            extra={
                "ip": request.client.host,
                "signature": paddle_signature[:20] + "..."
            }
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )
    
    return await request.json()
```

### Telegram Stars Verification

Telegram Stars payments are verified through the Bot API pre_checkout_query flow.

```python
@router.pre_checkout_query()
async def verify_stars_payment(query: PreCheckoutQuery):
    """
    Validate Stars payment before processing.
    This is the security checkpoint for Telegram payments.
    """
    
    payload = query.invoice_payload
    
    # 1. Verify payload format
    if not payload.startswith("topup:"):
        await query.answer(ok=False, error_message="Invalid payment")
        return
    
    # 2. Verify user matches
    parts = payload.split(":")
    if len(parts) != 3:
        await query.answer(ok=False, error_message="Invalid payment")
        return
    
    expected_user_id = int(parts[1])
    if query.from_user.id != expected_user_id:
        logger.warning(
            f"User mismatch: expected {expected_user_id}, got {query.from_user.id}"
        )
        await query.answer(ok=False, error_message="Invalid payment")
        return
    
    # 3. Verify pending payment exists
    pending = await redis.get(f"pending_stars:{payload}")
    if not pending:
        await query.answer(ok=False, error_message="Payment expired")
        return
    
    # 4. Verify amount matches
    pending_data = json.loads(pending)
    if query.total_amount != pending_data["stars"]:
        logger.warning(
            f"Amount mismatch: expected {pending_data['stars']}, got {query.total_amount}"
        )
        await query.answer(ok=False, error_message="Amount mismatch")
        return
    
    # All checks passed
    await query.answer(ok=True)
```

## Idempotency Implementation

### Idempotency Key Generation

```python
import secrets
from datetime import datetime

def generate_idempotency_key(
    user_id: int,
    operation: str,
    amount: float = None
) -> str:
    """
    Generate idempotency key for payment operation.
    
    Format: {operation}:{user_id}:{timestamp}:{random}
    """
    timestamp = int(datetime.utcnow().timestamp())
    random_part = secrets.token_hex(4)
    
    if amount is not None:
        return f"{operation}:{user_id}:{timestamp}:{int(amount*100)}:{random_part}"
    
    return f"{operation}:{user_id}:{timestamp}:{random_part}"
```

### Idempotency Storage

```python
class IdempotencyManager:
    """Manage idempotent operations."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ttl = 86400 * 7  # 7 days
    
    async def check_and_store(
        self,
        key: str,
        result: dict = None
    ) -> tuple[bool, dict]:
        """
        Check if operation was already performed.
        
        Returns: (is_new, stored_result)
        - is_new=True: First time, operation should proceed
        - is_new=False: Duplicate, return stored result
        """
        
        redis_key = f"idempotency:{key}"
        
        # Try to get existing result
        existing = await self.redis.get(redis_key)
        if existing:
            return False, json.loads(existing)
        
        # If result provided, store and mark as new
        if result:
            await self.redis.setex(
                redis_key,
                self.ttl,
                json.dumps(result)
            )
        
        return True, None
    
    async def mark_completed(self, key: str, result: dict):
        """Mark operation as completed with result."""
        redis_key = f"idempotency:{key}"
        await self.redis.setex(
            redis_key,
            self.ttl,
            json.dumps(result)
        )
    
    async def mark_failed(self, key: str, error: str):
        """Mark operation as failed."""
        redis_key = f"idempotency:{key}"
        await self.redis.setex(
            redis_key,
            self.ttl,
            json.dumps({"error": error, "failed": True})
        )


# Usage in webhook handler
async def process_payment_webhook(event: dict):
    idempotency = IdempotencyManager(redis)
    
    event_id = event.get("id")
    key = f"paddle_webhook:{event_id}"
    
    is_new, existing = await idempotency.check_and_store(key)
    
    if not is_new:
        logger.info(f"Duplicate webhook: {event_id}")
        return existing
    
    try:
        result = await process_payment(event)
        await idempotency.mark_completed(key, result)
        return result
    except Exception as e:
        await idempotency.mark_failed(key, str(e))
        raise
```

## Transaction Isolation

### Atomic Balance Updates with Lua

```lua
-- update_balance.lua
-- KEYS[1] = user:{user_id}
-- KEYS[2] = transactions:{user_id}
-- KEYS[3] = idempotency:{key}
-- ARGV[1] = amount
-- ARGV[2] = transaction_json
-- ARGV[3] = idempotency_key
-- ARGV[4] = now_iso

-- Check idempotency first
local existing = redis.call('GET', KEYS[3])
if existing then
    return cjson.decode(existing)
end

-- Get current balance
local current = redis.call('HGET', KEYS[1], 'balance_usd')
current = current and tonumber(current) or 0

local amount = tonumber(ARGV[1])
local new_balance = current + amount

-- Prevent negative balance for charges
if amount < 0 and new_balance < 0 then
    return {
        success = false,
        error = 'insufficient_balance',
        current_balance = current,
        required = math.abs(amount)
    }
end

-- Parse transaction
local transaction = cjson.decode(ARGV[2])
transaction.balance_before = current
transaction.balance_after = new_balance

-- Update balance
redis.call('HSET', KEYS[1], 'balance_usd', tostring(new_balance))
redis.call('HSET', KEYS[1], 'last_active_at', ARGV[4])

-- Record transaction
redis.call('RPUSH', KEYS[2], cjson.encode(transaction))

-- Also add to recent (for quick access)
redis.call('LPUSH', KEYS[2] .. ':recent', cjson.encode(transaction))
redis.call('LTRIM', KEYS[2] .. ':recent', 0, 49)  -- Keep last 50

-- Mark as processed (idempotency)
local result = {
    success = true,
    old_balance = current,
    new_balance = new_balance,
    transaction_id = transaction.id
}
redis.call('SETEX', KEYS[3], 604800, cjson.encode(result))

return result
```

```python
# Python wrapper
async def update_balance_safe(
    user_id: int,
    amount: float,
    transaction: dict,
    idempotency_key: str
) -> dict:
    """
    Safely update balance with full transaction isolation.
    """
    
    # Load Lua script
    script = redis.register_script(load_lua_script("update_balance.lua"))
    
    result = await script(
        keys=[
            f"user:{user_id}",
            f"transactions:{user_id}",
            f"idempotency:{idempotency_key}"
        ],
        args=[
            str(amount),
            json.dumps(transaction),
            idempotency_key,
            datetime.utcnow().isoformat()
        ]
    )
    
    if not result.get("success"):
        if result.get("error") == "insufficient_balance":
            raise InsufficientBalanceError(
                current=result["current_balance"],
                required=result["required"]
            )
        raise PaymentError(result.get("error"))
    
    return result
```

## Race Condition Handling

### Distributed Locks for Critical Operations

```python
import asyncio
from contextlib import asynccontextmanager

class DistributedLock:
    """Redis-based distributed lock."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    @asynccontextmanager
    async def acquire(
        self,
        lock_name: str,
        timeout: int = 30,
        blocking_timeout: int = 10
    ):
        """
        Acquire distributed lock.
        
        Args:
            lock_name: Unique lock identifier
            timeout: How long to hold lock (seconds)
            blocking_timeout: How long to wait for lock
        """
        
        lock_key = f"lock:{lock_name}"
        lock_value = secrets.token_hex(16)
        acquired = False
        
        # Try to acquire lock with exponential backoff
        start = time.time()
        while time.time() - start < blocking_timeout:
            acquired = await self.redis.set(
                lock_key,
                lock_value,
                nx=True,
                ex=timeout
            )
            
            if acquired:
                break
            
            await asyncio.sleep(0.1)
        
        if not acquired:
            raise LockAcquisitionError(f"Could not acquire lock: {lock_name}")
        
        try:
            yield
        finally:
            # Release lock only if we still own it
            await self._release(lock_key, lock_value)
    
    async def _release(self, key: str, value: str):
        """Release lock only if we own it."""
        
        lua_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        
        await self.redis.eval(lua_script, 1, key, value)


# Usage
lock = DistributedLock(redis)

async def process_high_value_payment(user_id: int, amount: float):
    """Process payment with distributed lock for safety."""
    
    # Lock per user to prevent concurrent payments
    async with lock.acquire(f"payment:{user_id}"):
        # Safe to process - only one payment at a time per user
        result = await update_balance_safe(
            user_id=user_id,
            amount=amount,
            transaction={...},
            idempotency_key=generate_idempotency_key(user_id, "topup", amount)
        )
        return result
```

### Optimistic Concurrency Control

```python
async def update_balance_optimistic(
    user_id: int,
    amount: float,
    max_retries: int = 3
) -> float:
    """
    Update balance with optimistic concurrency control.
    Retries on conflict.
    """
    
    for attempt in range(max_retries):
        # Get current state with version
        user_data = await redis.hgetall(f"user:{user_id}")
        current_balance = float(user_data.get("balance_usd", 0))
        version = int(user_data.get("version", 0))
        
        new_balance = current_balance + amount
        
        if new_balance < 0:
            raise InsufficientBalanceError(current_balance, abs(amount))
        
        # Try to update with version check
        lua_script = """
        local version = redis.call('HGET', KEYS[1], 'version')
        if version and tonumber(version) ~= tonumber(ARGV[1]) then
            return {conflict = true}
        end
        
        redis.call('HSET', KEYS[1], 'balance_usd', ARGV[2])
        redis.call('HINCRBY', KEYS[1], 'version', 1)
        return {success = true, balance = ARGV[2]}
        """
        
        result = await redis.eval(
            lua_script,
            1,
            f"user:{user_id}",
            str(version),
            str(new_balance)
        )
        
        if result.get("success"):
            return float(result["balance"])
        
        # Conflict - retry
        if attempt < max_retries - 1:
            await asyncio.sleep(0.1 * (attempt + 1))
    
    raise ConcurrencyError("Could not update balance after retries")
```

## Audit Logging

### Payment Audit Log

```python
from enum import Enum
from dataclasses import dataclass

class AuditEventType(str, Enum):
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    REFUND_PROCESSED = "refund_processed"
    BALANCE_UPDATED = "balance_updated"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_VERIFIED = "webhook_verified"
    WEBHOOK_FAILED = "webhook_failed"


@dataclass
class AuditEntry:
    event_type: AuditEventType
    timestamp: datetime
    user_id: int
    transaction_id: str
    amount_usd: float
    details: dict
    ip_address: str = None
    success: bool = True


class PaymentAuditLogger:
    """Log all payment-related events for audit."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.retention_days = 365  # 1 year
    
    async def log(self, entry: AuditEntry):
        """Log audit entry."""
        
        # Store in Redis list (recent only)
        key = f"audit:payment:{entry.user_id}"
        await self.redis.lpush(key, json.dumps({
            "event_type": entry.event_type.value,
            "timestamp": entry.timestamp.isoformat(),
            "transaction_id": entry.transaction_id,
            "amount_usd": entry.amount_usd,
            "details": entry.details,
            "ip_address": entry.ip_address,
            "success": entry.success
        }))
        
        # Keep last 1000 per user
        await self.redis.ltrim(key, 0, 999)
        
        # Also store in global timeline
        global_key = f"audit:payment:global:{datetime.utcnow().strftime('%Y-%m-%d')}"
        await self.redis.lpush(global_key, json.dumps({
            "user_id": entry.user_id,
            "event_type": entry.event_type.value,
            "timestamp": entry.timestamp.isoformat(),
            "transaction_id": entry.transaction_id,
            "amount_usd": entry.amount_usd,
            "success": entry.success
        }))
        
        # Set expiry on global key
        await self.redis.expire(global_key, 86400 * self.retention_days)
        
        # Log to application logger too
        logger.info(
            f"AUDIT: {entry.event_type.value}",
            extra={
                "user_id": entry.user_id,
                "transaction_id": entry.transaction_id,
                "amount": entry.amount_usd,
                "success": entry.success
            }
        )


# Usage
audit = PaymentAuditLogger(redis)

async def process_webhook(event: dict, request: Request):
    # Log webhook receipt
    await audit.log(AuditEntry(
        event_type=AuditEventType.WEBHOOK_RECEIVED,
        timestamp=datetime.utcnow(),
        user_id=0,  # Unknown yet
        transaction_id=event.get("id"),
        amount_usd=0,
        details={"event_type": event.get("event_type")},
        ip_address=request.client.host
    ))
    
    # Verify webhook
    try:
        verify_signature(...)
        await audit.log(AuditEntry(
            event_type=AuditEventType.WEBHOOK_VERIFIED,
            ...
        ))
    except:
        await audit.log(AuditEntry(
            event_type=AuditEventType.WEBHOOK_FAILED,
            success=False,
            ...
        ))
        raise
```

### Audit Trail Query

```python
async def get_user_payment_audit(
    user_id: int,
    start_date: datetime = None,
    end_date: datetime = None,
    limit: int = 100
) -> list[dict]:
    """Get payment audit trail for user."""
    
    key = f"audit:payment:{user_id}"
    entries = await redis.lrange(key, 0, limit - 1)
    
    result = []
    for entry in entries:
        data = json.loads(entry)
        timestamp = datetime.fromisoformat(data["timestamp"])
        
        # Filter by date range
        if start_date and timestamp < start_date:
            continue
        if end_date and timestamp > end_date:
            continue
            
        result.append(data)
    
    return result
```

## Security Checklist for Payments

### Pre-Launch

- [ ] Paddle webhook secret configured
- [ ] Webhook signature verification tested
- [ ] Idempotency keys implemented
- [ ] Atomic balance updates verified
- [ ] Distributed locks for concurrent operations
- [ ] Audit logging enabled
- [ ] Error handling covers all edge cases
- [ ] Negative balance protection in place
- [ ] Refund processing tested

### Monitoring

- [ ] Alert on signature failures
- [ ] Alert on duplicate webhook spikes
- [ ] Alert on failed payments > threshold
- [ ] Daily reconciliation running
- [ ] Audit logs being archived

### Regular Reviews

- [ ] Monthly: Review failed payments
- [ ] Quarterly: Security audit of payment code
- [ ] Yearly: PCI compliance review (if applicable)

## Summary

1. **Always verify** - Every webhook must be signature verified
2. **Always idempotent** - Every operation must handle duplicates
3. **Always atomic** - Balance updates use Lua scripts
4. **Always logged** - Full audit trail for all operations
5. **Always monitored** - Alerts on anomalies

# Payment Test Cases - @kikuai_bot

## Overview

This document contains test scenarios for payment system verification.

## Test Categories

1. **Happy Path** - Normal successful flows
2. **Edge Cases** - Boundary conditions
3. **Error Handling** - Failure scenarios
4. **Security** - Vulnerability testing
5. **Concurrency** - Race conditions
6. **Integration** - End-to-end flows

---

## 1. Happy Path Tests

### TC-001: Successful Paddle Payment

**Preconditions:**
- User has account with balance = $0.00
- Paddle sandbox configured

**Steps:**
1. User sends `/topup` command
2. User selects "$10" option
3. User clicks "Open Payment" button
4. User completes payment in Paddle sandbox
5. Webhook received and processed

**Expected Results:**
- Balance = $10.00
- Transaction recorded with type = "topup"
- Notification sent to user
- Webhook marked as processed

**Verification:**
```bash
# Check balance via API
curl -H "Authorization: Bearer $API_KEY" \
  https://bot.kikuai.dev/api/v1/balance

# Expected: {"balance_usd": 10.00}
```

---

### TC-002: Successful Telegram Stars Payment

**Preconditions:**
- User has account
- User has Telegram Stars

**Steps:**
1. User sends `/topup` command
2. User selects "⭐ Telegram Stars"
3. User selects "250 ⭐ (~$5)"
4. User confirms payment in Telegram
5. `pre_checkout_query` answered with OK
6. `successful_payment` callback received

**Expected Results:**
- Balance increased by $5.00
- Transaction recorded
- User notified

---

### TC-003: Multiple Payments Same User

**Preconditions:**
- User has account with balance = $10.00

**Steps:**
1. User makes $5 payment (Paddle)
2. User immediately makes $10 payment (Stars)
3. Both payments complete

**Expected Results:**
- Final balance = $25.00
- Two separate transactions recorded
- Both notifications sent
- No race conditions

---

## 2. Edge Cases

### TC-010: Minimum Payment Amount

**Steps:**
1. User attempts $5 payment (minimum)
2. Payment completes

**Expected Results:**
- Payment accepted
- Balance updated correctly

---

### TC-011: Maximum Payment Amount

**Steps:**
1. User attempts $1000 payment (maximum)
2. Payment completes

**Expected Results:**
- Payment accepted
- Balance updated correctly

---

### TC-012: Below Minimum Payment

**Steps:**
1. User attempts $4.99 payment (below minimum)

**Expected Results:**
- Error: "Minimum amount is $5"
- No checkout created
- No balance change

---

### TC-013: Above Maximum Payment

**Steps:**
1. User attempts $1001 payment (above maximum)

**Expected Results:**
- Error: "Maximum amount is $1000"
- No checkout created
- No balance change

---

### TC-014: User With Existing Pending Payment

**Steps:**
1. User creates payment checkout (but doesn't complete)
2. User creates another payment checkout

**Expected Results:**
- Second checkout created
- Both checkouts valid
- Only completed payment updates balance

---

### TC-015: Payment After Long Delay

**Steps:**
1. User creates checkout
2. User completes payment after 50 minutes
3. Webhook received

**Expected Results:**
- Payment processed successfully
- Balance updated
- (Pending payment key may have expired - handle gracefully)

---

### TC-016: Fractional Amounts

**Steps:**
1. User pays $25.50

**Expected Results:**
- Balance = $25.50 (exact amount)
- No rounding errors

---

## 3. Error Handling

### TC-020: Card Declined

**Steps:**
1. User creates Paddle checkout
2. User enters declined card (4000 0000 0000 0002 in sandbox)
3. Paddle returns failure

**Expected Results:**
- `transaction.payment_failed` webhook received
- User notified of failure
- No balance change
- Pending payment cleared

---

### TC-021: Expired Card

**Steps:**
1. User uses expired card in Paddle

**Expected Results:**
- User-friendly error message
- No balance change

---

### TC-022: Insufficient Funds

**Steps:**
1. User's card has insufficient funds

**Expected Results:**
- Appropriate error message
- No balance change

---

### TC-023: Timeout During Payment

**Steps:**
1. User creates checkout
2. User starts payment but closes browser
3. Session expires

**Expected Results:**
- No webhook (no payment made)
- User can retry with new checkout
- No partial state

---

### TC-024: Webhook Server Error

**Steps:**
1. Payment completes at Paddle
2. Our server returns 500
3. Paddle retries

**Expected Results:**
- Paddle retries webhook
- Eventually processed (idempotent)
- Balance updated only once

---

### TC-025: Invalid Webhook Signature

**Steps:**
1. Send webhook with tampered signature

**Expected Results:**
- 401 Unauthorized
- Logged as security event
- No processing

---

### TC-026: Malformed Webhook Payload

**Steps:**
1. Send webhook with invalid JSON

**Expected Results:**
- 400 Bad Request
- Error logged
- No processing

---

## 4. Security Tests

### TC-030: Duplicate Webhook (Replay Attack)

**Steps:**
1. Payment completes, webhook processed
2. Same webhook sent again (replay)

**Expected Results:**
- Second webhook returns "already_processed"
- Balance NOT doubled
- Idempotency key prevents duplicate

---

### TC-031: Webhook Forgery

**Steps:**
1. Craft fake webhook with valid format but invalid signature

**Expected Results:**
- 401 Unauthorized
- Security event logged
- No balance change

---

### TC-032: Amount Manipulation

**Steps:**
1. Payment initiated for $10
2. Webhook claims $100

**Expected Results:**
- Validate amount against Paddle API
- Only credit actual amount paid
- Log discrepancy for review

---

### TC-033: User ID Manipulation

**Steps:**
1. User A initiates payment
2. Attacker modifies custom_data to User B's ID

**Expected Results:**
- Signature check fails (custom_data is signed)
- No processing

---

### TC-034: Timing Attack on Signature

**Steps:**
1. Time signature verification with different inputs

**Expected Results:**
- Constant-time comparison used
- No timing difference exploitable

---

### TC-035: Old Webhook Replay

**Steps:**
1. Replay webhook from 6+ minutes ago

**Expected Results:**
- Timestamp check fails
- Webhook rejected

---

## 5. Concurrency Tests

### TC-040: Simultaneous Payments

**Steps:**
1. User A and User B complete payments at exact same time
2. Both webhooks arrive simultaneously

**Expected Results:**
- Both processed correctly
- No data corruption
- Correct balances for both

---

### TC-041: Same User Concurrent Payments

**Steps:**
1. User creates two payment sessions
2. Both complete simultaneously
3. Both webhooks arrive together

**Expected Results:**
- Both credited correctly
- Balance = sum of both payments
- Two separate transactions

**Verification Script:**
```python
import asyncio
import aiohttp

async def simulate_concurrent_webhooks():
    async with aiohttp.ClientSession() as session:
        # Generate two valid webhooks
        webhook1 = generate_test_webhook(user_id=123, amount=10)
        webhook2 = generate_test_webhook(user_id=123, amount=20)
        
        # Send simultaneously
        tasks = [
            session.post(WEBHOOK_URL, json=webhook1, headers=HEADERS),
            session.post(WEBHOOK_URL, json=webhook2, headers=HEADERS)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Both should succeed
        assert all(r.status == 200 for r in responses)
        
        # Check final balance
        balance = await get_balance(user_id=123)
        assert balance == 30.0  # $10 + $20
```

---

### TC-042: Balance Update Race

**Steps:**
1. User has balance = $50
2. API call charges $30 (for API usage)
3. Payment of $20 arrives simultaneously

**Expected Results:**
- Final balance = $40 (50 - 30 + 20)
- Both operations succeed
- No lost updates

---

### TC-043: Concurrent Refund and Payment

**Steps:**
1. User has payment completing
2. Previous payment being refunded simultaneously

**Expected Results:**
- Both operations complete atomically
- Balance reflects both changes
- Correct transaction order

---

## 6. Integration Tests

### TC-050: Full Paddle Flow E2E

**Type:** End-to-End

**Steps:**
1. Start with new user (balance = 0)
2. `/start` → Create account
3. `/topup` → Select $25
4. Complete Paddle checkout (sandbox)
5. Wait for webhook
6. `/balance` → Verify $25
7. Make API request (cost $0.01)
8. `/balance` → Verify $24.99

**Verification:**
```bash
# Automated test script
./scripts/test_paddle_e2e.sh
```

---

### TC-051: Full Stars Flow E2E

**Type:** End-to-End

**Steps:**
1. User with account
2. `/topup` → Select Stars
3. Pay 250 Stars
4. Verify balance increased

*Note: Requires manual testing with real Telegram Stars*

---

### TC-052: Webhook Reconciliation

**Steps:**
1. Process 100 test payments
2. Run reconciliation job
3. Compare with Paddle dashboard

**Expected Results:**
- All payments match
- No missing transactions
- No duplicates

---

### TC-053: Cross-Method Payments

**Steps:**
1. User pays $10 via Paddle
2. User pays $5 via Stars
3. Check total balance

**Expected Results:**
- Balance = $15
- Two separate transactions
- Both sources tracked

---

## Test Data

### Paddle Sandbox Cards

| Card Number | Result |
|-------------|--------|
| 4242 4242 4242 4242 | Success |
| 4000 0000 0000 0002 | Declined |
| 4000 0000 0000 9995 | Insufficient funds |
| 4000 0000 0000 0069 | Expired |

### Test Users

| User ID | Description |
|---------|-------------|
| 111111111 | New user (no balance) |
| 222222222 | User with $100 balance |
| 333333333 | User with negative balance |
| 444444444 | Suspended user |

---

## Test Automation

### Unit Tests

```python
# tests/test_payments.py

import pytest
from app.services.payment import (
    verify_paddle_signature,
    generate_idempotency_key,
    update_balance_atomic
)

class TestSignatureVerification:
    def test_valid_signature(self):
        body = b'{"event_type": "test"}'
        signature = generate_test_signature(body)
        assert verify_paddle_signature(body, signature)
    
    def test_invalid_signature(self):
        body = b'{"event_type": "test"}'
        assert not verify_paddle_signature(body, "invalid")
    
    def test_tampered_body(self):
        body = b'{"event_type": "test"}'
        signature = generate_test_signature(body)
        tampered = b'{"event_type": "hack"}'
        assert not verify_paddle_signature(tampered, signature)
    
    def test_old_timestamp(self):
        old_ts = int(time.time()) - 400  # 6+ minutes ago
        signature = f"ts={old_ts};h1=xxx"
        assert not verify_paddle_signature(b'{}', signature)


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_first_call_succeeds(self, redis):
        key = generate_idempotency_key(123, "topup", 10.0)
        is_new, _ = await idempotency.check_and_store(key)
        assert is_new is True
    
    @pytest.mark.asyncio
    async def test_duplicate_rejected(self, redis):
        key = generate_idempotency_key(123, "topup", 10.0)
        await idempotency.check_and_store(key)
        is_new, _ = await idempotency.check_and_store(key)
        assert is_new is False


class TestBalanceUpdate:
    @pytest.mark.asyncio
    async def test_add_to_balance(self, redis):
        # Setup: user with $10
        await setup_user(123, balance=10.0)
        
        # Add $5
        new = await update_balance_atomic(123, 5.0, {})
        
        assert new == 15.0
    
    @pytest.mark.asyncio
    async def test_prevent_negative(self, redis):
        await setup_user(123, balance=10.0)
        
        with pytest.raises(InsufficientBalanceError):
            await update_balance_atomic(123, -15.0, {})
```

### Integration Tests

```python
# tests/integration/test_paddle_webhook.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

class TestPaddleWebhook:
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_valid_webhook(self, client, mock_signature):
        response = client.post(
            "/api/v1/webhooks/paddle",
            json={"event_type": "transaction.completed", ...},
            headers={"Paddle-Signature": mock_signature}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "processed"
    
    def test_invalid_signature(self, client):
        response = client.post(
            "/api/v1/webhooks/paddle",
            json={"event_type": "transaction.completed"},
            headers={"Paddle-Signature": "invalid"}
        )
        assert response.status_code == 401
```

---

## Test Environment Setup

### 1. Paddle Sandbox

```bash
# Set environment
export PADDLE_ENVIRONMENT=sandbox
export PADDLE_API_KEY=test_xxx
export PADDLE_WEBHOOK_SECRET=whsec_xxx
```

### 2. Redis Test Instance

```bash
# Start test Redis
docker run --name redis-test -p 6380:6379 -d redis:7-alpine

export REDIS_URL=redis://localhost:6380/0
```

### 3. Run Tests

```bash
# Unit tests
pytest tests/test_payments.py -v

# Integration tests
pytest tests/integration/ -v

# All tests with coverage
pytest --cov=app --cov-report=html
```

---

## Manual Testing Checklist

### Before Release

- [ ] TC-001: Paddle happy path works
- [ ] TC-002: Stars payment works
- [ ] TC-020: Card decline handled
- [ ] TC-030: Duplicate webhook rejected
- [ ] TC-031: Invalid signature rejected
- [ ] TC-050: Full E2E flow works

### Regular Testing

- [ ] Weekly: Full E2E test
- [ ] After deploy: Smoke test (TC-001)
- [ ] Monthly: All security tests

# Paddle Integration

Detailed guide for integrating Paddle payments in KikuAI Bot.

## Overview

Paddle is used for traditional card payments (Visa, Mastercard, PayPal).

## Configuration

```bash
# .env
PADDLE_API_KEY=your_api_key
PADDLE_WEBHOOK_SECRET=your_webhook_secret
PADDLE_ENVIRONMENT=sandbox  # or production
```

## API Endpoints

### Create Checkout

```
POST /api/v1/payment/topup
```

Request:
```json
{
  "user_id": 12345,
  "amount_usd": 10.00,
  "method": "paddle"
}
```

Response:
```json
{
  "payment_id": "txn_123",
  "status": "pending",
  "checkout_url": "https://checkout.paddle.com/..."
}
```

### Webhook Handler

```
POST /api/v1/webhooks/paddle
Headers: Paddle-Signature: ts=123;h1=signature
```

Events processed:
- `transaction.completed` - Payment successful
- `transaction.payment_failed` - Payment failed  
- `transaction.refunded` - Refund processed

## Implementation Details

### PaddleProvider

Located in `api/services/payment_engine.py`:

```python
class PaddleProvider(PaymentProvider):
    async def create_checkout(...) -> PaymentResult:
        # Creates Paddle transaction with custom_data
        # Returns checkout URL for user
        
    async def verify_webhook(event) -> bool:
        # HMAC-SHA256 signature verification
        # Timestamp validation (5 min max age)
        
    async def process_webhook(event) -> Transaction:
        # Handles completed/failed/refunded events
        # Creates Transaction for balance update
```

### Signature Verification

```python
# Paddle sends: Paddle-Signature: ts=123;h1=abc...
signed_payload = f"{timestamp}:{raw_body}"
expected = hmac.new(secret, signed_payload, sha256).hexdigest()
```

## Testing

### Unit Tests

```bash
pytest tests/test_paddle_provider.py -v
```

### Sandbox Testing

1. Set `PADDLE_ENVIRONMENT=sandbox`
2. Use test card: `4111 1111 1111 1111`
3. Check webhook events in Paddle dashboard

## Error Handling

| Error | Action |
|-------|--------|
| Invalid signature | Return 200 (prevent retry) |
| Missing user_id | Log and ignore |
| API timeout | Retry with backoff |
| Server error | Return 500 (trigger retry) |

## Security Checklist

- ✅ Verify webhook signatures
- ✅ Check timestamp freshness (5 min max)
- ✅ Use HTTPS for webhooks
- ✅ Store webhook_secret securely
- ✅ Idempotency on all operations

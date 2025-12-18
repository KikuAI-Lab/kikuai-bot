# Testing Guide - KikuAI Bot

## Pre-Deployment Testing

### 1. Local Environment Test

```bash
# Start services
cd kikuai-bot
docker-compose up --build

# Check logs
docker-compose logs -f
```

### 2. Bot Commands Test

Open `@kikuai_bot` in Telegram and test:

1. **`/start`**
   - Should create user account
   - Should generate API key
   - Should show welcome message

2. **`/help`**
   - Should show help message

3. **`/balance`**
   - Should show current balance (initially $0.00)

4. **`/usage`**
   - Should show usage statistics

5. **`/topup`**
   - Should show payment method selection
   - Test Paddle checkout (use test card in sandbox)
   - Test Telegram Stars invoice

### 3. API Endpoints Test

```bash
# Health check
curl http://localhost:8000/healthz

# Metrics
curl http://localhost:8000/metrics

# Get API key (from bot)
API_KEY="your_api_key_from_bot"

# Get balance
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/balance

# Get usage
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/usage

# Test proxy (requires balance)
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/proxy/llm \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}'
```

### 4. Payment Flow Test

#### Paddle Payment

1. Send `/topup` in bot
2. Select "Card (Paddle)"
3. Enter amount (e.g., $10)
4. Complete checkout with test card:
   - Card: `4111 1111 1111 1111`
   - Expiry: Any future date
   - CVV: Any 3 digits
5. Verify:
   - Balance updated in bot
   - Notification received
   - Transaction recorded

#### Telegram Stars Payment

1. Send `/topup` in bot
2. Select "Telegram Stars"
3. Enter amount
4. Confirm invoice
5. Verify:
   - Balance updated
   - Notification received

### 5. Webhook Test

```bash
# Test webhook endpoint (should return error without signature)
curl -X POST http://localhost:8000/api/webhooks/paddle \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

## Post-Deployment Testing

### 1. Production Health Check

```bash
# Health
curl https://kikuai.dev/healthz

# Should return: {"status":"ok"}
```

### 2. Production API Test

```bash
# Get API key from bot
API_KEY="your_api_key"

# Test endpoints
curl -H "X-API-Key: $API_KEY" https://kikuai.dev/api/v1/balance
curl -H "X-API-Key: $API_KEY" https://kikuai.dev/api/v1/usage
```

### 3. Webhook Verification

1. **In Paddle Dashboard:**
   - Go to Settings → Notifications → Webhooks
   - Check webhook URL: `https://kikuai.dev/api/webhooks/paddle`
   - Verify events are selected:
     - `transaction.completed`
     - `transaction.payment_failed`
     - `transaction.refunded`

2. **Test Webhook:**
   ```bash
   # This should return error (no signature)
   curl -X POST https://kikuai.dev/api/webhooks/paddle \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

3. **Real Webhook Test:**
   - Make a test payment in Paddle
   - Check Paddle Dashboard → Webhooks → Recent events
   - Verify webhook was received and processed
   - Check bot logs: `docker logs kikuai-bot-api-1`

### 4. End-to-End Test

1. **Create Account:**
   - Open `@kikuai_bot`
   - Send `/start`
   - Save API key

2. **Add Balance:**
   - Send `/topup`
   - Complete payment (Paddle or Stars)
   - Verify balance updated

3. **Use API:**
   ```bash
   curl -X POST \
     -H "X-API-Key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     https://kikuai.dev/api/v1/proxy/llm \
     -d '{
       "model": "gpt-4",
       "messages": [{"role": "user", "content": "Hello"}]
     }'
   ```

4. **Verify:**
   - Request succeeded
   - Balance deducted
   - Usage updated

## Troubleshooting

### Bot not responding

```bash
# Check bot logs
docker logs kikuai-bot-bot-1

# Check if bot is running
docker ps | grep kikuai-bot-bot
```

### API not accessible

```bash
# Check API logs
docker logs kikuai-bot-api-1

# Check Nginx
docker logs nginx | grep bot.kikuai.dev
```

### Webhook not working

```bash
# Check API logs
docker logs kikuai-bot-api-1 | grep webhook

# Check Paddle Dashboard
# Settings → Notifications → Webhooks → Recent events
```

### Payment not processing

```bash
# Check payment engine logs
docker logs kikuai-bot-api-1 | grep payment

# Check Redis
docker exec kikuai-bot-redis-1 redis-cli
> KEYS user:*
> GET user:12345:balance
```

## Expected Results

### Successful Payment Flow

1. User sends `/topup` → Bot shows payment options
2. User selects method → Payment initiated
3. User completes payment → Webhook received
4. Balance updated → User notified
5. Transaction recorded → Available in `/balance`

### Successful API Call

1. Request with API key → Authenticated
2. Balance checked → Sufficient funds
3. Request proxied to ReliAPI → Response received
4. Balance deducted → Usage updated
5. Response returned → User receives data

## Test Checklist

- [ ] Bot responds to `/start`
- [ ] API key generated
- [ ] Balance shows correctly
- [ ] Paddle checkout works
- [ ] Telegram Stars invoice works
- [ ] Webhook processes payments
- [ ] Balance updates after payment
- [ ] API proxy works
- [ ] Balance deducted on API call
- [ ] 402 error on insufficient balance
- [ ] Usage tracking works
- [ ] Notifications sent











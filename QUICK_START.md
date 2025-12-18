# Quick Start Guide

## ✅ Configuration Complete

Все необходимые переменные окружения настроены:
- ✅ `TELEGRAM_BOT_TOKEN`
- ✅ `PADDLE_API_KEY`
- ✅ `PADDLE_WEBHOOK_SECRET`
- ✅ `PADDLE_ENVIRONMENT=production`
- ✅ `REDIS_URL`
- ✅ `RELIAPI_URL`
- ✅ `WEBAPP_URL`

## 🚀 Local Testing

```bash
# 1. Start services
cd kikuai-bot
docker-compose up --build

# 2. Check logs
docker-compose logs -f

# 3. Test bot
# Open @kikuai_bot in Telegram
# Send /start
# Send /topup
```

## 🌐 Production Deployment

### Step 1: Upload to Server

```bash
# From local machine
scp -r kikuai-bot root@37.27.38.186:/root/
```

### Step 2: Configure on Server

```bash
# SSH to server
ssh root@37.27.38.186

# Go to project
cd /root/kikuai-bot

# Verify .env exists and has all variables
cat .env
```

### Step 3: Setup Nginx

```bash
# Copy nginx config
cp /root/kikuai-bot/nginx.conf /root/kikuai-platform/nginx/conf.d/bot.kikuai.dev.conf

# Restart nginx
docker restart nginx
```

### Step 4: Create Docker Network

```bash
# Check if network exists
docker network ls | grep kikuai-platform_public

# If not, create it
docker network create kikuai-platform_public
```

### Step 5: Deploy

```bash
cd /root/kikuai-bot
docker-compose -f docker-compose.prod.yml up -d --build
```

### Step 6: Verify

```bash
# Health check
curl https://kikuai.dev/healthz

# Check services
docker ps | grep kikuai-bot

# Check logs
docker logs kikuai-bot-api-1
docker logs kikuai-bot-bot-1
```

## 🔍 Verify Webhook

### In Paddle Dashboard

1. Go to **Settings → Notifications → Webhooks**
2. Verify webhook URL: `https://kikuai.dev/api/webhooks/paddle`
3. Select events:
   - ✅ `transaction.completed`
   - ✅ `transaction.payment_failed`
   - ✅ `transaction.refunded`

### Test Webhook

```bash
# Test endpoint (should return error without proper signature)
curl -X POST https://kikuai.dev/api/webhooks/paddle \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

## 📊 Monitoring

- **Health:** `https://kikuai.dev/healthz`
- **Metrics:** `https://kikuai.dev/metrics`
- **Logs:** `docker logs -f kikuai-bot-api-1`

## 🐛 Troubleshooting

### Bot not responding

```bash
# Check bot logs
docker logs kikuai-bot-bot-1

# Check if bot is running
docker ps | grep kikuai-bot-bot
```

### Webhook not working

```bash
# Check API logs
docker logs kikuai-bot-api-1 | grep webhook

# Check Paddle Dashboard → Webhooks → Recent events
```

### Redis connection issues

```bash
# Test Redis
docker exec kikuai-bot-redis-1 redis-cli ping

# Check network
docker network inspect kikuai-bot-network
```

## 📝 Next Steps

1. ✅ Webhook secret added
2. ⏳ Deploy to production
3. ⏳ Test payment flow
4. ⏳ Monitor webhook events











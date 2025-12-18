# KikuAI Bot - Production Deployment Guide

## Prerequisites

- Server: 37.27.38.186 (Hetzner)
- Docker and Docker Compose installed
- Nginx configured (see `nginx.conf`)
- Paddle webhook secret obtained

## Step 1: Get Paddle Webhook Secret

1. Login to [Paddle Dashboard](https://vendors.paddle.com/)
2. Go to **Settings → Notifications → Webhooks**
3. Find webhook with URL: `https://kikuai.dev/api/webhooks/paddle`
4. Click **View secret** and copy it

## Step 2: Prepare Server

```bash
# SSH to server
ssh root@37.27.38.186

# Create project directory
mkdir -p /root/kikuai-bot
cd /root/kikuai-bot
```

## Step 3: Clone/Upload Code

```bash
# Option 1: Clone from Git (if repo is public/private)
git clone <your-repo-url> /root/kikuai-bot

# Option 2: Upload via SCP (from local machine)
# scp -r kikuai-bot root@37.27.38.186:/root/
```

## Step 4: Create .env File

```bash
cd /root/kikuai-bot
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
PADDLE_API_KEY=YOUR_PADDLE_API_KEY
PADDLE_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET_HERE
PADDLE_ENVIRONMENT=production
REDIS_URL=redis://redis:6379/0
WEBAPP_URL=https://bot.kikuai.dev/webapp
RELIAPI_URL=https://reliapi.kikuai.dev
EOF

# Edit and add webhook secret
nano .env
```

## Step 5: Configure Nginx

```bash
# Copy nginx config
cp /root/kikuai-bot/nginx.conf /root/kikuai-platform/nginx/conf.d/bot.kikuai.dev.conf

# Restart nginx
docker restart nginx

# Verify config
docker exec nginx nginx -t
```

## Step 6: Create Docker Network (if needed)

```bash
# Check if network exists
docker network ls | grep kikuai-platform_public

# If not, create it
docker network create kikuai-platform_public
```

## Step 7: Deploy

```bash
cd /root/kikuai-bot

# Build and start services
docker-compose -f docker-compose.prod.yml up -d --build

# Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

## Step 8: Verify Deployment

```bash
# Health check
curl https://kikuai.dev/healthz

# Check services
docker ps | grep kikuai-bot

# Check logs
docker logs kikuai-bot-api-1
docker logs kikuai-bot-bot-1
```

## Step 9: Test Webhook

```bash
# Test webhook endpoint (should return 400/503 without proper signature)
curl -X POST https://kikuai.dev/api/webhooks/paddle \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

## Troubleshooting

### Container not starting

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Check environment variables
docker exec kikuai-bot-api-1 env | grep PADDLE
```

### Webhook not working

1. Check Paddle Dashboard → Webhooks → Recent events
2. Check API logs: `docker logs kikuai-bot-api-1`
3. Verify webhook secret matches in `.env` and Paddle Dashboard

### Nginx routing issues

```bash
# Check nginx config
docker exec nginx nginx -T | grep -A20 "bot.kikuai.dev"

# Test proxy
curl -H "Host: bot.kikuai.dev" http://localhost/api/webhooks/paddle
```

### Redis connection issues

```bash
# Check Redis
docker exec kikuai-bot-redis-1 redis-cli ping

# Check network
docker network inspect kikuai-bot-network
```

## Monitoring

- **Health:** `https://kikuai.dev/healthz`
- **Metrics:** `https://kikuai.dev/metrics` (restrict access in production)
- **Logs:** `docker logs -f kikuai-bot-api-1`

## Updates

```bash
cd /root/kikuai-bot
git pull  # or upload new code
docker-compose -f docker-compose.prod.yml up -d --build
```

## Rollback

```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Restore previous version
git checkout <previous-commit>
docker-compose -f docker-compose.prod.yml up -d --build
```


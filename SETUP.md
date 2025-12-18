# KikuAI Bot Setup Guide

## Quick Start

### 1. Environment Variables

Файл `.env` уже создан в корне проекта. Добавьте `PADDLE_WEBHOOK_SECRET`:

```bash
# Получите webhook secret из Paddle Dashboard:
# Settings → Notifications → Webhooks → View secret

# Добавьте в .env:
PADDLE_WEBHOOK_SECRET=your_webhook_secret_here
```

### 2. Paddle Webhook Configuration

1. Войдите в [Paddle Dashboard](https://vendors.paddle.com/)
2. Перейдите в **Settings → Notifications → Webhooks**
3. Добавьте новый webhook:
   - **URL:** `https://kikuai.dev/api/webhooks/paddle`
   - **Events:** Выберите:
     - `transaction.completed`
     - `transaction.payment_failed`
     - `transaction.refunded`
4. Скопируйте **Webhook Secret** и добавьте в `.env`

### 3. Local Development

```bash
cd kikuai-bot
docker-compose up --build
```

Сервисы:
- **Bot:** Telegram bot (polling)
- **API:** FastAPI на `http://localhost:8000`
- **Redis:** `localhost:6379`

### 4. Testing

#### Health Check
```bash
curl http://localhost:8000/healthz
```

#### Metrics
```bash
curl http://localhost:8000/metrics
```

#### Test Payment Flow
1. Откройте бота в Telegram: `@kikuai_bot`
2. Отправьте `/start` - создастся аккаунт
3. Отправьте `/topup` - выберите метод оплаты
4. **Paddle:** Откроется checkout, после оплаты баланс обновится
5. **Telegram Stars:** Создастся invoice, после оплаты баланс обновится

### 5. Production Deployment (Hetzner)

#### Настройка Nginx

Создайте конфиг `/root/kikuai-platform/nginx/conf.d/bot.kikuai.dev.conf`:

```nginx
server {
    listen 80;
    server_name bot.kikuai.dev kikuai.dev;
    
    # Webhook endpoint (без /v1)
    location /api/webhooks/ {
        proxy_pass http://kikuai-bot-api-1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API endpoints
    location /api/v1/ {
        proxy_pass http://kikuai-bot-api-1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Web Apps
    location /webapp/ {
        proxy_pass http://kikuai-bot-api-1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Health check
    location /healthz {
        proxy_pass http://kikuai-bot-api-1:8000;
    }
}
```

#### Docker Compose на сервере

```bash
# На сервере 37.27.38.186
cd /root/kikuai-bot
docker-compose -f docker-compose.prod.yml up -d --build
```

#### Environment Variables на сервере

Создайте `.env` на сервере с production значениями:

```bash
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
PADDLE_API_KEY=YOUR_PADDLE_API_KEY
PADDLE_WEBHOOK_SECRET=your_production_webhook_secret
PADDLE_ENVIRONMENT=production
REDIS_URL=redis://redis:6379/0
WEBAPP_URL=https://bot.kikuai.dev/webapp
RELIAPI_URL=https://reliapi.kikuai.dev
```

## Troubleshooting

### Webhook не работает

1. Проверьте, что URL доступен:
   ```bash
   curl -X POST https://kikuai.dev/api/webhooks/paddle \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

2. Проверьте логи:
   ```bash
   docker logs kikuai-bot-api-1
   ```

3. Проверьте подпись в Paddle Dashboard → Webhooks → Recent events

### Баланс не обновляется

1. Проверьте Redis:
   ```bash
   docker exec -it kikuai-bot-redis-1 redis-cli
   > KEYS user:*
   > GET user:12345:balance
   ```

2. Проверьте логи бота:
   ```bash
   docker logs kikuai-bot-bot-1
   ```

## API Endpoints

- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /api/v1/webhooks/paddle` - Paddle webhook
- `POST /api/webhooks/paddle` - Paddle webhook (без /v1)
- `POST /api/v1/payment/topup` - Create payment
- `GET /api/v1/payment/{payment_id}` - Get payment status
- `POST /api/v1/proxy/llm` - Proxy to ReliAPI

## Security Notes

- Webhook secret должен быть уникальным и храниться в `.env`
- Не коммитьте `.env` в git
- Используйте HTTPS в production
- Проверяйте подпись всех webhook событий


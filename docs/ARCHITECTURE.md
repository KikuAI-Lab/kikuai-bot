# Architecture - @kikuai_bot

## Overview

**Purpose:** Telegram bot for managing and paying KikuAI Lab API products.

**Principles:**
- All management through Telegram bot (no web dashboards on kikuai.dev)
- Account created automatically on `/start`
- Pay-as-you-go model
- Payments via Paddle and Telegram Stars
- Telegram Web Apps for complex interfaces

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌──────────────────┐        ┌──────────────────┐                         │
│    │   Telegram App   │        │   Web App (TG)   │                         │
│    │   (Bot Client)   │        │   Dashboard UI   │                         │
│    └────────┬─────────┘        └────────┬─────────┘                         │
│             │                           │                                    │
└─────────────┼───────────────────────────┼────────────────────────────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TELEGRAM BOT LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────┐       │
│    │                    @kikuai_bot (aiogram 3.x)                   │       │
│    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │       │
│    │  │ Handlers │  │ Keyboards│  │Middleware│  │ Web App Integ│   │       │
│    │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │       │
│    └────────────────────────────────────────────────────────────────┘       │
│                                    │                                         │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND API LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────┐       │
│    │                   FastAPI Backend (port 8000)                   │       │
│    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │       │
│    │  │  Routes  │  │ Services │  │   Auth   │  │  Middleware  │   │       │
│    │  │          │  │          │  │          │  │              │   │       │
│    │  │ - users  │  │- account │  │- API key │  │- rate limit  │   │       │
│    │  │ - keys   │  │- paddle  │  │- balance │  │- logging     │   │       │
│    │  │ - payment│  │- t.stars │  │- webhook │  │- cors        │   │       │
│    │  │ - usage  │  │- usage   │  │  verify  │  │              │   │       │
│    │  │ - proxy  │  │- reliapi │  │          │  │              │   │       │
│    │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │       │
│    └────────────────────────────────────────────────────────────────┘       │
│                            │              │                                  │
└────────────────────────────┼──────────────┼──────────────────────────────────┘
                             │              │
              ┌──────────────┘              └──────────────┐
              ▼                                            ▼
┌──────────────────────────────┐          ┌──────────────────────────────┐
│         DATA LAYER           │          │     EXTERNAL SERVICES        │
├──────────────────────────────┤          ├──────────────────────────────┤
│                              │          │                              │
│  ┌────────────────────────┐  │          │  ┌────────────────────────┐  │
│  │     Redis (Primary)    │  │          │  │    Paddle Payments     │  │
│  │  - User accounts       │  │          │  │    - Checkout          │  │
│  │  - API keys            │  │          │  │    - Webhooks          │  │
│  │  - Usage tracking      │  │          │  │    - Subscriptions     │  │
│  │  - Balance             │  │          │  └────────────────────────┘  │
│  │  - Sessions            │  │          │                              │
│  │  - Rate limits         │  │          │  ┌────────────────────────┐  │
│  └────────────────────────┘  │          │  │   Telegram Stars API   │  │
│                              │          │  │    - createInvoiceLink │  │
│  ┌────────────────────────┐  │          │  │    - Pre-checkout      │  │
│  │  PostgreSQL (Optional) │  │          │  └────────────────────────┘  │
│  │  - Audit logs          │  │          │                              │
│  │  - Transaction history │  │          │  ┌────────────────────────┐  │
│  │  - Analytics           │  │          │  │      Product APIs      │  │
│  └────────────────────────┘  │          │  │  - ReliAPI             │  │
│                              │          │  │  - RouteLLM            │  │
└──────────────────────────────┘          │  │  - Future products     │  │
                                          │  └────────────────────────┘  │
                                          │                              │
                                          └──────────────────────────────┘
```

## Components

### 1. Telegram Bot (`@kikuai_bot`)

**Framework:** aiogram 3.x (async, modern)

**Structure:**
```
bot/
├── __init__.py
├── main.py              # Entry point
├── handlers/
│   ├── __init__.py
│   ├── start.py         # /start - account creation
│   ├── api_keys.py      # /api_key, /regenerate_key
│   ├── balance.py       # /balance, /usage, /history
│   ├── payment.py       # /topup - payment handling
│   ├── products.py      # /products, /product <name>
│   └── webapp.py        # Web App handlers
├── keyboards/
│   ├── __init__.py
│   ├── main_menu.py     # Main menu keyboard
│   └── inline.py        # Inline keyboards
├── middleware/
│   ├── __init__.py
│   ├── auth.py          # User authentication
│   └── logging.py       # Request logging
└── services/
    ├── __init__.py
    └── notifications.py # Notifications service
```

### 2. Backend API

**Framework:** FastAPI

**Structure:**
```
api/
├── __init__.py
├── main.py              # FastAPI app
├── routes/
│   ├── __init__.py
│   ├── users.py         # User management
│   ├── api_keys.py      # API key endpoints
│   ├── usage.py         # Usage tracking
│   ├── payment.py       # Payment endpoints
│   ├── products.py      # Product endpoints
│   └── webhooks.py      # Webhook handlers
├── services/
│   ├── __init__.py
│   ├── account.py       # Account service
│   ├── paddle.py        # Paddle integration
│   ├── telegram_stars.py# Telegram Stars
│   ├── usage_tracker.py # Usage tracking
│   └── reliapi.py       # ReliAPI integration
└── middleware/
    ├── __init__.py
    ├── auth.py          # API key validation
    ├── rate_limit.py    # Rate limiting
    └── logging.py       # Request logging
```

### 3. Web Apps

**Technology:** HTML/JS (simple start) or Nuxt 3 (if complex)

**Structure:**
```
webapp/
├── index.html           # Main Web App
├── manage_keys.html     # API keys management
├── dashboard.html       # Usage dashboard
├── payment.html         # Payment interface
└── products.html        # Products list
```

### 4. Database (Redis)

**Purpose:** Primary data store for real-time data

**Data structures:**
- User accounts
- API keys
- Usage counters
- Balance
- Rate limit counters
- Session data

### 5. External Services

**Paddle:**
- Payment processing
- Webhook handling
- Subscription management (if needed later)

**Telegram Stars API:**
- Native Telegram payments
- Alternative to Paddle

**Product APIs:**
- ReliAPI (ready)
- RouteLLM (coming)
- Future products

## Data Flow

### User Registration Flow

```
┌─────────┐                ┌─────────┐               ┌─────────┐
│  User   │                │   Bot   │               │   API   │
└────┬────┘                └────┬────┘               └────┬────┘
     │                          │                         │
     │  /start                  │                         │
     │─────────────────────────>│                         │
     │                          │                         │
     │                          │  POST /api/v1/auth/reg  │
     │                          │────────────────────────>│
     │                          │                         │
     │                          │      ┌──────────────────┤
     │                          │      │ Create user      │
     │                          │      │ Generate API key │
     │                          │      │ Store in Redis   │
     │                          │      └──────────────────┤
     │                          │                         │
     │                          │  {user_id, api_key}     │
     │                          │<────────────────────────│
     │                          │                         │
     │  Welcome! API key: xxx   │                         │
     │<─────────────────────────│                         │
     │                          │                         │
```

### API Request Flow

```
┌─────────┐         ┌─────────┐         ┌─────────┐         ┌─────────┐
│ Client  │         │Backend  │         │  Redis  │         │ ReliAPI │
└────┬────┘         └────┬────┘         └────┬────┘         └────┬────┘
     │                   │                   │                   │
     │  API Request      │                   │                   │
     │  (with API key)   │                   │                   │
     │──────────────────>│                   │                   │
     │                   │                   │                   │
     │                   │  Validate key     │                   │
     │                   │──────────────────>│                   │
     │                   │                   │                   │
     │                   │  user_id, balance │                   │
     │                   │<──────────────────│                   │
     │                   │                   │                   │
     │                   │  Check balance    │                   │
     │                   │  (if balance > 0) │                   │
     │                   │                   │                   │
     │                   │  Proxy request    │                   │
     │                   │──────────────────────────────────────>│
     │                   │                   │                   │
     │                   │  Response         │                   │
     │                   │<──────────────────────────────────────│
     │                   │                   │                   │
     │                   │  Track usage      │                   │
     │                   │  Deduct balance   │                   │
     │                   │──────────────────>│                   │
     │                   │                   │                   │
     │  Response         │                   │                   │
     │<──────────────────│                   │                   │
     │                   │                   │                   │
```

### Payment Flow (Paddle)

```
┌─────────┐         ┌─────────┐         ┌─────────┐         ┌─────────┐
│  User   │         │   Bot   │         │ Backend │         │ Paddle  │
└────┬────┘         └────┬────┘         └────┬────┘         └────┬────┘
     │                   │                   │                   │
     │  /topup           │                   │                   │
     │──────────────────>│                   │                   │
     │                   │                   │                   │
     │  [Web App Button] │                   │                   │
     │<──────────────────│                   │                   │
     │                   │                   │                   │
     │  Open Web App     │                   │                   │
     │──────────────────────────────────────>│                   │
     │                   │                   │                   │
     │                   │                   │  Create checkout  │
     │                   │                   │──────────────────>│
     │                   │                   │                   │
     │                   │                   │  checkout_url     │
     │                   │                   │<──────────────────│
     │                   │                   │                   │
     │  Redirect to Paddle checkout          │                   │
     │<──────────────────────────────────────│                   │
     │                   │                   │                   │
     │  ════════════════════════════════════════════════════════│
     │                    PAYMENT AT PADDLE                      │
     │  ════════════════════════════════════════════════════════│
     │                   │                   │                   │
     │                   │                   │  Webhook          │
     │                   │                   │<──────────────────│
     │                   │                   │                   │
     │                   │                   │  Verify & process │
     │                   │                   │  Update balance   │
     │                   │                   │                   │
     │  Payment success! │                   │                   │
     │<──────────────────│<──────────────────│                   │
     │                   │                   │                   │
```

## Technology Stack

| Component | Technology | Version | Notes |
|-----------|-----------|---------|-------|
| **Bot** | aiogram | 3.x | Async, modern |
| **Backend** | FastAPI | 0.100+ | OpenAPI, async |
| **Database** | Redis | 7.x | Real-time data |
| **Cache** | Redis | 7.x | Same instance |
| **Payments** | Paddle SDK | Latest | Server-side |
| **Payments** | Telegram Stars | Bot API | Native |
| **Web Apps** | HTML/JS | - | Simple start |
| **Container** | Docker | 24.x | Deployment |
| **Server** | Nginx | 1.24+ | Reverse proxy |

## Deployment

### Docker Compose Architecture

```yaml
services:
  bot:
    build: ./bot
    environment:
      - TELEGRAM_BOT_TOKEN=xxx
      - API_BASE_URL=http://api:8000
    depends_on:
      - api
      - redis
    networks:
      - internal

  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - PADDLE_API_KEY=xxx
    depends_on:
      - redis
    networks:
      - internal
      - public

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - internal

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./webapp:/var/www/webapp
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api
    networks:
      - public

volumes:
  redis_data:

networks:
  internal:
  public:
```

### Server Infrastructure (Hetzner)

**Server:** 37.27.38.186

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Hetzner Server (37.27.38.186)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                       Nginx (80/443)                                   │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐    │  │
│  │  │ bot.kikuai.dev  │  │reliapi.kikuai.dev│ │  api.patas.app      │    │  │
│  │  │ (webapp + api)  │  │  (ReliAPI)       │ │  (PATAS)           │    │  │
│  │  └────────┬────────┘  └────────┬─────────┘  └─────────┬──────────┘    │  │
│  └───────────┼────────────────────┼─────────────────────┼────────────────┘  │
│              │                    │                     │                    │
│  ┌───────────▼────────────────────▼─────────────────────▼────────────────┐  │
│  │                     Docker Containers                                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │  │
│  │  │  kikuai-bot  │  │   reliapi    │  │    patas     │                 │  │
│  │  │  (bot + api) │  │              │  │              │                 │  │
│  │  │    :8003     │  │    :8000     │  │    :8002     │                 │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │  │
│  │                                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │  │
│  │  │    Redis     │  │  Prometheus  │  │   Grafana    │                 │  │
│  │  │    :6379     │  │    :9090     │  │    :3000     │                 │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Security Overview

See [SECURITY.md](./SECURITY.md) for detailed security documentation.

**Key points:**
- API keys: cryptographically secure, hashed in storage
- Webhook validation: HMAC-SHA256 signature verification
- Rate limiting: per API key and per user
- HTTPS everywhere

## Scalability Overview

See [SCALABILITY.md](./SCALABILITY.md) for scaling strategies.

**Key points:**
- Horizontal scaling for bot and API
- Redis Cluster for data scaling
- Load balancing with Nginx

## API Endpoints Overview

See [API_SPEC.md](./API_SPEC.md) for full OpenAPI specification.

**Main endpoints:**
```
POST /api/v1/auth/register       # Auto-registration
GET  /api/v1/auth/me             # User info
GET  /api/v1/api_keys            # List API keys
POST /api/v1/api_keys            # Create new key
GET  /api/v1/balance             # Current balance
GET  /api/v1/usage               # Usage statistics
POST /api/v1/payment/topup       # Create payment
POST /api/v1/webhooks/paddle     # Paddle webhook
POST /api/v1/proxy/llm           # Proxy to ReliAPI
```

## Configuration

### Environment Variables

```bash
# Telegram
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_WEBHOOK_URL=https://bot.kikuai.dev/webhook

# Database
REDIS_URL=redis://localhost:6379/0

# Paddle
PADDLE_API_KEY=xxx
PADDLE_VENDOR_ID=xxx
PADDLE_WEBHOOK_SECRET=xxx
PADDLE_ENVIRONMENT=sandbox  # or production

# Products
RELIAPI_URL=https://reliapi.kikuai.dev
RELIAPI_API_KEY=xxx

# Web App
WEBAPP_URL=https://bot.kikuai.dev/webapp
```

### Product Configuration

```yaml
# config/products.yaml
products:
  - id: reliapi
    name: ReliAPI
    description: Reliability layer for API calls
    api_url: https://reliapi.kikuai.dev
    pricing:
      per_request: 0.001  # $0.001 per 1000 requests
    endpoints:
      - /proxy/llm
      - /proxy/http
    status: live

  - id: routellm
    name: RouteLLM
    description: Stable LLM routing
    api_url: https://routellm.kikuai.dev
    pricing:
      per_request: 0.002
    status: soon
```

## Monitoring

### Metrics

- Users count (total, active)
- API requests (per product, per user)
- Payments (amount, success rate)
- Usage patterns
- Errors and latency

### Logging

- All bot commands
- All API requests
- All payments
- Errors and exceptions

### Alerts

- Low user balance
- Payment failures
- API errors
- High load

## Next Steps

1. **Phase 1:** MVP (Weeks 1-2)
   - Basic bot structure
   - Account creation
   - API key management
   - ReliAPI integration

2. **Phase 2:** Payments (Week 3)
   - Paddle integration
   - Balance management
   - Webhook handling

3. **Phase 3:** Web Apps (Week 4)
   - Dashboard
   - Payment UI
   - Key management UI

4. **Phase 4:** Polish (Week 5)
   - Notifications
   - Analytics
   - Documentation

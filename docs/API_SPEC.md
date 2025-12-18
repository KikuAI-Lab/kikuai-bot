# API Specification - @kikuai_bot

## Overview

**Base URL:** `https://bot.kikuai.dev/api/v1`
**Format:** JSON
**Authentication:** API Key (Bearer token)

## Authentication

All API requests require an API key in the Authorization header:

```http
Authorization: Bearer kikuai_abc123def456...
```

Or as query parameter (less secure):
```http
GET /api/v1/balance?api_key=kikuai_abc123def456...
```

## Common Response Format

### Success Response

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-12-04T15:30:00Z"
  }
}
```

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "Your balance is too low. Please top up.",
    "details": {
      "current_balance": 0.50,
      "required": 1.00
    }
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-12-04T15:30:00Z"
  }
}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_API_KEY` | 401 | API key is invalid or missing |
| `API_KEY_DISABLED` | 403 | API key has been disabled |
| `INSUFFICIENT_BALANCE` | 402 | Balance too low for operation |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INVALID_REQUEST` | 400 | Request validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `INTERNAL_ERROR` | 500 | Server error |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable |

---

## Endpoints

### Auth & Users

#### `POST /api/v1/auth/register`

Create or retrieve user account (called by bot on /start).

**Request:**
```json
{
  "telegram_user_id": 123456789,
  "telegram_username": "johndoe",
  "telegram_first_name": "John",
  "referral_code": "REF123"  // optional
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": 123456789,
    "api_key": "kikuai_abc123def456...",
    "is_new": true,
    "balance_usd": 0.00,
    "created_at": "2025-12-04T15:30:00Z"
  }
}
```

---

#### `GET /api/v1/auth/me`

Get current user info.

**Headers:**
```
Authorization: Bearer kikuai_abc123...
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": 123456789,
    "telegram_username": "johndoe",
    "balance_usd": 45.50,
    "total_spent_usd": 154.00,
    "status": "active",
    "created_at": "2025-12-01T10:00:00Z",
    "current_usage": {
      "month": "2025-12",
      "requests": 15000,
      "tokens": 750000
    }
  }
}
```

---

### API Keys

#### `GET /api/v1/api_keys`

List all API keys for user.

**Response:**
```json
{
  "success": true,
  "data": {
    "keys": [
      {
        "id": "key_abc123",
        "name": "Production Key",
        "key_preview": "kikuai_abc...xyz",
        "status": "active",
        "last_used_at": "2025-12-04T15:00:00Z",
        "created_at": "2025-12-01T10:00:00Z"
      }
    ]
  }
}
```

---

#### `POST /api/v1/api_keys`

Create new API key.

**Request:**
```json
{
  "name": "Development Key",
  "permissions": ["reliapi:read", "reliapi:write"]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "key_def456",
    "name": "Development Key",
    "api_key": "kikuai_newkey123...",  // Only shown once!
    "status": "active",
    "created_at": "2025-12-04T15:30:00Z"
  }
}
```

> ⚠️ **Warning:** The full API key is only returned once at creation time. Store it securely.

---

#### `DELETE /api/v1/api_keys/{key_id}`

Delete (revoke) an API key.

**Response:**
```json
{
  "success": true,
  "data": {
    "deleted": true
  }
}
```

---

### Balance & Usage

#### `GET /api/v1/balance`

Get current balance.

**Response:**
```json
{
  "success": true,
  "data": {
    "balance_usd": 45.50,
    "currency": "USD",
    "low_balance_warning": false,
    "estimated_remaining_requests": 45500
  }
}
```

---

#### `GET /api/v1/usage`

Get usage statistics.

**Query Parameters:**
- `period`: `day` | `week` | `month` | `year` (default: `month`)
- `product`: Product ID filter (optional)

**Response:**
```json
{
  "success": true,
  "data": {
    "period": "2025-12",
    "summary": {
      "total_requests": 15000,
      "total_tokens": 750000,
      "total_cost_usd": 15.00
    },
    "by_product": [
      {
        "product_id": "reliapi",
        "product_name": "ReliAPI",
        "requests": 12000,
        "tokens": 600000,
        "cost_usd": 12.00
      },
      {
        "product_id": "routellm",
        "product_name": "RouteLLM",
        "requests": 3000,
        "tokens": 150000,
        "cost_usd": 3.00
      }
    ],
    "daily_breakdown": [
      {
        "date": "2025-12-04",
        "requests": 1500,
        "tokens": 75000,
        "cost_usd": 1.50
      }
    ]
  }
}
```

---

#### `GET /api/v1/history`

Get transaction history.

**Query Parameters:**
- `limit`: Number of transactions (default: 50, max: 100)
- `offset`: Pagination offset (default: 0)
- `type`: Filter by type: `topup` | `usage` | `refund`

**Response:**
```json
{
  "success": true,
  "data": {
    "transactions": [
      {
        "id": "txn_abc123",
        "type": "topup",
        "amount_usd": 10.00,
        "balance_after": 55.50,
        "source": "paddle",
        "description": "Balance top-up via Paddle",
        "created_at": "2025-12-04T15:30:00Z"
      },
      {
        "id": "txn_def456",
        "type": "usage",
        "amount_usd": -0.50,
        "balance_after": 45.50,
        "source": "reliapi",
        "description": "ReliAPI usage: 500 requests",
        "created_at": "2025-12-04T15:00:00Z"
      }
    ],
    "pagination": {
      "total": 150,
      "limit": 50,
      "offset": 0,
      "has_more": true
    }
  }
}
```

---

### Payments

#### `POST /api/v1/payment/topup`

Create payment checkout session.

**Request:**
```json
{
  "amount_usd": 10.00,
  "method": "paddle",  // "paddle" | "telegram_stars"
  "success_url": "https://bot.kikuai.dev/webapp/payment/success",
  "cancel_url": "https://bot.kikuai.dev/webapp/payment/cancel"
}
```

**Response (Paddle):**
```json
{
  "success": true,
  "data": {
    "payment_id": "pay_abc123",
    "method": "paddle",
    "checkout_url": "https://checkout.paddle.com/...",
    "amount_usd": 10.00,
    "expires_at": "2025-12-04T16:30:00Z"
  }
}
```

**Response (Telegram Stars):**
```json
{
  "success": true,
  "data": {
    "payment_id": "pay_def456",
    "method": "telegram_stars",
    "invoice_link": "https://t.me/$invoice...",
    "stars_amount": 250,
    "amount_usd": 10.00
  }
}
```

---

#### `GET /api/v1/payment/{payment_id}`

Get payment status.

**Response:**
```json
{
  "success": true,
  "data": {
    "payment_id": "pay_abc123",
    "status": "completed",  // "pending" | "completed" | "failed" | "refunded"
    "amount_usd": 10.00,
    "balance_updated": true,
    "created_at": "2025-12-04T15:30:00Z",
    "completed_at": "2025-12-04T15:32:00Z"
  }
}
```

---

### Webhooks

#### `POST /api/v1/webhooks/paddle`

Handle Paddle webhooks. **Internal endpoint.**

**Headers:**
```
Paddle-Signature: ts=1234567890;h1=abc123...
```

**Request:** Paddle webhook payload

**Response:**
```json
{
  "status": "processed"
}
```

---

### Products

#### `GET /api/v1/products`

List available products.

**Response:**
```json
{
  "success": true,
  "data": {
    "products": [
      {
        "id": "reliapi",
        "name": "ReliAPI",
        "description": "Reliability layer for API calls",
        "status": "active",
        "pricing": {
          "model": "per_request",
          "per_request": 0.001,
          "per_1k_requests": 0.10
        },
        "endpoints": [
          {
            "path": "/proxy/llm",
            "method": "POST",
            "description": "LLM API proxy with retries"
          },
          {
            "path": "/proxy/http",
            "method": "POST",
            "description": "HTTP proxy with reliability"
          }
        ],
        "documentation_url": "https://docs.kikuai.dev/reliapi"
      },
      {
        "id": "routellm",
        "name": "RouteLLM",
        "description": "Stable LLM routing",
        "status": "coming_soon"
      }
    ]
  }
}
```

---

#### `GET /api/v1/products/{product_id}`

Get product details.

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "reliapi",
    "name": "ReliAPI",
    "description": "Reliability layer for API calls",
    "long_description": "ReliAPI provides...",
    "status": "active",
    "pricing": {
      "model": "per_request",
      "per_request": 0.001
    },
    "features": [
      "Automatic retries",
      "Fallback providers",
      "Response caching"
    ],
    "quick_start": {
      "python": "import requests\n...",
      "curl": "curl -X POST ..."
    }
  }
}
```

---

### Product Proxy Endpoints

#### `POST /api/v1/proxy/llm`

Proxy request to LLM API through ReliAPI.

**Request:**
```json
{
  "provider": "openai",
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "options": {
    "retry_count": 3,
    "fallback_providers": ["anthropic"],
    "cache_ttl": 3600
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "chatcmpl-abc123",
    "choices": [...],
    "usage": {
      "prompt_tokens": 10,
      "completion_tokens": 50,
      "total_tokens": 60
    }
  },
  "meta": {
    "provider_used": "openai",
    "retries": 0,
    "cached": false,
    "cost_usd": 0.002,
    "latency_ms": 450
  }
}
```

---

#### `POST /api/v1/proxy/http`

Proxy generic HTTP request through ReliAPI.

**Request:**
```json
{
  "method": "GET",
  "url": "https://api.example.com/data",
  "headers": {
    "Authorization": "Bearer xxx"
  },
  "options": {
    "retry_count": 3,
    "timeout_ms": 5000
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status_code": 200,
    "headers": {...},
    "body": {...}
  },
  "meta": {
    "retries": 1,
    "latency_ms": 230
  }
}
```

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| All endpoints | 100 | per minute |
| `/api/v1/proxy/*` | 1000 | per minute |
| `/api/v1/payment/*` | 10 | per minute |

Rate limit headers:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1701700000
```

---

## OpenAPI Specification

```yaml
openapi: 3.1.0
info:
  title: KikuAI Bot API
  version: 1.0.0
  description: API for managing KikuAI Lab products through Telegram bot
  contact:
    name: KikuAI Lab
    url: https://kikuai.dev
    email: support@kikuai.dev

servers:
  - url: https://bot.kikuai.dev/api/v1
    description: Production
  - url: http://localhost:8000/api/v1
    description: Development

components:
  securitySchemes:
    ApiKeyAuth:
      type: http
      scheme: bearer
      bearerFormat: API Key

  schemas:
    User:
      type: object
      properties:
        user_id:
          type: integer
          format: int64
        telegram_username:
          type: string
        balance_usd:
          type: number
          format: float
        status:
          type: string
          enum: [active, suspended]
        created_at:
          type: string
          format: date-time

    ApiKey:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        key_preview:
          type: string
        status:
          type: string
          enum: [active, disabled]
        created_at:
          type: string
          format: date-time

    Transaction:
      type: object
      properties:
        id:
          type: string
        type:
          type: string
          enum: [topup, usage, refund]
        amount_usd:
          type: number
        balance_after:
          type: number
        created_at:
          type: string
          format: date-time

    Error:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
        details:
          type: object

security:
  - ApiKeyAuth: []

paths:
  /auth/me:
    get:
      summary: Get current user
      responses:
        '200':
          description: User info
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'

  /balance:
    get:
      summary: Get balance
      responses:
        '200':
          description: Balance info

  /payment/topup:
    post:
      summary: Create payment
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                amount_usd:
                  type: number
                method:
                  type: string
                  enum: [paddle, telegram_stars]
      responses:
        '200':
          description: Payment created
```

---

## SDKs and Examples

### Python

```python
import requests

class KikuAIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://bot.kikuai.dev/api/v1"
    
    def get_balance(self):
        response = requests.get(
            f"{self.base_url}/balance",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return response.json()
    
    def proxy_llm(self, provider: str, model: str, messages: list):
        response = requests.post(
            f"{self.base_url}/proxy/llm",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "provider": provider,
                "model": model,
                "messages": messages
            }
        )
        return response.json()

# Usage
client = KikuAIClient("kikuai_abc123...")
balance = client.get_balance()
print(f"Balance: ${balance['data']['balance_usd']}")
```

### cURL

```bash
# Get balance
curl -X GET https://bot.kikuai.dev/api/v1/balance \
  -H "Authorization: Bearer kikuai_abc123..."

# Proxy LLM request
curl -X POST https://bot.kikuai.dev/api/v1/proxy/llm \
  -H "Authorization: Bearer kikuai_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### JavaScript

```javascript
const KikuAI = {
  apiKey: 'kikuai_abc123...',
  baseUrl: 'https://bot.kikuai.dev/api/v1',
  
  async getBalance() {
    const response = await fetch(`${this.baseUrl}/balance`, {
      headers: { 'Authorization': `Bearer ${this.apiKey}` }
    });
    return response.json();
  },
  
  async proxyLlm(provider, model, messages) {
    const response = await fetch(`${this.baseUrl}/proxy/llm`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ provider, model, messages })
    });
    return response.json();
  }
};
```

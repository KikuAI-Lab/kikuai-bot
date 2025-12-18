# Security - @kikuai_bot

## Overview

This document outlines security measures for the KikuAI Bot platform, covering:
- API key generation and management
- Webhook validation
- Rate limiting
- Attack protection
- Data privacy (GDPR)

## API Key Security

### Key Generation

**Format:** `kikuai_{random_32_chars}`
**Example:** `kikuai_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

**Generation algorithm:**
```python
import secrets
import hashlib

def generate_api_key() -> tuple[str, str]:
    """
    Generate a cryptographically secure API key.
    Returns (key, key_hash).
    """
    # 32 bytes = 256 bits of entropy
    random_bytes = secrets.token_bytes(32)
    
    # URL-safe base64 encoding (43 chars)
    key_suffix = secrets.token_urlsafe(24)  # 24 bytes → 32 chars
    
    api_key = f"kikuai_{key_suffix}"
    
    # Store hash, not the key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    return api_key, key_hash

def validate_api_key(api_key: str, stored_hash: str) -> bool:
    """
    Validate API key against stored hash.
    Uses constant-time comparison to prevent timing attacks.
    """
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return secrets.compare_digest(key_hash, stored_hash)
```

**Key properties:**
- 256 bits of entropy
- Cryptographically random (using `secrets` module)
- URL-safe characters only
- Prefixed for easy identification (`kikuai_`)

### Key Storage

**Never store plaintext keys!**

```python
# In Redis, store only the hash
redis_client.hset(f"api_key:{key_hash}", mapping={
    "user_id": user_id,
    "created_at": datetime.utcnow().isoformat(),
    "status": "active"
})

# Lookup by key requires hashing first
def lookup_key(api_key: str):
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return redis_client.hgetall(f"api_key:{key_hash}")
```

### Key Rotation

```python
async def regenerate_api_key(user_id: int) -> str:
    """
    Regenerate API key for user.
    Old key is immediately invalidated.
    """
    # Get current key hash
    user_data = await get_user(user_id)
    old_key_hash = user_data.get("api_key_hash")
    
    # Generate new key
    new_key, new_key_hash = generate_api_key()
    
    # Atomic update: delete old, create new
    pipe = redis_client.pipeline()
    if old_key_hash:
        pipe.delete(f"api_key:{old_key_hash}")
    pipe.hset(f"api_key:{new_key_hash}", mapping={
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "active"
    })
    pipe.hset(f"user:{user_id}", "api_key_hash", new_key_hash)
    pipe.execute()
    
    return new_key  # Return to user once, never stored
```

## Webhook Security

### Paddle Webhook Verification

Paddle uses HMAC-SHA256 signature for webhook verification.

```python
import hmac
import hashlib
from fastapi import HTTPException, Header, Request

PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET")

async def verify_paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature")
) -> dict:
    """
    Verify Paddle webhook signature.
    Raises HTTPException if invalid.
    """
    body = await request.body()
    
    # Parse signature header: ts=xxx;h1=xxx
    sig_parts = {}
    for part in paddle_signature.split(";"):
        key, value = part.split("=", 1)
        sig_parts[key] = value
    
    timestamp = sig_parts.get("ts")
    received_signature = sig_parts.get("h1")
    
    if not timestamp or not received_signature:
        raise HTTPException(401, "Invalid signature format")
    
    # Check timestamp freshness (prevent replay attacks)
    if abs(int(timestamp) - time.time()) > 300:  # 5 minutes
        raise HTTPException(401, "Webhook timestamp too old")
    
    # Compute expected signature
    signed_payload = f"{timestamp}:{body.decode()}"
    expected_signature = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison
    if not hmac.compare_digest(received_signature, expected_signature):
        raise HTTPException(401, "Invalid webhook signature")
    
    return await request.json()
```

### Telegram Bot Webhook Verification

```python
from aiogram import Bot
from hashlib import sha256

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32]

async def verify_telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
) -> bool:
    """
    Verify Telegram webhook using secret token.
    """
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid Telegram webhook token")
    return True
```

## Rate Limiting

### Strategy

| Endpoint Type | Limit | Window | Scope |
|--------------|-------|--------|-------|
| Public | 20/min | 1 minute | IP |
| Auth endpoints | 5/min | 1 minute | IP |
| API (authenticated) | 100/min | 1 minute | API key |
| Proxy endpoints | 1000/min | 1 minute | API key |
| Payment endpoints | 10/min | 1 minute | User ID |

### Implementation

```python
import time
from fastapi import Request, HTTPException

class RateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.
        Returns (allowed, remaining).
        """
        now = int(time.time())
        window_start = now - window_seconds
        
        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(f"ratelimit:{key}", 0, window_start)
        
        # Count current entries
        pipe.zcard(f"ratelimit:{key}")
        
        # Add current request
        pipe.zadd(f"ratelimit:{key}", {f"{now}:{secrets.token_hex(4)}": now})
        
        # Set expiry
        pipe.expire(f"ratelimit:{key}", window_seconds)
        
        results = pipe.execute()
        current_count = results[1]
        
        if current_count >= limit:
            return False, 0
        
        return True, limit - current_count - 1
    
    async def rate_limit_middleware(
        self,
        request: Request,
        limit: int,
        window: int
    ):
        """Middleware to apply rate limiting."""
        # Determine key (API key or IP)
        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if api_key:
            key = f"apikey:{hashlib.md5(api_key.encode()).hexdigest()}"
        else:
            key = f"ip:{request.client.host}"
        
        allowed, remaining = await self.check_rate_limit(key, limit, window)
        
        # Set rate limit headers
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_limit = limit
        request.state.rate_limit_reset = int(time.time()) + window
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(request.state.rate_limit_reset),
                    "Retry-After": str(window)
                }
            )
```

### Adaptive Rate Limiting

For suspicious behavior:

```python
class AdaptiveRateLimiter(RateLimiter):
    async def check_with_backoff(self, key: str, base_limit: int, window: int):
        """
        Apply exponential backoff for repeat offenders.
        """
        # Get violation count
        violations = int(self.redis.get(f"violations:{key}") or 0)
        
        # Reduce limit based on violations
        adjusted_limit = max(1, base_limit // (2 ** min(violations, 4)))
        
        allowed, remaining = await self.check_rate_limit(
            key, adjusted_limit, window
        )
        
        if not allowed:
            # Increment violations (decay after 1 hour)
            pipe = self.redis.pipeline()
            pipe.incr(f"violations:{key}")
            pipe.expire(f"violations:{key}", 3600)
            pipe.execute()
        
        return allowed, remaining
```

## Protection Against Attacks

### SQL Injection

Not applicable (using Redis, not SQL).

For future PostgreSQL:
- Use parameterized queries only
- ORM with SQLAlchemy

### XSS Protection

Web Apps should:
```javascript
// Escape all user content
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Content Security Policy headers
app.use((req, res, next) => {
    res.setHeader(
        'Content-Security-Policy',
        "default-src 'self'; script-src 'self' https://telegram.org"
    );
    next();
});
```

### CSRF Protection

For Web Apps:
```python
from fastapi import Request
import secrets

def generate_csrf_token(session_id: str) -> str:
    """Generate CSRF token tied to session."""
    token = secrets.token_urlsafe(32)
    redis_client.setex(f"csrf:{session_id}", 3600, token)
    return token

def verify_csrf_token(session_id: str, token: str) -> bool:
    """Verify CSRF token."""
    stored = redis_client.get(f"csrf:{session_id}")
    if not stored:
        return False
    return secrets.compare_digest(stored, token)
```

### Brute Force Protection

```python
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes

async def check_brute_force(user_id: int) -> bool:
    """
    Check if user is locked out due to too many failed attempts.
    """
    key = f"failed_attempts:{user_id}"
    attempts = int(redis_client.get(key) or 0)
    
    if attempts >= MAX_LOGIN_ATTEMPTS:
        ttl = redis_client.ttl(key)
        if ttl > 0:
            raise HTTPException(
                429,
                f"Too many failed attempts. Try again in {ttl} seconds."
            )
    
    return True

async def record_failed_attempt(user_id: int):
    """Record a failed authentication attempt."""
    key = f"failed_attempts:{user_id}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCKOUT_DURATION)
    pipe.execute()

async def clear_failed_attempts(user_id: int):
    """Clear failed attempts on successful login."""
    redis_client.delete(f"failed_attempts:{user_id}")
```

### DDoS Mitigation

1. **Cloudflare/Nginx rate limiting:**
```nginx
# nginx.conf
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

server {
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
    }
}
```

2. **Request size limits:**
```python
from fastapi import Request

MAX_BODY_SIZE = 1024 * 1024  # 1MB

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.headers.get("content-length"):
        if int(request.headers["content-length"]) > MAX_BODY_SIZE:
            raise HTTPException(413, "Request body too large")
    return await call_next(request)
```

### Injection Prevention (Redis)

```python
import re

def sanitize_key(key: str) -> str:
    """
    Sanitize Redis key to prevent injection.
    Only allow alphanumeric, underscore, colon.
    """
    if not re.match(r'^[a-zA-Z0-9_:]+$', key):
        raise ValueError(f"Invalid key format: {key}")
    return key

# Usage
user_key = sanitize_key(f"user:{user_id}")
```

## Data Privacy (GDPR)

### Data Collection

**We collect only:**
- Telegram user ID (required for identification)
- Telegram username (optional, for display)
- API usage statistics
- Payment information (handled by Paddle)

**We do NOT collect:**
- Phone numbers
- Email addresses (only if user provides for receipts)
- Location data
- Message content

### Data Access

```python
async def export_user_data(user_id: int) -> dict:
    """
    Export all user data (GDPR right to access).
    """
    user = await get_user(user_id)
    transactions = await get_all_transactions(user_id)
    usage = await get_all_usage(user_id)
    
    return {
        "user": {
            "id": user_id,
            "created_at": user.get("created_at"),
            "status": user.get("status")
        },
        "transactions": transactions,
        "usage": usage,
        "exported_at": datetime.utcnow().isoformat()
    }
```

### Data Deletion

```python
async def delete_user_data(user_id: int) -> bool:
    """
    Delete all user data (GDPR right to erasure).
    """
    # Get all keys related to user
    keys_to_delete = [
        f"user:{user_id}",
        f"transactions:{user_id}",
        f"transactions:{user_id}:recent",
    ]
    
    # Find all usage keys
    for key in redis_client.scan_iter(f"usage:{user_id}:*"):
        keys_to_delete.append(key)
    
    # Find and delete API keys
    user = await get_user(user_id)
    if user and user.get("api_key_hash"):
        keys_to_delete.append(f"api_key:{user['api_key_hash']}")
    
    # Delete all keys atomically
    if keys_to_delete:
        redis_client.delete(*keys_to_delete)
    
    # Log deletion for audit
    logger.info(f"Deleted user data for {user_id}")
    
    return True
```

### Data Retention

| Data Type | Retention | Reason |
|-----------|-----------|--------|
| User account | Until deletion | Service operation |
| API keys | Until deletion | Service operation |
| Usage (monthly) | 2 years | Billing/analytics |
| Transactions | 7 years | Legal requirement |
| Sessions | 24 hours | Temporary |
| Logs | 90 days | Debugging |

## Secrets Management

### Environment Variables

```bash
# .env.example (never commit .env!)

# Telegram
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_WEBHOOK_SECRET=generated_secret

# Database
REDIS_URL=redis://localhost:6379/0

# Paddle
PADDLE_API_KEY=your_api_key
PADDLE_VENDOR_ID=your_vendor_id
PADDLE_WEBHOOK_SECRET=your_webhook_secret
PADDLE_ENVIRONMENT=sandbox

# Internal
API_SECRET_KEY=generated_32_char_secret
```

### Docker Secrets

```yaml
# docker-compose.yml
services:
  api:
    secrets:
      - paddle_api_key
      - telegram_bot_token

secrets:
  paddle_api_key:
    external: true
  telegram_bot_token:
    external: true
```

### Key Rotation

Rotate sensitive keys periodically:
- API secret key: Every 90 days
- Paddle credentials: On compromise
- Bot token: On compromise

## Logging and Monitoring

### Security Events to Log

```python
SECURITY_EVENTS = [
    "api_key_created",
    "api_key_deleted",
    "api_key_regenerated",
    "failed_authentication",
    "rate_limit_exceeded",
    "webhook_signature_invalid",
    "suspicious_activity",
    "user_deleted"
]

async def log_security_event(
    event: str,
    user_id: int = None,
    details: dict = None,
    severity: str = "info"
):
    """Log security event for audit."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "user_id": user_id,
        "details": details,
        "severity": severity
    }
    
    # Store in Redis for quick access
    redis_client.lpush("security_events", json.dumps(log_entry))
    redis_client.ltrim("security_events", 0, 9999)  # Keep last 10k
    
    # Log to file/service
    if severity == "critical":
        logger.critical(log_entry)
    elif severity == "warning":
        logger.warning(log_entry)
    else:
        logger.info(log_entry)
```

### Alerting

Critical events trigger alerts:
- Multiple failed auth attempts
- Webhook signature failures
- Unusual API usage patterns
- Rate limit violations

## Security Checklist

### Before Launch

- [ ] All secrets in environment variables
- [ ] HTTPS enforced everywhere
- [ ] Webhook signatures verified
- [ ] Rate limiting enabled
- [ ] API key hashing implemented
- [ ] Input validation on all endpoints
- [ ] Error messages don't leak info
- [ ] Security headers configured
- [ ] Logging enabled
- [ ] Backup encryption enabled

### Regular Reviews

- [ ] Monthly: Review access logs
- [ ] Quarterly: Rotate API keys
- [ ] Quarterly: Review security events
- [ ] Annually: Security audit

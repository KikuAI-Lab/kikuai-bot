# Database Schema - @kikuai_bot

## Overview

**Primary database:** Redis (real-time data, caching)
**Secondary (optional):** PostgreSQL (audit logs, analytics)

## Redis Data Model

### Key Naming Convention

```
{entity}:{identifier}:{optional_suffix}
```

Examples:
- `user:123456789` - User data
- `api_key:kikuai_abc123` - API key data
- `usage:123456789:2025-12` - Monthly usage counter

### 1. User Accounts

**Key pattern:** `user:{telegram_user_id}`
**TTL:** None (persistent)

```json
{
  "user_id": 123456789,
  "telegram_username": "@username",
  "telegram_first_name": "John",
  "api_key": "kikuai_xxx...",
  "created_at": "2025-12-01T10:00:00Z",
  "balance_usd": 10.50,
  "total_spent_usd": 45.00,
  "status": "active",
  "last_active_at": "2025-12-04T15:30:00Z",
  "settings": {
    "notifications_enabled": true,
    "low_balance_threshold": 5.0
  }
}
```

**Indexes:**
- `users:by_api_key:{api_key}` → `user_id` (for API key lookups)
- `users:active` → ZSET with last_active_at as score

### 2. API Keys

**Key pattern:** `api_key:{api_key}`
**TTL:** None (persistent)

```json
{
  "key": "kikuai_abc123def456...",
  "key_hash": "sha256:...",
  "user_id": 123456789,
  "name": "Production Key",
  "created_at": "2025-12-01T10:00:00Z",
  "last_used_at": "2025-12-04T15:30:00Z",
  "status": "active",
  "permissions": ["reliapi:read", "reliapi:write"]
}
```

**Key format:**
```
kikuai_{random_32_chars}
```

Example: `kikuai_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

### 3. Usage Tracking

**Key pattern:** `usage:{user_id}:{YYYY-MM}`
**Type:** HASH
**TTL:** 35 days (auto-cleanup old months)

```
HSET usage:123456789:2025-12
  total_requests 1500
  reliapi_requests 1000
  reliapi_tokens 50000
  routellm_requests 500
  last_updated "2025-12-04T15:30:00Z"
```

**Daily breakdown (optional):**
**Key pattern:** `usage:{user_id}:{YYYY-MM-DD}`
**Type:** HASH
**TTL:** 90 days

```
HSET usage:123456789:2025-12-04
  requests 150
  tokens 7500
```

### 4. Balance Transactions

**Key pattern:** `transactions:{user_id}`
**Type:** LIST (RPUSH for append)
**TTL:** None

```json
{
  "id": "txn_abc123",
  "type": "topup",
  "amount_usd": 10.00,
  "balance_before": 5.00,
  "balance_after": 15.00,
  "source": "paddle",
  "paddle_transaction_id": "ptx_123",
  "created_at": "2025-12-04T15:30:00Z"
}
```

**Transaction types:**
- `topup` - Balance top-up (Paddle/Stars)
- `usage` - API usage charge
- `refund` - Refund from provider
- `adjustment` - Manual adjustment

**Recent transactions (for quick display):**
**Key pattern:** `transactions:{user_id}:recent`
**Type:** LIST (LPUSH, LTRIM to 50)
**TTL:** None

### 5. Rate Limiting

**Key pattern:** `ratelimit:{user_id}:{window}`
**Type:** STRING (counter)
**TTL:** Auto (based on window)

Windows:
- `minute` - 60 seconds TTL
- `hour` - 3600 seconds TTL
- `day` - 86400 seconds TTL

```
SET ratelimit:123456789:minute 45 EX 60
SET ratelimit:kikuai_abc123:minute 45 EX 60
```

### 6. Sessions / Temporary Data

**Key pattern:** `session:{session_id}`
**TTL:** 24 hours

```json
{
  "user_id": 123456789,
  "state": "awaiting_payment",
  "data": {
    "checkout_id": "chk_123",
    "amount": 10.00
  },
  "created_at": "2025-12-04T15:30:00Z"
}
```

### 7. Webhooks Idempotency

**Key pattern:** `webhook:{provider}:{transaction_id}`
**Type:** STRING
**TTL:** 7 days

```
SET webhook:paddle:ptx_123 "processed" EX 604800
```

### 8. Products Configuration (Cached)

**Key pattern:** `products:config`
**Type:** STRING (JSON)
**TTL:** 1 hour (refreshed periodically)

```json
{
  "reliapi": {
    "id": "reliapi",
    "name": "ReliAPI",
    "status": "active",
    "pricing": {
      "per_request": 0.001
    },
    "endpoints": ["/proxy/llm", "/proxy/http"]
  }
}
```

## Redis Commands Reference

### User Operations

```redis
# Create user
HSET user:123456789 
  user_id 123456789
  telegram_username "@john"
  api_key "kikuai_abc123"
  balance_usd "0.00"
  status "active"
  created_at "2025-12-04T15:30:00Z"

# Get user
HGETALL user:123456789

# Update balance
HINCRBYFLOAT user:123456789 balance_usd 10.00

# Check if user exists
EXISTS user:123456789
```

### API Key Operations

```redis
# Create API key mapping
SET api_key:kikuai_abc123 '{"user_id":123456789,...}' EX -1

# Validate API key (O(1) lookup)
GET api_key:kikuai_abc123

# Delete API key
DEL api_key:kikuai_abc123
```

### Usage Tracking

```redis
# Increment usage counter
HINCRBY usage:123456789:2025-12 total_requests 1
HINCRBY usage:123456789:2025-12 reliapi_requests 1

# Get monthly usage
HGETALL usage:123456789:2025-12

# Set TTL on usage key (35 days)
EXPIRE usage:123456789:2025-12 3024000
```

### Rate Limiting

```redis
# Increment and check rate limit (atomic)
MULTI
INCR ratelimit:123456789:minute
EXPIRE ratelimit:123456789:minute 60
EXEC

# Using Lua script for atomic check:
local current = redis.call('GET', KEYS[1])
if current and tonumber(current) >= tonumber(ARGV[1]) then
  return 0
end
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 1
```

## Data Retention Policy

| Data Type | Retention | TTL Strategy |
|-----------|-----------|--------------|
| User accounts | Forever | No TTL |
| API keys | Forever | No TTL |
| Monthly usage | 2 years | 35 days auto, archive to PG |
| Daily usage | 90 days | Auto TTL |
| Transactions | Forever | Archive to PG after 1 year |
| Sessions | 24 hours | Auto TTL |
| Rate limits | Window-based | Auto TTL |
| Webhooks | 7 days | Auto TTL |

## Memory Estimation

| Entity | Size per record | Expected count | Total |
|--------|----------------|----------------|-------|
| Users | ~500 bytes | 10,000 | 5 MB |
| API keys | ~300 bytes | 15,000 | 4.5 MB |
| Usage (monthly) | ~200 bytes | 120,000 | 24 MB |
| Transactions | ~300 bytes | 500,000 | 150 MB |
| Rate limits | ~50 bytes | 50,000 | 2.5 MB |
| Other | - | - | ~50 MB |
| **Total** | - | - | **~250 MB** |

## High Availability Setup

### Redis Sentinel (Recommended)

```yaml
# docker-compose.yml
services:
  redis-master:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_master_data:/data

  redis-replica:
    image: redis:7-alpine
    command: redis-server --replicaof redis-master 6379
    depends_on:
      - redis-master

  sentinel:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/sentinel.conf
    depends_on:
      - redis-master
      - redis-replica
```

### Redis Cluster (For scale)

When data exceeds single node capacity:
- 3 master + 3 replica setup
- Hash slot distribution
- Automatic failover

## Backup Strategy

### RDB Snapshots

```redis
# redis.conf
save 900 1      # Save if 1 key changed in 900 sec
save 300 10     # Save if 10 keys changed in 300 sec
save 60 10000   # Save if 10000 keys changed in 60 sec

dbfilename dump.rdb
dir /data
```

### AOF (Append Only File)

```redis
# redis.conf
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
```

### Backup Script

```bash
#!/bin/bash
# backup_redis.sh

BACKUP_DIR="/backups/redis"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create RDB snapshot
docker exec redis redis-cli BGSAVE
sleep 5

# Copy backup
docker cp redis:/data/dump.rdb $BACKUP_DIR/dump_$TIMESTAMP.rdb

# Compress
gzip $BACKUP_DIR/dump_$TIMESTAMP.rdb

# Keep only last 7 days
find $BACKUP_DIR -name "dump_*.rdb.gz" -mtime +7 -delete
```

## Migration Strategy

### From Redis to PostgreSQL (If needed later)

```sql
-- PostgreSQL schema for long-term storage

CREATE TABLE users (
  id BIGINT PRIMARY KEY,  -- telegram_user_id
  telegram_username VARCHAR(255),
  api_key VARCHAR(64) UNIQUE,
  balance_usd DECIMAL(10, 2) DEFAULT 0,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE api_keys (
  key_hash VARCHAR(64) PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  name VARCHAR(255),
  permissions JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  last_used_at TIMESTAMP
);

CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id BIGINT REFERENCES users(id),
  type VARCHAR(20),
  amount_usd DECIMAL(10, 2),
  balance_before DECIMAL(10, 2),
  balance_after DECIMAL(10, 2),
  source VARCHAR(50),
  external_id VARCHAR(255),
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE usage_daily (
  user_id BIGINT REFERENCES users(id),
  date DATE,
  product VARCHAR(50),
  requests INT DEFAULT 0,
  tokens INT DEFAULT 0,
  PRIMARY KEY (user_id, date, product)
);

-- Indexes
CREATE INDEX idx_transactions_user ON transactions(user_id);
CREATE INDEX idx_transactions_created ON transactions(created_at);
CREATE INDEX idx_usage_date ON usage_daily(date);
```

## Error Handling

### Connection Failures

```python
import redis
from redis.exceptions import ConnectionError, TimeoutError

class RedisClient:
    def __init__(self, url: str, max_retries: int = 3):
        self.pool = redis.ConnectionPool.from_url(url)
        self.max_retries = max_retries
    
    def get_connection(self):
        return redis.Redis(connection_pool=self.pool)
    
    def execute_with_retry(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (ConnectionError, TimeoutError) as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
```

### Data Consistency

For critical operations (balance updates):

```python
async def update_balance_atomic(user_id: str, amount: float, transaction: dict):
    """Atomically update balance and record transaction."""
    lua_script = """
    local current = redis.call('HGET', KEYS[1], 'balance_usd')
    local new_balance = tonumber(current) + tonumber(ARGV[1])
    
    if new_balance < 0 then
        return {err = 'insufficient_balance'}
    end
    
    redis.call('HSET', KEYS[1], 'balance_usd', tostring(new_balance))
    redis.call('RPUSH', KEYS[2], ARGV[2])
    
    return new_balance
    """
    
    result = await redis.eval(
        lua_script, 
        2,  # number of keys
        f"user:{user_id}",
        f"transactions:{user_id}",
        str(amount),
        json.dumps(transaction)
    )
    
    return result
```

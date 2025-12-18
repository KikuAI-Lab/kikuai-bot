# Performance - @kikuai_bot

## Overview

Performance recommendations and optimization strategies for the KikuAI Bot platform.

## Performance Targets

| Metric | Target | Critical |
|--------|--------|----------|
| API latency (p50) | < 50ms | < 200ms |
| API latency (p99) | < 200ms | < 1000ms |
| Bot response time | < 500ms | < 2000ms |
| Redis latency | < 1ms | < 10ms |
| Throughput | 1000 rps | 100 rps |
| Memory usage | < 70% | < 90% |
| CPU usage | < 60% | < 80% |

## Redis Optimizations

### 1. Connection Pooling

```python
import redis.asyncio as redis

# Bad: New connection per request
async def bad_example():
    client = redis.from_url(REDIS_URL)
    result = await client.get("key")
    await client.close()

# Good: Connection pool
pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=50,
    decode_responses=True
)
redis_client = redis.Redis(connection_pool=pool)

async def good_example():
    return await redis_client.get("key")
```

### 2. Pipelining

```python
# Bad: Multiple round trips
async def bad_get_user_data(user_id: int):
    balance = await redis.get(f"user:{user_id}:balance")
    usage = await redis.get(f"user:{user_id}:usage")
    settings = await redis.get(f"user:{user_id}:settings")
    return balance, usage, settings

# Good: Single round trip
async def good_get_user_data(user_id: int):
    pipe = redis_client.pipeline()
    pipe.get(f"user:{user_id}:balance")
    pipe.get(f"user:{user_id}:usage")
    pipe.get(f"user:{user_id}:settings")
    return await pipe.execute()

# Benchmark: 3x faster with pipelining
```

### 3. Data Structure Optimization

```python
# Bad: Multiple keys for related data
await redis.set(f"user:{uid}:name", "John")
await redis.set(f"user:{uid}:balance", 10)
await redis.set(f"user:{uid}:status", "active")

# Good: Hash for structured data
await redis.hset(f"user:{uid}", mapping={
    "name": "John",
    "balance": "10",
    "status": "active"
})

# Get all fields at once
user = await redis.hgetall(f"user:{uid}")
```

### 4. Avoid Large Keys

```python
# Bad: Store all transactions in one key
await redis.lpush(f"transactions:{uid}", json.dumps(huge_list))

# Good: Pagination with sorted sets
await redis.zadd(
    f"transactions:{uid}",
    {json.dumps(txn): txn["timestamp"]}
)

# Get recent 10
recent = await redis.zrevrange(f"transactions:{uid}", 0, 9)
```

### 5. Use SCAN Instead of KEYS

```python
# Bad: Blocks Redis
keys = await redis.keys("user:*:balance")

# Good: Non-blocking iteration
async def scan_keys(pattern):
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        for key in keys:
            yield key
        if cursor == 0:
            break
```

## Caching Strategy

### Multi-Level Cache

```
Request → L1 (memory, 100ms) → L2 (Redis, 5min) → Source
```

```python
from functools import lru_cache
from cachetools import TTLCache
import asyncio

# L1: In-memory cache (per process)
l1_cache = TTLCache(maxsize=1000, ttl=0.1)

class MultiLevelCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.l1 = l1_cache
    
    async def get(self, key: str, fetch_func, l2_ttl: int = 300):
        """Get with multi-level caching."""
        
        # L1: Memory (instant)
        if key in self.l1:
            return self.l1[key]
        
        # L2: Redis (fast)
        cached = await self.redis.get(f"cache:{key}")
        if cached:
            value = json.loads(cached)
            self.l1[key] = value
            return value
        
        # Source: Fetch and cache
        value = await fetch_func()
        
        # Store in both levels
        self.l1[key] = value
        await self.redis.setex(f"cache:{key}", l2_ttl, json.dumps(value))
        
        return value

# Usage
cache = MultiLevelCache(redis_client)

async def get_product_info(product_id: str):
    return await cache.get(
        f"product:{product_id}",
        fetch_func=lambda: fetch_from_db(product_id),
        l2_ttl=3600
    )
```

### Cache Invalidation

```python
class CacheInvalidator:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def invalidate(self, pattern: str):
        """Invalidate cache keys matching pattern."""
        async for key in self.scan_keys(f"cache:{pattern}"):
            await self.redis.delete(key)
    
    async def invalidate_user(self, user_id: int):
        """Invalidate all cache for user."""
        await self.invalidate(f"user:{user_id}:*")
```

### What to Cache

| Data | Cache? | TTL | Reason |
|------|--------|-----|--------|
| User profile | Yes | 5 min | Frequently accessed |
| Product list | Yes | 1 hour | Rarely changes |
| Usage (current month) | Yes | 1 min | Near real-time |
| Balance | No | - | Must be real-time |
| API keys | No | - | Security critical |
| Rate limits | No | - | Must be real-time |

## Rate Limiting Optimization

### Sliding Window Algorithm

```python
import time

class SlidingWindowRateLimiter:
    """Efficient sliding window rate limiter."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check rate limit using sliding window.
        
        Returns: (allowed, remaining)
        """
        now = int(time.time() * 1000)  # Milliseconds
        window_start = now - (window_seconds * 1000)
        
        # Use Lua script for atomicity
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        
        -- Remove old entries
        redis.call('ZREMRANGEBYSCORE', key, 0, window)
        
        -- Count current entries
        local count = redis.call('ZCARD', key)
        
        if count < limit then
            -- Add current request
            redis.call('ZADD', key, now, now .. ':' .. math.random())
            redis.call('EXPIRE', key, ARGV[4])
            return {1, limit - count - 1}
        else
            return {0, 0}
        end
        """
        
        result = await self.redis.eval(
            lua_script,
            1,
            f"ratelimit:{key}",
            now,
            window_start,
            limit,
            window_seconds
        )
        
        return bool(result[0]), result[1]
```

### Rate Limit Caching

```python
# Cache rate limit decisions for very short period
class CachedRateLimiter:
    def __init__(self, limiter, cache_ms: int = 10):
        self.limiter = limiter
        self.cache_ms = cache_ms
        self.cache = {}
    
    async def is_allowed(self, key: str, limit: int, window: int):
        now = time.time() * 1000
        cache_key = f"{key}:{limit}:{window}"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if now - cached_time < self.cache_ms:
                return result
        
        # Get fresh result
        result = await self.limiter.is_allowed(key, limit, window)
        self.cache[cache_key] = (now, result)
        
        return result
```

## API Performance

### Async All The Way

```python
# Bad: Blocking call in async context
@router.get("/slow")
async def slow_endpoint():
    result = requests.get("https://api.example.com")  # Blocks!
    return result.json()

# Good: Fully async
import httpx

@router.get("/fast")
async def fast_endpoint():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
    return response.json()
```

### Response Streaming

```python
from fastapi.responses import StreamingResponse

@router.get("/large_data")
async def stream_large_data():
    async def generate():
        async for chunk in get_large_dataset():
            yield json.dumps(chunk) + "\n"
    
    return StreamingResponse(generate(), media_type="application/x-ndjson")
```

### Gzip Compression

```python
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### Lazy Loading

```python
@router.get("/usage")
async def get_usage(
    include_details: bool = False  # Default: fast response
):
    usage = await get_usage_summary(user_id)
    
    if include_details:
        usage["daily"] = await get_daily_breakdown(user_id)
    
    return usage
```

## Bot Performance

### Webhook Over Polling

```python
# Webhook: Best for production
async def setup_webhook():
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True
    )

# Process in parallel
@router.post("/webhook")
async def handle_webhook(update: dict):
    # Don't await long operations
    asyncio.create_task(process_update(update))
    return {"ok": True}  # Return immediately
```

### Background Tasks

```python
from fastapi import BackgroundTasks

@router.post("/payment/topup")
async def create_topup(
    request: Request,
    background_tasks: BackgroundTasks
):
    # Create checkout synchronously
    checkout = await create_checkout(request)
    
    # Send notification in background
    background_tasks.add_task(
        notify_user,
        user_id=request.user_id,
        message="Payment initiated"
    )
    
    return checkout
```

### Message Batching

```python
class MessageBatcher:
    """Batch multiple messages to reduce API calls."""
    
    def __init__(self, bot, max_batch: int = 10, delay_ms: int = 100):
        self.bot = bot
        self.max_batch = max_batch
        self.delay_ms = delay_ms
        self.queue = asyncio.Queue()
        self._started = False
    
    async def send(self, chat_id: int, text: str):
        await self.queue.put((chat_id, text))
        
        if not self._started:
            self._started = True
            asyncio.create_task(self._worker())
    
    async def _worker(self):
        while True:
            batch = []
            try:
                while len(batch) < self.max_batch:
                    item = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=self.delay_ms / 1000
                    )
                    batch.append(item)
            except asyncio.TimeoutError:
                pass
            
            if batch:
                await self._send_batch(batch)
    
    async def _send_batch(self, batch):
        tasks = [
            self.bot.send_message(chat_id, text)
            for chat_id, text in batch
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
```

## Web Apps Optimization

### Static Asset Caching

```nginx
# nginx.conf
location /webapp/ {
    root /var/www;
    expires 1d;
    add_header Cache-Control "public, immutable";
}

location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

### Minification

```javascript
// Build script
import { minify } from 'terser';

const minified = await minify(code, {
    compress: true,
    mangle: true
});
```

### Lazy Loading

```html
<!-- Load heavy charts only when needed -->
<script type="module">
  if (document.querySelector('#chart-container')) {
    const { Chart } = await import('./chart.js');
    new Chart('chart-container', data);
  }
</script>
```

## Benchmarking

### Load Testing Script

```python
# locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(0.1, 0.5)
    
    def on_start(self):
        self.api_key = "test_key"
    
    @task(10)
    def get_balance(self):
        self.client.get(
            "/api/v1/balance",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    @task(5)
    def get_usage(self):
        self.client.get(
            "/api/v1/usage",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    @task(1)
    def proxy_request(self):
        self.client.post(
            "/api/v1/proxy/llm",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"provider": "openai", "model": "gpt-3.5-turbo"}
        )
```

```bash
# Run load test
locust -f locustfile.py --headless -u 100 -r 10 -t 5m \
    --host https://bot.kikuai.dev
```

### Redis Benchmark

```bash
# Built-in benchmark
redis-benchmark -h localhost -p 6379 -c 50 -n 100000 -q

# Custom benchmark
redis-benchmark -t get,set,lpush,lpop,sadd,hset -q
```

### API Benchmark

```bash
# Using wrk
wrk -t12 -c400 -d30s \
    -H "Authorization: Bearer test_key" \
    https://bot.kikuai.dev/api/v1/balance

# Using hey
hey -n 10000 -c 100 \
    -H "Authorization: Bearer test_key" \
    https://bot.kikuai.dev/api/v1/balance
```

## Monitoring

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# System metrics
REDIS_CONNECTIONS = Gauge(
    'redis_pool_connections',
    'Redis connection pool size',
    ['type']
)

CACHE_HIT_RATE = Counter(
    'cache_hits_total',
    'Cache hit count',
    ['level', 'result']
)

# Middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_LATENCY.labels(
        endpoint=request.url.path
    ).observe(duration)
    
    return response
```

### Grafana Dashboards

Key panels:
- Request rate (rps)
- Latency percentiles (p50, p95, p99)
- Error rate
- Redis operations
- Cache hit rate
- Memory usage
- CPU usage

### Alerting Rules

```yaml
# prometheus/alerts.yml
groups:
  - name: performance
    rules:
      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency (p99 > 1s)"
      
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error rate > 1%"
      
      - alert: RedisLatency
        expr: redis_command_duration_seconds_p99 > 0.01
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Redis latency > 10ms"
```

## Performance Checklist

### Before Launch
- [ ] Connection pooling configured
- [ ] Redis pipelining used for batch operations
- [ ] Caching strategy implemented
- [ ] Compression enabled
- [ ] Async throughout
- [ ] Load testing passed

### Regular Reviews
- [ ] Weekly: Check latency metrics
- [ ] Monthly: Review cache hit rates
- [ ] Quarterly: Load testing
- [ ] On scaling: Re-benchmark

## Summary

1. **Use connection pools** - Never create connections per request
2. **Pipeline Redis operations** - Reduce round trips
3. **Cache aggressively** - Most reads are cacheable
4. **Async everywhere** - Never block the event loop
5. **Monitor constantly** - Know before users complain

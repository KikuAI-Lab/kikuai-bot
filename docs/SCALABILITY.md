# Scalability - @kikuai_bot

## Overview

This document outlines strategies for scaling the KikuAI Bot platform as user base and traffic grow.

## Current Baseline

**Expected initial load:**
- Users: 1,000 - 10,000
- API requests: 100K - 1M/month
- Concurrent users: 10 - 100

**Single server capacity:**
- Server: Hetzner 37.27.38.186
- CPU: 4 cores
- RAM: 8GB
- Storage: 160GB SSD

## Scaling Stages

### Stage 1: Vertical Scaling (0-10K users)

**What:** Increase resources on single server

```
┌─────────────────────────────────────────────────────────────────┐
│                    Single Server Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │   Bot    │  │   API    │  │  Redis   │  │  Nginx   │        │
│  │ (1 proc) │  │(4 workers)│  │(1 inst) │  │          │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Optimizations:**
1. Increase Uvicorn workers (1 per CPU core)
2. Enable Redis persistence
3. Add Nginx caching
4. Optimize database queries

```yaml
# docker-compose.yml
services:
  api:
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
    deploy:
      resources:
        limits:
          memory: 2G
```

### Stage 2: Service Separation (10K-50K users)

**What:** Separate services onto different containers/servers

```
┌─────────────────────────────────────────────────────────────────┐
│                    Server 1 (Application)                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │   Bot    │  │   API    │  │  Nginx   │                       │
│  │ (async)  │  │(8 workers)│  │          │                       │
│  └──────────┘  └──────────┘  └──────────┘                       │
└─────────────────────────────────────────────────────────────────┘
              │                     │
              ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Server 2 (Data)                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────┐  ┌────────────────────────┐          │
│  │    Redis Master       │  │     PostgreSQL         │          │
│  │    (persistence)      │  │     (analytics)        │          │
│  └───────────────────────┘  └────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- Database on dedicated resources
- Better resource isolation
- Easier maintenance

### Stage 3: Horizontal Scaling (50K-500K users)

**What:** Multiple API instances behind load balancer

```
                         ┌──────────────┐
                         │ Load Balancer│
                         │   (Nginx)    │
                         └───────┬──────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌────────────────┐      ┌────────────────┐      ┌────────────────┐
│   API Node 1   │      │   API Node 2   │      │   API Node 3   │
│   (8 workers)  │      │   (8 workers)  │      │   (8 workers)  │
└────────────────┘      └────────────────┘      └────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                         ┌───────┴───────┐
                         │               │
                         ▼               ▼
               ┌──────────────┐  ┌──────────────┐
               │Redis Primary │  │Redis Replica │
               └──────────────┘  └──────────────┘
```

**Implementation:**

```yaml
# docker-compose.scale.yml
services:
  api:
    image: kikuai-api:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 2G
    environment:
      - REDIS_URL=redis://redis-primary:6379
    networks:
      - internal

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.lb.conf:/etc/nginx/nginx.conf
    networks:
      - internal
      - public
```

```nginx
# nginx.lb.conf
upstream api_backend {
    least_conn;  # Load balancing algorithm
    server api1:8000 weight=1;
    server api2:8000 weight=1;
    server api3:8000 weight=1;
    
    keepalive 32;  # Connection pooling
}

server {
    location /api/ {
        proxy_pass http://api_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

### Stage 4: Distributed System (500K+ users)

**What:** Full microservices with Redis Cluster

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CDN (Cloudflare)                                │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Load Balancer (HAProxy)                           │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│   API Cluster     │        │   Bot Cluster     │        │  Webhook Handlers │
│   (10 nodes)      │        │   (3 nodes)       │        │   (3 nodes)       │
└─────────┬─────────┘        └─────────┬─────────┘        └─────────┬─────────┘
          │                            │                            │
          └────────────────────────────┼────────────────────────────┘
                                       │
                                       ▼
          ┌────────────────────────────────────────────────────────┐
          │                    Redis Cluster                        │
          │  ┌────────┐  ┌────────┐  ┌────────┐                    │
          │  │Master 1│  │Master 2│  │Master 3│                    │
          │  │Replica │  │Replica │  │Replica │                    │
          │  └────────┘  └────────┘  └────────┘                    │
          └────────────────────────────────────────────────────────┘
                                       │
                                       ▼
          ┌────────────────────────────────────────────────────────┐
          │               PostgreSQL (Citus Cluster)               │
          │  ┌────────┐  ┌────────┐  ┌────────┐                    │
          │  │Shard 1 │  │Shard 2 │  │Shard 3 │                    │
          │  └────────┘  └────────┘  └────────┘                    │
          └────────────────────────────────────────────────────────┘
```

## Redis Scaling

### Redis Sentinel (High Availability)

```yaml
# docker-compose.sentinel.yml
version: '3.8'

services:
  redis-master:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_master:/data
    networks:
      - redis_net

  redis-replica-1:
    image: redis:7-alpine
    command: redis-server --replicaof redis-master 6379
    networks:
      - redis_net

  redis-replica-2:
    image: redis:7-alpine
    command: redis-server --replicaof redis-master 6379
    networks:
      - redis_net

  sentinel-1:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/sentinel.conf:ro
    networks:
      - redis_net

  sentinel-2:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/sentinel.conf:ro
    networks:
      - redis_net

  sentinel-3:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/sentinel.conf:ro
    networks:
      - redis_net

volumes:
  redis_master:

networks:
  redis_net:
```

```conf
# sentinel.conf
sentinel monitor mymaster redis-master 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

### Redis Cluster (Sharding)

For very large datasets:

```bash
# Create 6-node cluster (3 masters + 3 replicas)
redis-cli --cluster create \
  redis1:6379 redis2:6379 redis3:6379 \
  redis4:6379 redis5:6379 redis6:6379 \
  --cluster-replicas 1
```

**Python client for cluster:**
```python
from redis.cluster import RedisCluster

rc = RedisCluster(
    host="redis1",
    port=6379,
    decode_responses=True
)

# Keys are automatically routed to correct shard
rc.set("user:123", json.dumps(user_data))
```

## Caching Strategy

### Multi-Level Cache

```
┌─────────────────────────────────────────────────────────────────┐
│                         L1: Memory Cache                         │
│               (per-process, 100ms TTL, 1000 items)              │
├─────────────────────────────────────────────────────────────────┤
│                         L2: Redis Cache                          │
│                  (shared, 5min TTL, unlimited)                   │
├─────────────────────────────────────────────────────────────────┤
│                         L3: Database                             │
│                        (Redis/PostgreSQL)                        │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
import functools
from cachetools import TTLCache

# L1: In-memory cache (per process)
memory_cache = TTLCache(maxsize=1000, ttl=0.1)  # 100ms

class CacheManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.memory = memory_cache
    
    async def get(self, key: str):
        # L1: Memory
        if key in self.memory:
            return self.memory[key]
        
        # L2: Redis
        value = await self.redis.get(f"cache:{key}")
        if value:
            result = json.loads(value)
            self.memory[key] = result
            return result
        
        return None
    
    async def set(self, key: str, value: any, ttl: int = 300):
        # Store in both levels
        self.memory[key] = value
        await self.redis.setex(f"cache:{key}", ttl, json.dumps(value))
    
    def cache(self, ttl: int = 300):
        """Decorator for caching function results."""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                cache_key = f"{func.__name__}:{hash((args, tuple(kwargs.items())))}"
                
                cached = await self.get(cache_key)
                if cached is not None:
                    return cached
                
                result = await func(*args, **kwargs)
                await self.set(cache_key, result, ttl)
                return result
            return wrapper
        return decorator

# Usage
cache = CacheManager(redis_client)

@cache.cache(ttl=60)
async def get_user(user_id: int):
    return await fetch_user_from_db(user_id)
```

### What to Cache

| Data | TTL | Reason |
|------|-----|--------|
| User profile | 5 min | Frequent access |
| Product list | 1 hour | Rarely changes |
| Usage stats (current) | 1 min | Near real-time |
| Rate limit counters | 0 | Must be real-time |
| Balance | 0 | Must be real-time |

## Database Scaling

### Read Replicas

```python
# Connection pool with read/write split
class DatabasePool:
    def __init__(self):
        self.write_pool = redis.from_url(REDIS_MASTER_URL)
        self.read_pool = redis.from_url(REDIS_REPLICA_URL)
    
    def get_connection(self, write: bool = False):
        return self.write_pool if write else self.read_pool

# Usage
async def get_user(user_id: int):
    conn = db_pool.get_connection(write=False)  # Use replica
    return await conn.hgetall(f"user:{user_id}")

async def update_balance(user_id: int, amount: float):
    conn = db_pool.get_connection(write=True)  # Use master
    return await conn.hincrbyfloat(f"user:{user_id}", "balance_usd", amount)
```

### Connection Pooling

```python
# aioredis with connection pool
import aioredis

redis_pool = aioredis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=100,
    decode_responses=True
)

redis_client = aioredis.Redis(connection_pool=redis_pool)
```

## Load Balancing

### Algorithm Choice

| Algorithm | Use Case |
|-----------|----------|
| Round Robin | Default, equal servers |
| Least Connections | Variable request duration |
| IP Hash | Session stickiness needed |
| Weighted | Mixed server capacity |

### Health Checks

```nginx
upstream api {
    server api1:8000 weight=5;
    server api2:8000 weight=3;
    server api3:8000 weight=2;
    
    # Health check
    server api1:8000 max_fails=3 fail_timeout=30s;
}
```

### Graceful Degradation

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def call_external_api(url: str):
    """Call external API with circuit breaker."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

## Queue-Based Processing

### Background Jobs

```python
# Using Redis as job queue
import asyncio
from dataclasses import dataclass

@dataclass
class Job:
    job_id: str
    job_type: str
    data: dict
    created_at: datetime

class JobQueue:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.queue_name = "jobs:pending"
    
    async def enqueue(self, job_type: str, data: dict):
        job = Job(
            job_id=secrets.token_hex(8),
            job_type=job_type,
            data=data,
            created_at=datetime.utcnow()
        )
        await self.redis.rpush(self.queue_name, json.dumps(asdict(job)))
        return job.job_id
    
    async def dequeue(self) -> Optional[Job]:
        result = await self.redis.blpop(self.queue_name, timeout=5)
        if result:
            return Job(**json.loads(result[1]))
        return None

# Worker process
async def worker():
    queue = JobQueue(redis_client)
    while True:
        job = await queue.dequeue()
        if job:
            await process_job(job)

# Usage
await job_queue.enqueue("send_notification", {
    "user_id": 123,
    "message": "Low balance alert"
})
```

### Event-Driven Architecture

```python
# Pub/Sub for real-time events
class EventBus:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.pubsub = None
    
    async def publish(self, channel: str, event: dict):
        await self.redis.publish(channel, json.dumps(event))
    
    async def subscribe(self, channel: str, handler):
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(channel)
        
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                event = json.loads(message["data"])
                await handler(event)

# Usage
async def on_payment_received(event):
    user_id = event["user_id"]
    amount = event["amount"]
    await send_telegram_notification(user_id, f"Payment of ${amount} received!")

# Start subscriber
asyncio.create_task(event_bus.subscribe("payments", on_payment_received))

# Publish from webhook handler
await event_bus.publish("payments", {
    "user_id": 123,
    "amount": 10.00,
    "method": "paddle"
})
```

## Performance Benchmarks

### Target Metrics

| Metric | Target | Current |
|--------|--------|---------|
| API latency (p50) | < 50ms | TBD |
| API latency (p99) | < 200ms | TBD |
| Throughput | 1000 rps | TBD |
| Redis latency | < 1ms | TBD |
| Uptime | 99.9% | TBD |

### Load Testing

```bash
# Using wrk for benchmarking
wrk -t12 -c400 -d30s \
  -H "Authorization: Bearer kikuai_test..." \
  https://bot.kikuai.dev/api/v1/balance

# Using locust for realistic load
locust -f loadtest.py --headless -u 100 -r 10 -t 5m
```

```python
# loadtest.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        self.api_key = "kikuai_test..."
    
    @task(10)
    def get_balance(self):
        self.client.get("/api/v1/balance",
            headers={"Authorization": f"Bearer {self.api_key}"})
    
    @task(5)
    def get_usage(self):
        self.client.get("/api/v1/usage",
            headers={"Authorization": f"Bearer {self.api_key}"})
    
    @task(1)
    def proxy_request(self):
        self.client.post("/api/v1/proxy/llm",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"provider": "openai", "model": "gpt-3.5-turbo"})
```

## Cost Estimation

### Hetzner Servers

| Stage | Server | Cost/month |
|-------|--------|------------|
| 1 | CX31 (4 CPU, 8GB) | €8 |
| 2 | CX41 (8 CPU, 16GB) | €17 |
| 3 | 3x CX31 + CX21 (DB) | €31 |
| 4 | Custom cluster | ~€100 |

### Break-Even Analysis

With pay-as-you-go at $0.001 per request:
- 1M requests/month = $1,000 revenue
- Server cost at Stage 2 = ~$20
- Profit margin = 98%

## Monitoring for Scale

### Key Metrics to Watch

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
request_count = Counter('api_requests_total', 
    'Total API requests', ['endpoint', 'status'])

request_latency = Histogram('api_request_duration_seconds',
    'Request latency', ['endpoint'])

# System metrics
active_connections = Gauge('active_connections',
    'Active connections')

redis_connections = Gauge('redis_pool_connections',
    'Redis pool connections', ['type'])
```

### Scaling Triggers

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU usage | > 70% for 5min | Scale up |
| Memory usage | > 80% | Scale up |
| Request latency p99 | > 500ms | Investigate |
| Error rate | > 1% | Alert |
| Redis memory | > 70% | Add node |

## Summary

1. **Start simple** - Single server handles initial load
2. **Monitor first** - Know your bottlenecks before optimizing
3. **Cache aggressively** - Most data can be cached
4. **Scale horizontally** - Add nodes, not bigger servers
5. **Queue long tasks** - Don't block API requests
6. **Plan for failure** - Replicas and circuit breakers

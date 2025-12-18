"""Usage tracking service."""

import json
from datetime import datetime
from typing import Dict, Any
import redis

from config.settings import REDIS_URL

redis_client = redis.from_url(REDIS_URL)


class UsageTracker:
    """Service for tracking API usage."""
    
    def track_request(
        self,
        user_id: int,
        endpoint: str,
        cost_usd: float = 0.0,
    ):
        """Track a single API request."""
        month = datetime.now().strftime("%Y-%m")
        
        # Increment request count
        usage_key = f"usage:{user_id}:{month}"
        redis_client.incr(usage_key)
        
        # Track cost
        if cost_usd > 0:
            cost_key = f"cost:{user_id}:{month}"
            redis_client.incrbyfloat(cost_key, cost_usd)
        
        # Track by endpoint
        endpoint_key = f"usage:{user_id}:{month}:{endpoint}"
        redis_client.incr(endpoint_key)
    
    def get_usage(self, user_id: int, month: str = None) -> Dict[str, Any]:
        """Get usage statistics for a user."""
        if not month:
            month = datetime.now().strftime("%Y-%m")
        
        usage_key = f"usage:{user_id}:{month}"
        cost_key = f"cost:{user_id}:{month}"
        
        requests = int(redis_client.get(usage_key) or 0)
        cost = float(redis_client.get(cost_key) or 0)
        
        return {
            "user_id": user_id,
            "month": month,
            "requests": requests,
            "cost_usd": cost,
        }
    
    def get_endpoint_usage(self, user_id: int, month: str = None) -> Dict[str, int]:
        """Get usage by endpoint."""
        if not month:
            month = datetime.now().strftime("%Y-%m")
        
        # Get all endpoint keys
        pattern = f"usage:{user_id}:{month}:*"
        keys = redis_client.keys(pattern)
        
        endpoint_usage = {}
        for key in keys:
            endpoint = key.decode().split(":")[-1]
            count = int(redis_client.get(key) or 0)
            endpoint_usage[endpoint] = count
        
        return endpoint_usage


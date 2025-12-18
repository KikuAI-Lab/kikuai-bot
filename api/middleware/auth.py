"""Authentication middleware."""

import json
from typing import Optional
from fastapi import HTTPException, Header
import redis

from config.settings import REDIS_URL

redis_client = redis.from_url(REDIS_URL)


async def get_user_id_from_api_key(api_key: str) -> Optional[int]:
    """Get user_id from API key."""
    if not api_key:
        return None
    
    api_key_key = f"api_key:{api_key}"
    key_data = redis_client.get(api_key_key)
    if not key_data:
        return None
    
    try:
        data = json.loads(key_data)
        return data.get("user_id")
    except:
        return None


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> int:
    """Verify API key and return user_id."""
    user_id = await get_user_id_from_api_key(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user_id


async def get_user(user_id: int) -> Optional[dict]:
    """Get user data from Redis."""
    user_key = f"user:{user_id}"
    user_data = redis_client.get(user_key)
    if not user_data:
        return None
    
    try:
        return json.loads(user_data)
    except:
        return None


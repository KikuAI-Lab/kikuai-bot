"""Balance and usage endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import json
import redis
from datetime import datetime

from api.middleware.auth import verify_api_key, get_user
from config.settings import REDIS_URL

router = APIRouter(prefix="/api/v1", tags=["balance"])
redis_client = redis.from_url(REDIS_URL)


class BalanceResponse(BaseModel):
    """Balance response model."""
    balance_usd: float
    currency: str = "USD"


class UsageResponse(BaseModel):
    """Usage response model."""
    month: str
    requests: int
    cost_usd: float
    endpoint_usage: dict = {}


def get_usage_from_redis(user_id: int, month: str = None) -> dict:
    """Get usage statistics from Redis."""
    if not month:
        month = datetime.now().strftime("%Y-%m")
    
    usage_key = f"usage:{user_id}:{month}"
    cost_key = f"cost:{user_id}:{month}"
    
    requests = int(redis_client.get(usage_key) or 0)
    cost = float(redis_client.get(cost_key) or 0)
    
    # Get endpoint usage
    pattern = f"usage:{user_id}:{month}:*"
    endpoint_keys = redis_client.keys(pattern)
    
    endpoint_usage = {}
    for key in endpoint_keys:
        endpoint = key.decode().split(":")[-1]
        count = int(redis_client.get(key) or 0)
        endpoint_usage[endpoint] = count
    
    return {
        "month": month,
        "requests": requests,
        "cost_usd": cost,
        "endpoint_usage": endpoint_usage,
    }


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(x_api_key: str = Header(..., alias="X-API-Key")):
    """Get current balance."""
    user_id = await verify_api_key(x_api_key)
    user = await get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    balance = user.get("balance_usd", 0.0)
    
    return BalanceResponse(balance_usd=balance)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    month: Optional[str] = None,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Get usage statistics."""
    user_id = await verify_api_key(x_api_key)
    usage = get_usage_from_redis(user_id, month)
    
    return UsageResponse(**usage)


@router.get("/history")
async def get_history(
    limit: int = 10,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Get transaction history."""
    user_id = await verify_api_key(x_api_key)
    
    # TODO: Implement transaction history
    # For now, return empty list
    return {
        "transactions": [],
        "total": 0,
    }


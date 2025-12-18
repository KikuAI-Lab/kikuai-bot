"""Web App endpoints for Telegram Web Apps."""

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
import json
import redis
import hmac
import hashlib
import urllib.parse
from datetime import datetime

from config.settings import REDIS_URL, TELEGRAM_BOT_TOKEN

router = APIRouter(prefix="/api/v1/webapp", tags=["webapp"])
redis_client = redis.from_url(REDIS_URL)


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Verify Telegram Web App initData and extract user info.
    
    Returns user_id if valid, raises HTTPException if invalid.
    """
    try:
        # Parse init_data
        params = dict(urllib.parse.parse_qsl(init_data))
        
        # Get hash
        received_hash = params.pop('hash', None)
        if not received_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing hash in initData"
            )
        
        # Create data check string
        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(params.items())
        )
        
        # Calculate secret key
        secret_key = hmac.new(
            "WebAppData".encode(),
            TELEGRAM_BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Calculate expected hash
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Verify hash
        if not hmac.compare_digest(expected_hash, received_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData hash"
            )
        
        # Parse user data
        user_str = params.get('user', '{}')
        user_data = json.loads(user_str)
        
        return user_data
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid initData format: {str(e)}"
        )


class DashboardResponse(BaseModel):
    """Dashboard data response."""
    balance_usd: float
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


@router.get("/dashboard")
async def get_dashboard(request: Request):
    """
    Get dashboard data for Telegram Web App.
    
    Uses Telegram initData for authentication.
    """
    # Get initData from query parameter or header
    init_data = request.query_params.get("_auth") or request.headers.get("X-Telegram-Init-Data")
    
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Telegram initData"
        )
    
    # Verify and get user
    user_data = verify_telegram_init_data(init_data)
    user_id = user_data.get("id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user data"
        )
    
    # Get user from Redis
    user_key = f"user:{user_id}"
    user_data_redis = redis_client.get(user_key)
    
    if not user_data_redis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user = json.loads(user_data_redis)
    balance = user.get("balance_usd", 0.0)
    usage = get_usage_from_redis(user_id)
    
    return DashboardResponse(
        balance_usd=balance,
        **usage
    )











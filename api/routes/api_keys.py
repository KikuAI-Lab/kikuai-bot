"""API key management endpoints."""

import json
import secrets
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import redis

from config.settings import REDIS_URL

router = APIRouter(prefix="/api/v1/api_keys", tags=["api_keys"])
redis_client = redis.from_url(REDIS_URL)


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"kikuai_{secrets.token_urlsafe(32)}"


class APIKeyResponse(BaseModel):
    """API key response model."""
    key: str
    created_at: str


class APIKeyListResponse(BaseModel):
    """API keys list response model."""
    keys: List[APIKeyResponse]


async def get_user_id_from_api_key(api_key: str) -> Optional[int]:
    """Get user_id from API key."""
    api_key_key = f"api_key:{api_key}"
    key_data = redis_client.get(api_key_key)
    if not key_data:
        return None
    data = json.loads(key_data)
    return data.get("user_id")


async def get_user(user_id: int) -> Optional[dict]:
    """Get user data from Redis."""
    user_key = f"user:{user_id}"
    user_data = redis_client.get(user_key)
    if not user_data:
        return None
    return json.loads(user_data)


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(x_api_key: str = Header(..., alias="X-API-Key")):
    """List all API keys for the authenticated user."""
    user_id = await get_user_id_from_api_key(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # For now, return single key (we can extend to multiple keys later)
    return APIKeyListResponse(
        keys=[
            APIKeyResponse(
                key=user.get("api_key"),
                created_at=user.get("created_at", datetime.now().isoformat()),
            )
        ]
    )


@router.post("", response_model=APIKeyResponse)
async def create_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Create a new API key."""
    user_id = await get_user_id_from_api_key(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate new key
    new_key = generate_api_key()
    
    # Update user
    old_key = user.get("api_key")
    user["api_key"] = new_key
    user_key = f"user:{user_id}"
    redis_client.set(user_key, json.dumps(user))
    
    # Remove old API key mapping
    if old_key:
        old_api_key_key = f"api_key:{old_key}"
        redis_client.delete(old_api_key_key)
    
    # Save new API key mapping
    api_key_key = f"api_key:{new_key}"
    redis_client.set(api_key_key, json.dumps({
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
    }))
    
    return APIKeyResponse(
        key=new_key,
        created_at=datetime.now().isoformat(),
    )


@router.delete("/{key_id}")
async def delete_api_key(key_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
    """Delete an API key."""
    user_id = await get_user_id_from_api_key(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # For now, we only support single key per user
    # This endpoint is for future multi-key support
    return {"message": "Key deletion not yet supported"}


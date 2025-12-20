from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.base import get_db, Account, APIKey
from api.services.account_service import AccountService

router = APIRouter(prefix="/api/v1/api_keys", tags=["api_keys"])

class APIKeyResponse(BaseModel):
    id: str
    prefix: str
    label: str
    scopes: List[str]
    is_active: bool
    created_at: str
    last_used_at: Optional[str]

class APIKeyCreateResponse(BaseModel):
    id: str
    raw_key: str # Full kikuai_pref_secret
    prefix: str
    label: str

from api.middleware.auth import get_current_account

@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """List all API keys for the authenticated account."""
    stmt = select(APIKey).where(APIKey.account_id == account.id)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    return [
        APIKeyResponse(
            id=str(k.id),
            prefix=k.key_prefix,
            label=k.label or "default",
            scopes=k.scopes,
            is_active=k.is_active,
            created_at=k.created_at.isoformat(),
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None
        )
        for k in keys
    ]

@router.post("", response_model=APIKeyCreateResponse)
async def create_api_key(
    label: str = "new_key",
    scopes: List[str] = None,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Create a new scoped secure API key."""
    account_service = AccountService(db)
    raw_key = await account_service.create_api_key(
        account_id=account.id, 
        label=label, 
        scopes=scopes or [],
        actor_id=str(account.telegram_id)
    )
    
    # Extract prefix for response
    prefix = raw_key.split("_")[1]
    
    # Get the newly created object
    stmt = select(APIKey).where(APIKey.account_id == account.id, APIKey.key_prefix == prefix)
    res = await db.execute(stmt)
    key_obj = res.scalar_one()
    
    return APIKeyCreateResponse(
        id=str(key_obj.id),
        raw_key=raw_key,
        prefix=prefix,
        label=key_obj.label
    )

@router.delete("/{prefix}")
async def revoke_api_key(
    prefix: str,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Revoke a specific API key by its prefix."""
    account_service = AccountService(db)
    await account_service.revoke_key(
        account_id=account.id, 
        prefix=prefix,
        actor_id=str(account.telegram_id)
    )
    return {"status": "success", "message": f"Key with prefix {prefix} has been revoked."}

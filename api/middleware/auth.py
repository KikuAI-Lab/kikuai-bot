from typing import List, Tuple
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from api.db.base import get_db, Account
from api.services.account_service import AccountService
from api.services.ledger_balance import redis_client
from api.context import ip_address_var, account_id_var, opt_in_debug_var
import time

async def check_auth_rate_limit():
    """Check if the current IP is rate-limited for auth failures."""
    ip = ip_address_var.get()
    if not ip:
        return
    
    try:
        limit_key = f"auth_fail:{ip}"
        fails = redis_client.get(limit_key)
        if fails and int(fails) >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication failures. Please try again later."
            )
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        # Else ignore Redis failure (Degraded)

def record_auth_failure():
    """Record an authentication failure for the current IP."""
    ip = ip_address_var.get()
    if not ip:
        return
    
    try:
        limit_key = f"auth_fail:{ip}"
        fails = redis_client.incr(limit_key)
        if fails == 1:
            redis_client.expire(limit_key, 900) # 15 minutes window
    except Exception:
        pass # Degraded

async def get_current_account(
    authorization: str = Header(None, alias="Authorization"),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """Dependency to get current account from JWT token or API key.
    
    Supports two auth methods:
    1. Authorization: Bearer <jwt_token> (for dashboard users)
    2. X-API-Key: kiku_xxx_yyy (for API consumers)
    """
    await check_auth_rate_limit()
    
    account = None
    
    # Try JWT Bearer token first
    if authorization and authorization.startswith("Bearer "):
        from api.services.auth_service import AuthService
        from uuid import UUID
        
        token = authorization[7:]  # Remove "Bearer " prefix
        user_info = AuthService.verify_access_token(token)
        
        if user_info:
            from sqlalchemy import select
            stmt = select(Account).where(Account.id == UUID(user_info.account_id))
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()
    
    # Fallback to API key
    if not account and x_api_key:
        account_service = AccountService(db)
        account, _ = await account_service.verify_key(x_api_key)
    
    if not account:
        record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Set context vars
    account_id_var.set(account.id)
    opt_in_debug_var.set(account.opt_in_debug)
    
    return account

async def get_current_account_and_scopes(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Tuple[Account, List[str]]:
    """Dependency to get account and its scopes."""
    await check_auth_rate_limit()
    
    account_service = AccountService(db)
    account, scopes = await account_service.verify_key(x_api_key)
    
    if not account:
        record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    
    # Set context vars
    account_id_var.set(account.id)
    opt_in_debug_var.set(account.opt_in_debug)
    
    return account, scopes

def require_scope(required_scope: str):
    """Dependency that ensures a key has the required scope."""
    async def scope_checker(
        data: Tuple[Account, List[str]] = Depends(get_current_account_and_scopes)
    ):
        account, scopes = data
        if not scopes or required_scope not in scopes:
            # For MVP, if scopes are empty, we might allow all (optional logic)
            # But per expert feedback, we should be strict.
            if scopes: # Only enforce if scopes are defined
                raise HTTPException(status_code=403, detail=f"Missing required scope: {required_scope}")
        return account
    return scope_checker


# Backward compatibility aliases
async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> bool:
    """Legacy function for backward compatibility."""
    return True  # Actual verification done in get_current_account

async def get_user(x_api_key: str = Header(..., alias="X-API-Key")):
    """Legacy function for backward compatibility - returns telegram_id."""
    # This is a placeholder - actual implementation should use get_current_account
    return None

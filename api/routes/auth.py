"""Authentication API routes.

Endpoints:
- POST /api/v1/auth/magic-link - Request magic link email
- POST /api/v1/auth/verify - Verify magic link token
- POST /api/v1/auth/telegram - Login with Telegram
- POST /api/v1/auth/refresh - Refresh access token
- POST /api/v1/auth/logout - Logout (invalidate refresh token)
- GET /api/v1/auth/me - Get current user info
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Body, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.base import get_db, Account
from api.services.auth_service import AuthService, TokenPair, UserInfo

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    status: str
    message: str


class TelegramAuthRequest(BaseModel):
    """Telegram Login Widget auth data."""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccountResponse(BaseModel):
    id: str
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    balance_usd: str
    created_at: datetime


# Simple in-memory refresh token storage (replace with Redis/DB in production)
# Format: {token_hash: {"account_id": UUID, "expires_at": datetime}}
_refresh_tokens: dict = {}


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """Dependency to get current authenticated user."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:]  # Remove "Bearer " prefix
    user_info = AuthService.verify_access_token(token)
    
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    account = await AuthService.get_account_by_id(db, UUID(user_info.account_id))
    if not account:
        raise HTTPException(status_code=401, detail="Account not found")
    
    return account


@router.post("/magic-link", response_model=MagicLinkResponse)
async def request_magic_link(
    request: MagicLinkRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request a magic link for email-based login.
    
    If the email is registered, sends a magic link.
    For security, always returns success even if email not found.
    """
    account = await AuthService.get_account_by_email(db, request.email)
    
    if account:
        token = await AuthService.set_magic_link_token(db, account)
        
        # TODO: Send actual email via Resend
        # For now, log the link
        magic_link = f"https://kikuai.dev/auth/verify?token={token}"
        print(f"[AUTH] Magic link for {request.email}: {magic_link}")
    
    # Always return success (don't reveal if email exists)
    return MagicLinkResponse(
        status="success",
        message="If the email is registered, a magic link has been sent."
    )


@router.post("/verify", response_model=TokenPair)
async def verify_magic_link(
    token: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """Verify a magic link token and return JWT tokens."""
    account = await AuthService.verify_magic_link_token(db, token)
    
    if not account:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")
    
    # Create token pair
    token_pair, refresh_hash = AuthService.create_token_pair(account)
    
    # Store refresh token
    _refresh_tokens[refresh_hash] = {
        "account_id": account.id,
        "expires_at": datetime.utcnow() + timedelta(days=7)
    }
    
    return token_pair


@router.post("/telegram", response_model=TokenPair)
async def login_with_telegram(
    auth_data: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """Login with Telegram Login Widget.
    
    Validates the auth data from Telegram and returns JWT tokens.
    Creates account if not exists.
    """
    # Validate Telegram auth
    auth_dict = auth_data.model_dump()
    if not AuthService.validate_telegram_auth(auth_dict):
        raise HTTPException(status_code=401, detail="Invalid Telegram authentication")
    
    # Get or create account
    account = await AuthService.get_or_create_account_by_telegram(
        db,
        telegram_id=auth_data.id,
        username=auth_data.username,
        first_name=auth_data.first_name,
    )
    
    # Create token pair
    token_pair, refresh_hash = AuthService.create_token_pair(account)
    
    # Store refresh token
    _refresh_tokens[refresh_hash] = {
        "account_id": account.id,
        "expires_at": datetime.utcnow() + timedelta(days=7)
    }
    
    return token_pair


@router.post("/refresh", response_model=TokenPair)
async def refresh_access_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh an access token using a refresh token."""
    token_hash = AuthService.hash_refresh_token(request.refresh_token)
    
    token_data = _refresh_tokens.get(token_hash)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    if datetime.utcnow() > token_data["expires_at"]:
        del _refresh_tokens[token_hash]
        raise HTTPException(status_code=401, detail="Refresh token expired")
    
    # Get account
    account = await AuthService.get_account_by_id(db, token_data["account_id"])
    if not account:
        del _refresh_tokens[token_hash]
        raise HTTPException(status_code=401, detail="Account not found")
    
    # Rotate refresh token (delete old, create new)
    del _refresh_tokens[token_hash]
    
    # Create new token pair
    new_token_pair, new_refresh_hash = AuthService.create_token_pair(account)
    
    # Store new refresh token
    _refresh_tokens[new_refresh_hash] = {
        "account_id": account.id,
        "expires_at": datetime.utcnow() + timedelta(days=7)
    }
    
    return new_token_pair


@router.post("/logout")
async def logout(
    request: RefreshRequest,
):
    """Logout by invalidating the refresh token."""
    token_hash = AuthService.hash_refresh_token(request.refresh_token)
    
    if token_hash in _refresh_tokens:
        del _refresh_tokens[token_hash]
    
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/me", response_model=AccountResponse)
async def get_current_account(
    account: Account = Depends(get_current_user)
):
    """Get current authenticated user's account info."""
    return AccountResponse(
        id=str(account.id),
        telegram_id=account.telegram_id,
        email=account.email,
        balance_usd=str(account.balance_usd),
        created_at=account.created_at,
    )

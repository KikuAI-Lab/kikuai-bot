import hmac
import hashlib
import secrets
import json
from datetime import datetime
from typing import Optional, Tuple, List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.base import Account, APIKey, AuditLog
from api.services.ledger_balance import redis_client
from api.context import request_id_var, ip_address_var, user_agent_var
from config.settings import SERVER_SECRET

class AccountService:
    """Service for managing KikuAI accounts and API keys with B2B-grade security."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    def _hash_key(self, api_secret: str) -> str:
        """Hash API secret using HMAC-SHA256 with server secret."""
        return hmac.new(
            SERVER_SECRET.encode(),
            api_secret.encode(),
            hashlib.sha256
        ).hexdigest()

    async def record_audit(
        self, 
        account_id: UUID, 
        action: str, 
        actor_id: Optional[str] = None, 
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: dict = None
    ):
        """Record an administrative action with metadata. Auto-fills from context if missing."""
        log = AuditLog(
            account_id=account_id,
            action=action,
            actor_id=actor_id,
            request_id=request_id or request_id_var.get(),
            ip_address=ip_address or ip_address_var.get(),
            user_agent=user_agent or user_agent_var.get(),
            metadata_json=metadata
        )
        self.session.add(log)

    async def get_or_create_account(self, telegram_id: int) -> Account:
        """Get or create account by Telegram ID."""
        stmt = select(Account).where(Account.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()
        
        if not account:
            account = Account(telegram_id=telegram_id)
            self.session.add(account)
            await self.session.flush() # Get ID
            await self.record_audit(account.id, "ACCOUNT_CREATED", actor_id=str(telegram_id))
            await self.session.commit()
            await self.session.refresh(account)
            
        return account

    async def create_api_key(
        self, 
        account_id: UUID, 
        label: str = "default", 
        scopes: List[str] = None, 
        actor_id: str = None,
        request_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> str:
        """
        Create a new secure API key.
        Format: kikuai_{prefix}_{secret}
        Storage: prefix (clear, 12 chars), secret (HMAC-SHA256)
        """
        prefix = secrets.token_hex(6) # 12 chars hex
        secret = secrets.token_urlsafe(32)
        raw_key = f"kikuai_{prefix}_{secret}"
        key_hash = self._hash_key(secret)
        
        new_key = APIKey(
            account_id=account_id,
            key_prefix=prefix,
            key_hash=key_hash,
            label=label,
            scopes=scopes or []
        )
        self.session.add(new_key)
        
        await self.record_audit(
            account_id, 
            "KEY_CREATED", 
            actor_id=actor_id, 
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "label": label,
                "prefix": prefix,
                "scopes": scopes
            }
        )
        
        await self.session.commit()
        
        # Redis cache: Look up by prefix for speed
        redis_data = {
            "account_id": str(account_id),
            "scopes": scopes or [],
            "key_hash": key_hash
        }
        redis_client.set(f"api_prefix:{prefix}", json.dumps(redis_data), ex=3600*24)
        
        return raw_key

    async def verify_key(self, raw_key: str) -> Tuple[Optional[Account], List[str]]:
        """Verify the full API key and return account + scopes."""
        if not raw_key.startswith("kikuai_"):
            return None, []
        
        parts = raw_key.split("_")
        if len(parts) != 3:
            return None, []
        
        _, prefix, secret = parts
        incoming_hash = self._hash_key(secret)
        
        # Try Redis first
        cached_data = redis_client.get(f"api_prefix:{prefix}")
        if cached_data:
            if isinstance(cached_data, bytes):
                cached_data = cached_data.decode()
            data = json.loads(cached_data)
            if hmac.compare_digest(data["key_hash"], incoming_hash):
                account_id = UUID(data["account_id"])
                stmt = select(Account).where(Account.id == account_id)
                result = await self.session.execute(stmt)
                return result.scalar_one_or_none(), data["scopes"]
            else:
                return None, []
        
        # Database fallback
        stmt = select(APIKey).where(APIKey.key_prefix == prefix, APIKey.is_active == True)
        result = await self.session.execute(stmt)
        api_key_obj = result.scalar_one_or_none()
        
        if api_key_obj and hmac.compare_digest(api_key_obj.key_hash, incoming_hash):
            # Cache it
            redis_data = {
                "account_id": str(api_key_obj.account_id),
                "scopes": api_key_obj.scopes,
                "key_hash": api_key_obj.key_hash
            }
            redis_client.set(f"api_prefix:{prefix}", json.dumps(redis_data), ex=3600*24)
            
            stmt = select(Account).where(Account.id == api_key_obj.account_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none(), api_key_obj.scopes
            
        return None, []

    async def revoke_key(
        self, 
        account_id: UUID, 
        prefix: str, 
        actor_id: str = None,
        request_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Revoke a specific API key by its prefix."""
        stmt = select(APIKey).where(APIKey.account_id == account_id, APIKey.key_prefix == prefix)
        result = await self.session.execute(stmt)
        key = result.scalar_one_or_none()
        
        if key:
            key.is_active = False
            try:
                redis_client.delete(f"api_prefix:{prefix}")
            except Exception:
                pass # Degraded cache
                
            await self.record_audit(
                account_id, 
                "KEY_REVOKED", 
                actor_id=actor_id, 
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"prefix": prefix}
            )
            await self.session.commit()

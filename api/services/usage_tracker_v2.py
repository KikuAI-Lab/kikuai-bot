import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.base import UsageLog, Account, Product
from api.services.ledger_balance import LedgerBalanceService, redis_client

# Simple in-memory cache for product pricing to reduce DB hits
_product_price_cache = {}  # product_id -> (price: Decimal, timestamp: float)
_product_price_cache_ttl = 300  # 5 minutes

class UsageTracker:
    """Refactored UsageTracker using PostgreSQL as the Ledger and Redis as Buffer."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ledger = LedgerBalanceService(session)

    async def track_usage(
        self,
        telegram_id: int,
        product_id: str,
        idempotency_key: str,
        units: int = 1,
        metadata: Optional[dict] = None
    ) -> Decimal:
        """
        Track usage for a product and deduct cost.
        Requires an idempotency_key from the request layer.
        """
        # Get product pricing (with caching)
        price = self._get_cached_price(product_id)
        
        if price is None:
            # Cache miss - fetch from DB
            stmt = select(Product).where(Product.id == product_id)
            result = await self.session.execute(stmt)
            product = result.scalar_one_or_none()

            if not product:
                raise ValueError(f"Product {product_id} not found")
            
            price = Decimal(str(product.base_price_per_unit))
            self._set_cached_price(product_id, price)

        cost = price * units
        
        # Record in PostgreSQL (Ledger + UsageLog)
        new_balance = await self.ledger.record_usage(
            telegram_id=telegram_id,
            product_id=product_id,
            units=units,
            cost=cost,
            idempotency_key=idempotency_key,
            metadata=metadata
        )
        
        # Buffer counters in Redis for fast analytics (optional/redundant but good for real-time)
        month = datetime.utcnow().strftime("%Y-%m")
        redis_client.incrby(f"usage:{telegram_id}:{month}:{product_id}", units)
        
        return new_balance

    def _get_cached_price(self, product_id: str) -> Optional[Decimal]:
        """Get price from local cache if valid."""
        if product_id in _product_price_cache:
            price, timestamp = _product_price_cache[product_id]
            if datetime.utcnow().timestamp() - timestamp < _product_price_cache_ttl:
                return price
            else:
                del _product_price_cache[product_id]
        return None

    def _set_cached_price(self, product_id: str, price: Decimal):
        """Update local cache."""
        _product_price_cache[product_id] = (price, datetime.utcnow().timestamp())

    async def get_usage_stats(self, telegram_id: int, month: Optional[str] = None) -> Dict[str, Any]:
        """Get summarized usage stats from PostgreSQL."""
        if not month:
            # Current month logic
            start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = datetime.strptime(month, "%Y-%m")
            
        account_stmt = select(Account).where(Account.telegram_id == telegram_id)
        account_res = await self.session.execute(account_stmt)
        account = account_res.scalar_one_or_none()
        
        if not account:
            return {"error": "Account not found"}

        # Query usage logs
        stmt = select(
            UsageLog.product_id,
            func.sum(UsageLog.units_consumed).label("total_units"),
            func.sum(UsageLog.cost_usd).label("total_cost")
        ).where(
            UsageLog.account_id == account.id,
            UsageLog.timestamp >= start_date
        ).group_by(UsageLog.product_id)
        
        result = await self.session.execute(stmt)
        stats = []
        for row in result:
            stats.append({
                "product_id": row.product_id,
                "units": row.total_units,
                "cost_usd": float(row.total_cost)
            })
            
        return {
            "telegram_id": telegram_id,
            "period": month or "current_month",
            "balance_usd": float(account.balance_usd),
            "usage": stats
        }

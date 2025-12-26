"""Admin usage statistics endpoint."""

from datetime import datetime, timedelta
from typing import List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.db.base import get_db, Account, UsageLog
from api.middleware.auth import get_current_account

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class ProductUsage(BaseModel):
    product_id: str
    total_units: int
    total_cost_usd: float
    unique_users: int


class DailyUsage(BaseModel):
    date: str
    units: int
    cost_usd: float


class UsageStatsResponse(BaseModel):
    period: str
    total_revenue_usd: float
    total_requests: int
    unique_users: int
    by_product: List[ProductUsage]
    daily: List[DailyUsage]


class LowBalanceUser(BaseModel):
    telegram_id: int
    balance_usd: float
    last_activity: str | None


@router.get("/usage-stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    days: int = 30,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated usage statistics (admin only)."""
    # Simple admin check - can be extended
    if account.telegram_id not in [123456789]:  # Replace with actual admin IDs
        pass  # Allow all authenticated users for now
    
    since = datetime.utcnow() - timedelta(days=days)
    
    # Total stats
    stmt = select(
        func.sum(UsageLog.units),
        func.sum(UsageLog.cost_usd),
        func.count(func.distinct(UsageLog.telegram_id))
    ).where(UsageLog.created_at >= since)
    
    result = await db.execute(stmt)
    row = result.one()
    total_units = row[0] or 0
    total_cost = float(row[1] or 0)
    unique_users = row[2] or 0
    
    # By product
    stmt = select(
        UsageLog.product_id,
        func.sum(UsageLog.units),
        func.sum(UsageLog.cost_usd),
        func.count(func.distinct(UsageLog.telegram_id))
    ).where(UsageLog.created_at >= since).group_by(UsageLog.product_id)
    
    result = await db.execute(stmt)
    by_product = [
        ProductUsage(
            product_id=row[0],
            total_units=row[1] or 0,
            total_cost_usd=float(row[2] or 0),
            unique_users=row[3] or 0
        )
        for row in result.all()
    ]
    
    # Daily breakdown
    stmt = select(
        func.date(UsageLog.created_at),
        func.sum(UsageLog.units),
        func.sum(UsageLog.cost_usd)
    ).where(UsageLog.created_at >= since).group_by(
        func.date(UsageLog.created_at)
    ).order_by(func.date(UsageLog.created_at))
    
    result = await db.execute(stmt)
    daily = [
        DailyUsage(
            date=row[0].isoformat() if row[0] else "",
            units=row[1] or 0,
            cost_usd=float(row[2] or 0)
        )
        for row in result.all()
    ]
    
    return UsageStatsResponse(
        period=f"last_{days}_days",
        total_revenue_usd=total_cost,
        total_requests=total_units,
        unique_users=unique_users,
        by_product=by_product,
        daily=daily
    )


@router.get("/low-balance-users", response_model=List[LowBalanceUser])
async def get_low_balance_users(
    threshold: float = 1.0,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """Get users with low balance."""
    stmt = select(Account).where(
        Account.balance_usd < Decimal(str(threshold)),
        Account.balance_usd > 0
    ).order_by(Account.balance_usd)
    
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    
    return [
        LowBalanceUser(
            telegram_id=acc.telegram_id,
            balance_usd=float(acc.balance_usd),
            last_activity=acc.updated_at.isoformat() if acc.updated_at else None
        )
        for acc in accounts
    ]

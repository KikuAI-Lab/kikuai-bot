from decimal import Decimal, ROUND_HALF_EVEN
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.db.base import AsyncSessionLocal, Transaction as DBTransaction, Account as DBAccount
from api.services.payment_engine import BalanceManager, Transaction, TransactionType
from api.services.ledger_balance import LedgerBalanceService

class PostgresBalanceManager(BalanceManager):
    """
    Bridges the legacy PaymentEngine to the new PostgreSQL Ledger.
    Supports high-precision DECIMAL(18, 8) and Banker's Rounding.
    """
    def __init__(self, db_session: Optional[AsyncSession] = None):
        self._provided_session = db_session

    async def _get_ledger(self, session: AsyncSession) -> LedgerBalanceService:
        return LedgerBalanceService(session)

    async def get_balance(self, user_id: int) -> Decimal:
        """Get account balance by Telegram ID."""
        if self._provided_session:
            ledger = await self._get_ledger(self._provided_session)
            account = await ledger.get_account_by_tg_id(user_id)
            return account.balance_usd
        
        async with AsyncSessionLocal() as session:
            ledger = await self._get_ledger(session)
            account = await ledger.get_account_by_tg_id(user_id)
            return account.balance_usd

    async def update_balance(
        self,
        user_id: int,
        amount: Decimal,
        transaction: Transaction,
        idempotency_key: str,
    ) -> Decimal:
        """Record a transaction in the PostgreSQL ledger."""
        if self._provided_session:
            return await self._do_update(self._provided_session, user_id, amount, transaction, idempotency_key)
            
        async with AsyncSessionLocal() as session:
            return await self._do_update(session, user_id, amount, transaction, idempotency_key)

    async def _do_update(self, session, user_id, amount, transaction, idempotency_key):
        ledger = await self._get_ledger(session)
        # Enforce Decimal precision and Banker's Rounding
        amount_dec = Decimal(str(amount)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
        
        if amount_dec > 0:
            return await ledger.add_funds(
                telegram_id=user_id,
                amount=amount_dec,
                idempotency_key=idempotency_key,
                description=transaction.metadata.get("reason") or transaction.source
            )
        else:
            return await ledger.record_usage(
                telegram_id=user_id,
                product_id=transaction.source,
                units=1,
                cost=-amount_dec,
                idempotency_key=idempotency_key,
                metadata=transaction.metadata
            )

    async def check_idempotency(self, key: str) -> Optional[dict]:
        """Check if idempotency key exists in transactions table."""
        if self._provided_session:
            return await self._do_check_idempotency(self._provided_session, key)
            
        async with AsyncSessionLocal() as session:
            return await self._do_check_idempotency(session, key)

    async def _do_check_idempotency(self, session, key):
        stmt = select(DBTransaction).where(DBTransaction.idempotency_key == key)
        result = await session.execute(stmt)
        tx = result.scalar_one_or_none()
        if tx:
            return {"processed": True, "type": tx.type}
        return None

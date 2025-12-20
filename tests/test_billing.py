import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from api.db.base import Base, Account, Product, Transaction, UsageLog
from api.services.ledger_balance import LedgerBalanceService

# Use in-memory SQLite for testing if Postgres isn't available, 
# but for true verification we should use the configured DB.
# Here we'll mock the internal engine for unit testing.

@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_ledger_add_funds(test_db: AsyncSession):
    service = LedgerBalanceService(test_db)
    tg_id = 123456
    amount = Decimal("50.00")
    idempotency = str(uuid4())
    
    # 1. Add funds
    new_balance = await service.add_funds(tg_id, amount, idempotency)
    assert new_balance == amount
    
    # 2. Verify account exists
    account = await service.get_account_by_tg_id(tg_id)
    assert account.balance_usd == amount
    
    # 3. Verify transaction record
    from sqlalchemy import select
    stmt = select(Transaction).where(Transaction.account_id == account.id)
    result = await test_db.execute(stmt)
    tx = result.scalar_one()
    assert tx.amount_usd == amount
    assert tx.type == "topup"
    assert tx.idempotency_key == idempotency

@pytest.mark.asyncio
async def test_ledger_record_usage(test_db: AsyncSession):
    service = LedgerBalanceService(test_db)
    tg_id = 123456
    
    # Setup: Add funds and Product
    await service.add_funds(tg_id, Decimal("10.00"), "topup_1")
    
    product = Product(id="masker", name="Masker", base_price_per_unit=Decimal("0.01"))
    test_db.add(product)
    await test_db.commit()
    
    # 1. Record usage (10 units @ 0.01 = 0.10 cost)
    new_balance = await service.record_usage(tg_id, "masker", 10, Decimal("0.10"))
    assert new_balance == Decimal("9.90")
    
    # 2. Verify usage log
    from sqlalchemy import select
    account = await service.get_account_by_tg_id(tg_id)
    stmt = select(UsageLog).where(UsageLog.account_id == account.id)
    result = await test_db.execute(stmt)
    log = result.scalar_one()
    assert log.product_id == "masker"
    assert log.units_consumed == 10
    assert log.cost_usd == Decimal("0.10")

@pytest.mark.asyncio
async def test_insufficient_balance(test_db: AsyncSession):
    service = LedgerBalanceService(test_db)
    tg_id = 999
    
    # Try to use funds without having any
    with pytest.raises(ValueError, match="Insufficient balance"):
        await service.record_usage(tg_id, "masker", 1, Decimal("1.00"))

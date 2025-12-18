"""Redis-based BalanceManager implementation."""

import json
import secrets
from decimal import Decimal
from datetime import datetime
from typing import Optional
import redis

from api.services.payment_engine import BalanceManager, Transaction, TransactionType
from config.settings import REDIS_URL

redis_client = redis.from_url(REDIS_URL)


class RedisBalanceManager(BalanceManager):
    """Redis-based balance manager with atomic operations."""
    
    async def get_balance(self, user_id: int) -> Decimal:
        """Get user's current balance."""
        user_key = f"user:{user_id}"
        user_data = redis_client.get(user_key)
        
        if not user_data:
            return Decimal("0.00")
        
        try:
            user_dict = json.loads(user_data)
            balance = user_dict.get("balance_usd", 0.0)
            return Decimal(str(balance))
        except:
            return Decimal("0.00")
    
    async def update_balance(
        self,
        user_id: int,
        amount: Decimal,
        transaction: Transaction,
        idempotency_key: str,
    ) -> Decimal:
        """
        Atomically update balance and record transaction.
        Uses Lua script for atomicity.
        """
        lua_script = """
        -- Keys: user_key, transactions_key, idempotency_key
        -- Args: amount, transaction_json, timestamp
        
        local user_key = KEYS[1]
        local transactions_key = KEYS[2]
        local idempotency_key = KEYS[3]
        
        local amount = tonumber(ARGV[1])
        local transaction_json = ARGV[2]
        local timestamp = ARGV[3]
        
        -- Check idempotency first
        if redis.call('EXISTS', idempotency_key) == 1 then
            return {err = 'duplicate', key = idempotency_key}
        end
        
        -- Get current balance
        local user_data = redis.call('GET', user_key)
        local current_balance = 0.0
        
        if user_data then
            local user_dict = cjson.decode(user_data)
            current_balance = tonumber(user_dict.balance_usd or 0)
        end
        
        local new_balance = current_balance + amount
        
        -- Prevent negative balance for charges (negative amount)
        if amount < 0 and new_balance < 0 then
            return {err = 'insufficient_balance', balance = current_balance}
        end
        
        -- Update user balance
        if user_data then
            local user_dict = cjson.decode(user_data)
            user_dict.balance_usd = new_balance
            user_dict.last_active_at = timestamp
            redis.call('SET', user_key, cjson.encode(user_dict))
        else
            -- Create minimal user record if doesn't exist
            local new_user = {
                user_id = tonumber(user_key:match("user:(%d+)")),
                balance_usd = new_balance,
                last_active_at = timestamp
            }
            redis.call('SET', user_key, cjson.encode(new_user))
        end
        
        -- Add transaction to list
        redis.call('RPUSH', transactions_key, transaction_json)
        
        -- Keep only last 1000 transactions
        redis.call('LTRIM', transactions_key, -1000, -1)
        
        -- Mark idempotency key as processed (7 days TTL)
        redis.call('SETEX', idempotency_key, 604800, 'processed')
        
        return {ok = 'success', balance = new_balance}
        """
        
        user_key = f"user:{user_id}"
        transactions_key = f"transactions:{user_id}"
        idempotency_key_full = f"idempotency:{idempotency_key}"
        
        transaction_dict = transaction.to_dict()
        transaction_json = json.dumps(transaction_dict)
        timestamp = datetime.utcnow().isoformat()
        
        try:
            result = redis_client.eval(
                lua_script,
                3,
                user_key,
                transactions_key,
                idempotency_key_full,
                str(float(amount)),
                transaction_json,
                timestamp
            )
            
            # Handle Redis response format
            # Result can be: [b'ok', b'123.45'] or {'ok': 'success', 'balance': '123.45'}
            if isinstance(result, dict):
                if result.get('err') == 'duplicate':
                    from api.services.payment_engine import DuplicatePaymentError
                    raise DuplicatePaymentError(idempotency_key)
                elif result.get('err') == 'insufficient_balance':
                    from api.services.payment_engine import InsufficientBalanceError
                    current = Decimal(str(result.get('balance', 0)))
                    raise InsufficientBalanceError(current, -amount)
                elif result.get('ok') == 'success':
                    new_balance = Decimal(str(result.get('balance', 0)))
                    return new_balance
            elif isinstance(result, list) and len(result) >= 2:
                # Handle list format: [b'ok', b'123.45'] or ['ok', '123.45']
                status = result[0]
                if isinstance(status, bytes):
                    status = status.decode()
                
                if status == 'err':
                    error_type = result[1]
                    if isinstance(error_type, bytes):
                        error_type = error_type.decode()
                    
                    if error_type == 'duplicate':
                        from api.services.payment_engine import DuplicatePaymentError
                        raise DuplicatePaymentError(idempotency_key)
                    elif error_type == 'insufficient_balance':
                        from api.services.payment_engine import InsufficientBalanceError
                        current_balance = result[2] if len(result) > 2 else 0
                        if isinstance(current_balance, bytes):
                            current_balance = current_balance.decode()
                        current = Decimal(str(current_balance))
                        raise InsufficientBalanceError(current, -amount)
                elif status == 'ok':
                    balance_val = result[1]
                    if isinstance(balance_val, bytes):
                        balance_val = balance_val.decode()
                    new_balance = Decimal(str(balance_val))
                    return new_balance
            
            # Fallback if result format is unexpected
            raise Exception(f"Unexpected result format: {result}")
            
        except Exception as e:
            # Re-raise payment errors as-is
            from api.services.payment_engine import DuplicatePaymentError, InsufficientBalanceError
            if isinstance(e, (DuplicatePaymentError, InsufficientBalanceError)):
                raise
            # Wrap other errors
            raise Exception(f"Balance update failed: {str(e)}")
    
    async def check_idempotency(self, key: str) -> Optional[dict]:
        """Check if operation was already performed."""
        idempotency_key_full = f"idempotency:{key}"
        exists = redis_client.exists(idempotency_key_full)
        
        if exists:
            # Return minimal info that operation was processed
            return {"processed": True, "key": key}
        
        return None


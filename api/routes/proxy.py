"""Proxy endpoints for ReliAPI."""

from decimal import Decimal
from typing import Dict, Any, Optional
import secrets
from fastapi import APIRouter, HTTPException, Header, Body, status
from pydantic import BaseModel

from api.middleware.auth import verify_api_key, get_user
from api.services.reliapi import ReliAPIService
from api.services.usage_tracker import UsageTracker
from api.services.payment_engine import PaymentEngine, InsufficientBalanceError

router = APIRouter(prefix="/api/v1/proxy", tags=["proxy"])

reliapi_service = ReliAPIService()
usage_tracker = UsageTracker()

# PaymentEngine will be initialized in main.py and passed here
_payment_engine: Optional[PaymentEngine] = None


def set_payment_engine(engine: PaymentEngine):
    """Set payment engine instance."""
    global _payment_engine
    _payment_engine = engine


class LLMRequest(BaseModel):
    """LLM proxy request model."""
    target: str
    model: str
    messages: list
    cache: int = 3600
    idempotency_key: str = None
    max_retries: int = 3


class HTTPRequest(BaseModel):
    """HTTP proxy request model."""
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    body: Any = None
    cache: int = 3600
    idempotency_key: str = None
    max_retries: int = 3


@router.post("/llm")
async def proxy_llm(
    request: LLMRequest = Body(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Proxy LLM request to ReliAPI."""
    # Verify API key and get user_id
    user_id = await verify_api_key(x_api_key)
    
    # Get user to check balance
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Estimate cost (simplified - in production, use actual pricing)
    estimated_cost = Decimal("0.001")  # $0.001 per request estimate
    
    # Check balance and charge if payment engine available
    if _payment_engine:
        try:
            transaction = await _payment_engine.charge_usage(
                user_id=user_id,
                amount=estimated_cost,
                product_id="reliapi",
                details={
                    "endpoint": "proxy/llm",
                    "model": request.model,
                    "target": request.target,
                }
            )
        except InsufficientBalanceError as e:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient balance: ${e.current:.2f} available, ${e.required:.2f} required"
            )
    
    try:
        # Proxy request to ReliAPI
        # Note: We need to use the user's ReliAPI key, not our bot's key
        # For MVP, we'll use a placeholder
        reliapi_key = x_api_key  # In production, map to user's ReliAPI key
        
        result = await reliapi_service.proxy_llm_request(
            api_key=reliapi_key,
            request_data=request.dict(),
        )
        
        # Get actual cost from response if available
        actual_cost = Decimal(str(result.get("meta", {}).get("cost_usd", 0.0)))
        
        # Track usage
        usage_tracker.track_request(
            user_id=user_id,
            endpoint="proxy/llm",
            cost_usd=float(actual_cost),
        )
        
        # If actual cost differs from estimated, adjust balance
        # (For MVP, we'll skip this complexity)
        
        return result
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 402 Payment Required)
        raise
    except Exception as e:
        # Refund if request failed after charging
        if _payment_engine and estimated_cost > 0:
            try:
                # Refund the charge using balance manager directly
                from api.services.balance_manager import RedisBalanceManager
                from api.services.payment_engine import Transaction, TransactionType
                balance_manager = RedisBalanceManager()
                current_balance = await balance_manager.get_balance(user_id)
                refund_txn = Transaction(
                    id=f"refund_{secrets.token_hex(8)}",
                    user_id=user_id,
                    type=TransactionType.REFUND,
                    amount_usd=estimated_cost,
                    balance_before=current_balance,
                    balance_after=current_balance + estimated_cost,
                    source="reliapi",
                    metadata={"reason": "request_failed", "original_endpoint": "proxy/llm"}
                )
                await balance_manager.update_balance(
                    user_id=user_id,
                    amount=estimated_cost,
                    transaction=refund_txn,
                    idempotency_key=f"refund_{user_id}_{secrets.token_hex(8)}"
                )
            except Exception as refund_error:
                # Log but don't fail the error response
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to refund charge for user {user_id}: {refund_error}")
        
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/http")
async def proxy_http(
    request: HTTPRequest = Body(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Proxy HTTP request to ReliAPI."""
    # Verify API key and get user_id
    user_id = await verify_api_key(x_api_key)
    
    # Get user to check balance
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Estimate cost (simplified - HTTP proxy might have lower cost)
    estimated_cost = Decimal("0.0005")  # $0.0005 per request estimate
    
    # Check balance and charge if payment engine available
    if _payment_engine:
        try:
            transaction = await _payment_engine.charge_usage(
                user_id=user_id,
                amount=estimated_cost,
                product_id="reliapi",
                details={
                    "endpoint": "proxy/http",
                    "method": request.method,
                    "url": request.url,
                }
            )
        except InsufficientBalanceError as e:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient balance: ${e.current:.2f} available, ${e.required:.2f} required"
            )
    
    try:
        # Proxy request to ReliAPI
        reliapi_key = x_api_key  # In production, map to user's ReliAPI key
        
        result = await reliapi_service.proxy_http_request(
            api_key=reliapi_key,
            request_data=request.dict(),
        )
        
        # Get actual cost from response if available
        actual_cost = Decimal(str(result.get("meta", {}).get("cost_usd", 0.0)))
        
        # Track usage
        usage_tracker.track_request(
            user_id=user_id,
            endpoint="proxy/http",
            cost_usd=float(actual_cost),
        )
        
        return result
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 402 Payment Required)
        raise
    except Exception as e:
        # Refund if request failed after charging
        if _payment_engine and estimated_cost > 0:
            try:
                # Refund the charge using balance manager directly
                from api.services.balance_manager import RedisBalanceManager
                from api.services.payment_engine import Transaction, TransactionType
                balance_manager = RedisBalanceManager()
                current_balance = await balance_manager.get_balance(user_id)
                refund_txn = Transaction(
                    id=f"refund_{secrets.token_hex(8)}",
                    user_id=user_id,
                    type=TransactionType.REFUND,
                    amount_usd=estimated_cost,
                    balance_before=current_balance,
                    balance_after=current_balance + estimated_cost,
                    source="reliapi",
                    metadata={"reason": "request_failed", "original_endpoint": "proxy/http"}
                )
                await balance_manager.update_balance(
                    user_id=user_id,
                    amount=estimated_cost,
                    transaction=refund_txn,
                    idempotency_key=f"refund_{user_id}_{secrets.token_hex(8)}"
                )
            except Exception as refund_error:
                # Log but don't fail the error response
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to refund charge for user {user_id}: {refund_error}")
        
        raise HTTPException(status_code=500, detail=str(e))


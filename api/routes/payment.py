"""Payment endpoints."""

from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Body, status
from pydantic import BaseModel

from api.middleware.auth import verify_api_key
from api.services.payment_engine import (
    PaymentRequest,
    PaymentMethod,
    PaymentEngine,
    PaymentStatus,
)
from config.settings import WEBAPP_URL

router = APIRouter(prefix="/api/v1/payment", tags=["payment"])

# PaymentEngine will be initialized in main.py and passed here
# For now, we'll use a global variable that will be set
_payment_engine: Optional[PaymentEngine] = None


def set_payment_engine(engine: PaymentEngine):
    """Set payment engine instance."""
    global _payment_engine
    _payment_engine = engine


class TopupRequest(BaseModel):
    """Top-up request model."""
    amount_usd: float
    method: PaymentMethod


class TopupResponse(BaseModel):
    """Top-up response model."""
    payment_id: str
    method: PaymentMethod
    checkout_url: Optional[str] = None
    invoice_link: Optional[str] = None
    amount_usd: float
    expires_at: Optional[str] = None


@router.post("/topup", response_model=TopupResponse)
async def create_topup(
    request: TopupRequest = Body(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Create payment checkout session."""
    if not _payment_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service not initialized"
        )
    
    user_id = await verify_api_key(x_api_key)
    
    # Validate amount
    if request.amount_usd < 5.0 or request.amount_usd > 1000.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be between $5 and $1000"
        )
    
    # Create payment request
    payment_request = PaymentRequest(
        user_id=user_id,
        amount_usd=Decimal(str(request.amount_usd)),
        method=request.method,
    )
    
    # Generate URLs
    success_url = f"{WEBAPP_URL}/payment/success?session={{checkout_id}}"
    cancel_url = f"{WEBAPP_URL}/payment/cancel"
    
    try:
        # Create payment
        result = await _payment_engine.create_payment(
            request=payment_request,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        
        if not result.is_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error or "Payment creation failed"
            )
        
        return TopupResponse(
            payment_id=result.payment_id,
            method=request.method,
            checkout_url=result.checkout_url,
            invoice_link=result.invoice_link,
            amount_usd=request.amount_usd,
            expires_at=result.expires_at.isoformat() if result.expires_at else None,
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{payment_id}")
async def get_payment_status(
    payment_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Get payment status."""
    if not _payment_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service not initialized"
        )
    
    user_id = await verify_api_key(x_api_key)
    
    # TODO: Implement payment status lookup
    # For now, return placeholder
    return {
        "payment_id": payment_id,
        "status": "pending",
        "message": "Status check not yet implemented"
    }





"""Webhook endpoints for payment providers."""

from fastapi import APIRouter, HTTPException, Request, Header, status
from typing import Optional

from api.services.payment_engine import (
    WebhookEvent,
    PaymentMethod,
    PaymentEngine,
    InvalidSignatureError,
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# PaymentEngine will be initialized in main.py and passed here
_payment_engine: Optional[PaymentEngine] = None


def set_payment_engine(engine: PaymentEngine):
    """Set payment engine instance."""
    global _payment_engine
    _payment_engine = engine


@router.post("/paddle")
async def handle_paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature"),
):
    """
    Handle Paddle webhook events.
    
    Paddle requires 200 response to confirm receipt.
    Returns 200 even for errors to prevent retries of invalid requests.
    Returns 500 for transient errors to trigger retry.
    """
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    if not _payment_engine:
        logger.error("Paddle webhook received but payment engine not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service not initialized"
        )
    
    start_time = time.time()
    body = await request.body()
    
    # Parse webhook event
    try:
        event_data = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in Paddle webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    event_type = event_data.get("event_type", "unknown")
    event_id = event_data.get("event_id", "")
    
    logger.info(f"Paddle webhook received: type={event_type}, id={event_id}")
    
    # Create WebhookEvent
    webhook_event = WebhookEvent(
        provider=PaymentMethod.PADDLE,
        event_type=event_type,
        event_id=event_id,
        data=event_data.get("data", {}),
        raw_body=body,
        signature=paddle_signature,
    )
    
    from api.services.metrics import WebhookTimer, track_webhook_event
    
    with WebhookTimer("paddle"):
        try:
            # Process webhook
            transaction = await _payment_engine.process_webhook(webhook_event)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if transaction:
                logger.info(
                    f"Paddle webhook processed: event={event_id}, "
                    f"transaction={transaction.id}, duration={duration_ms:.0f}ms"
                )
                return {
                    "status": "processed",
                    "transaction_id": transaction.id,
                }
            else:
                logger.info(f"Paddle webhook ignored: event={event_id}, duration={duration_ms:.0f}ms")
                return {
                    "status": "ignored",
                    "message": "Event already processed or not applicable"
                }
        
        except InvalidSignatureError as e:
            logger.warning(f"Paddle webhook invalid signature: event={event_id}")
            # Return 200 to prevent retries - signature will never be valid
            return {
                "status": "error",
                "message": "Invalid signature"
            }
        
        except Exception as e:
            logger.error(f"Paddle webhook processing error: event={event_id}, error={e}")
            # Return 500 for transient errors to trigger Paddle retry
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Processing error: {str(e)}"
            )


@router.post("/telegram_stars")
async def handle_telegram_stars_webhook(
    request: Request,
):
    """Handle Telegram Stars webhook events."""
    # Telegram Stars doesn't use traditional webhooks
    # Payment is handled through aiogram's pre_checkout_query and successful_payment handlers
    # This endpoint is a placeholder for future use
    return {
        "status": "not_implemented",
        "message": "Telegram Stars payments are handled through bot handlers"
    }





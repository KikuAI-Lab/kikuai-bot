"""
Lemon Squeezy Payment Provider.

Implements PaymentProvider interface for Lemon Squeezy integration.
Handles checkout creation, webhook verification, and order processing.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx

from api.services.payment_engine import (
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    Transaction,
    TransactionType,
    WebhookEvent,
    InvalidSignatureError,
    ProviderError,
)
from config.settings import (
    LEMONSQUEEZY_API_KEY,
    LEMONSQUEEZY_STORE_ID,
    LEMONSQUEEZY_WEBHOOK_SECRET,
    CREDITS_PER_USD,
)

logger = logging.getLogger(__name__)

# Lemon Squeezy API base URL
LS_API_BASE = "https://api.lemonsqueezy.com/v1"


@dataclass
class LemonSqueezyCheckout:
    """Checkout session data from Lemon Squeezy."""
    checkout_id: str
    checkout_url: str
    expires_at: Optional[datetime] = None


class LemonSqueezyProvider(PaymentProvider):
    """
    Lemon Squeezy payment provider.
    
    Uses Lemon Squeezy's API for creating checkouts and processing
    webhook events for order completion.
    """
    
    def __init__(
        self,
        api_key: str = None,
        store_id: str = None,
        webhook_secret: str = None,
        balance_service=None,
    ):
        self._api_key = api_key or LEMONSQUEEZY_API_KEY
        self._store_id = store_id or LEMONSQUEEZY_STORE_ID
        self._webhook_secret = webhook_secret or LEMONSQUEEZY_WEBHOOK_SECRET
        self._balance_service = balance_service
        
        if not self._api_key:
            logger.warning("LemonSqueezy API key not configured")
    
    @property
    def name(self) -> str:
        return "lemonsqueezy"
    
    async def create_checkout(
        self,
        request: PaymentRequest,
        success_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        """
        Create a Lemon Squeezy checkout session.
        
        Uses the 'Create Checkout' API to generate a payment link.
        The checkout is configured for one-time credit purchases.
        """
        if not self._api_key or not self._store_id:
            return PaymentResult(
                payment_id="",
                status=PaymentStatus.FAILED,
                error="Lemon Squeezy not configured"
            )
        
        # Calculate credits from USD amount
        credits_amount = int(request.amount_usd * CREDITS_PER_USD)
        
        # Build checkout data
        # We use a dynamic checkout with custom price
        checkout_data = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "custom_price": int(request.amount_usd * 100),  # cents
                    "product_options": {
                        "name": f"{credits_amount:,} KikuAI Credits",
                        "description": f"Top up your KikuAI account with {credits_amount:,} credits (${request.amount_usd})",
                    },
                    "checkout_options": {
                        "button_color": "#00FFB2",
                    },
                    "checkout_data": {
                        "custom": {
                            "user_id": str(request.user_id),
                            "credits": credits_amount,
                            "idempotency_key": request.idempotency_key,
                        }
                    },
                    "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z",
                    "preview": False,
                },
                "relationships": {
                    "store": {
                        "data": {
                            "type": "stores",
                            "id": self._store_id,
                        }
                    },
                    # Note: For custom prices, we need a variant
                    # This will be configured via dashboard product
                },
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{LS_API_BASE}/checkouts",
                    json=checkout_data,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/vnd.api+json",
                        "Content-Type": "application/vnd.api+json",
                    },
                    timeout=30.0,
                )
                
                if response.status_code == 201:
                    data = response.json()
                    checkout = data.get("data", {})
                    attrs = checkout.get("attributes", {})
                    
                    checkout_url = attrs.get("url")
                    checkout_id = checkout.get("id", request.idempotency_key)
                    
                    logger.info(f"LemonSqueezy checkout created: {checkout_id}")
                    
                    return PaymentResult(
                        payment_id=checkout_id,
                        status=PaymentStatus.PENDING,
                        checkout_url=checkout_url,
                        expires_at=datetime.utcnow() + timedelta(hours=24),
                        metadata={
                            "user_id": request.user_id,
                            "credits": credits_amount,
                        }
                    )
                else:
                    error_msg = response.text[:200]
                    logger.error(f"LemonSqueezy checkout failed: {response.status_code} - {error_msg}")
                    return PaymentResult(
                        payment_id=request.idempotency_key,
                        status=PaymentStatus.FAILED,
                        error=f"Checkout creation failed: {response.status_code}"
                    )
                    
        except httpx.TimeoutException:
            logger.error("LemonSqueezy checkout timeout")
            return PaymentResult(
                payment_id=request.idempotency_key,
                status=PaymentStatus.FAILED,
                error="Payment service timeout"
            )
        except Exception as e:
            logger.error(f"LemonSqueezy checkout error: {e}")
            return PaymentResult(
                payment_id=request.idempotency_key,
                status=PaymentStatus.FAILED,
                error=str(e)
            )
    
    async def verify_webhook(self, event: WebhookEvent) -> bool:
        """
        Verify Lemon Squeezy webhook signature.
        
        Uses HMAC-SHA256 with the webhook secret to verify
        the X-Signature header matches the request body.
        """
        if not self._webhook_secret:
            logger.warning("LemonSqueezy webhook secret not configured")
            return False
        
        try:
            expected_signature = hmac.new(
                self._webhook_secret.encode("utf-8"),
                event.raw_body,
                hashlib.sha256
            ).hexdigest()
            
            # Signature is in format: sha256=<hex>
            provided = event.signature
            if provided.startswith("sha256="):
                provided = provided[7:]
            
            return hmac.compare_digest(expected_signature, provided)
            
        except Exception as e:
            logger.error(f"Webhook signature verification error: {e}")
            return False
    
    async def process_webhook(self, event: WebhookEvent) -> Optional[Transaction]:
        """
        Process Lemon Squeezy webhook event.
        
        Handles order_created event to credit user accounts.
        """
        # Verify signature first
        if not await self.verify_webhook(event):
            raise InvalidSignatureError("Invalid webhook signature")
        
        event_type = event.event_type
        logger.info(f"Processing LemonSqueezy webhook: {event_type}")
        
        # Only process order completion events
        if event_type not in ("order_created",):
            logger.debug(f"Ignoring event type: {event_type}")
            return None
        
        # Extract order data
        order_data = event.data.get("attributes", {})
        order_id = event.data.get("id", "")
        
        # Get custom data with user info
        meta = event.data.get("meta", {}).get("custom_data", {})
        if not meta:
            # Try alternative location
            meta = order_data.get("first_order_item", {}).get("custom_data", {})
        
        user_id = meta.get("user_id")
        credits = meta.get("credits")
        idempotency_key = meta.get("idempotency_key")
        
        if not user_id or not credits:
            logger.warning(f"Missing user_id or credits in webhook: {order_id}")
            return None
        
        # Get payment amount
        total_usd = Decimal(str(order_data.get("total", 0))) / 100
        
        logger.info(
            f"LemonSqueezy order completed: order={order_id}, "
            f"user={user_id}, credits={credits}, amount=${total_usd}"
        )
        
        # Credit the user's balance
        if self._balance_service:
            try:
                transaction = await self._balance_service.credit_balance(
                    user_id=int(user_id),
                    amount_usd=total_usd,
                    source=f"lemonsqueezy:{order_id}",
                    metadata={
                        "order_id": order_id,
                        "credits": credits,
                        "idempotency_key": idempotency_key,
                    }
                )
                return transaction
            except Exception as e:
                logger.error(f"Failed to credit balance: {e}")
                raise
        
        # Return a transaction record even without balance service
        return Transaction(
            id=f"ls_{order_id}",
            user_id=int(user_id),
            type=TransactionType.TOPUP,
            amount_usd=total_usd,
            balance_before=Decimal("0"),
            balance_after=total_usd,
            source=f"lemonsqueezy:{order_id}",
            external_id=order_id,
            metadata={
                "credits": credits,
                "idempotency_key": idempotency_key,
            }
        )
    
    async def get_payment_status(self, payment_id: str) -> PaymentStatus:
        """Get payment status from Lemon Squeezy."""
        # Would need to query orders API - for now return pending
        return PaymentStatus.PENDING
    
    async def refund(self, payment_id: str, amount: Optional[Decimal] = None) -> bool:
        """
        Refund a Lemon Squeezy order.
        
        Lemon Squeezy supports refunds through the dashboard and API.
        """
        if not self._api_key:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{LS_API_BASE}/orders/{payment_id}/refund",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/vnd.api+json",
                    },
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    logger.info(f"LemonSqueezy refund successful: {payment_id}")
                    return True
                else:
                    logger.error(f"LemonSqueezy refund failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"LemonSqueezy refund error: {e}")
            return False

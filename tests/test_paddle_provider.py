"""Tests for PaddleProvider."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time
import hashlib
import hmac

from api.services.payment_engine import (
    PaddleProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    PaymentMethod,
    WebhookEvent,
    Transaction,
    TransactionType,
    ProviderError,
    InvalidSignatureError,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def paddle_provider():
    """Create PaddleProvider instance for testing."""
    return PaddleProvider(
        api_key="test_api_key",
        webhook_secret="test_webhook_secret",
        sandbox=True,
    )


@pytest.fixture
def payment_request():
    """Create sample payment request."""
    return PaymentRequest(
        user_id=12345,
        amount_usd=Decimal("10.00"),
        method=PaymentMethod.PADDLE,
        idempotency_key="test_idempotency_key",
    )


@pytest.fixture
def webhook_secret():
    return "test_webhook_secret"


def create_signed_webhook(data: dict, secret: str, event_type: str = "transaction.completed") -> WebhookEvent:
    """Create a properly signed webhook event for testing."""
    timestamp = str(int(time.time()))
    raw_body = json.dumps(data).encode()
    
    signed_payload = f"{timestamp}:{raw_body.decode()}"
    signature = hmac.new(
        secret.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    
    return WebhookEvent(
        provider=PaymentMethod.PADDLE,
        event_type=event_type,
        event_id="evt_test_123",
        data=data.get("data", {}),
        raw_body=raw_body,
        signature=f"ts={timestamp};h1={signature}",
    )


# ============================================================================
# Test verify_webhook
# ============================================================================

class TestVerifyWebhook:
    """Tests for webhook signature verification."""
    
    @pytest.mark.asyncio
    async def test_valid_signature(self, paddle_provider, webhook_secret):
        """Test valid webhook signature is accepted."""
        data = {"data": {"id": "txn_123"}}
        event = create_signed_webhook(data, webhook_secret)
        
        result = await paddle_provider.verify_webhook(event)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_invalid_signature(self, paddle_provider):
        """Test invalid webhook signature is rejected."""
        data = {"data": {"id": "txn_123"}}
        event = create_signed_webhook(data, "wrong_secret")
        
        result = await paddle_provider.verify_webhook(event)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_missing_timestamp(self, paddle_provider):
        """Test webhook without timestamp is rejected."""
        event = WebhookEvent(
            provider=PaymentMethod.PADDLE,
            event_type="transaction.completed",
            event_id="evt_123",
            data={},
            raw_body=b"{}",
            signature="h1=invalid_signature",  # No ts=
        )
        
        result = await paddle_provider.verify_webhook(event)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_expired_timestamp(self, paddle_provider, webhook_secret):
        """Test webhook with old timestamp is rejected."""
        old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        raw_body = b'{"data": {}}'
        
        signed_payload = f"{old_timestamp}:{raw_body.decode()}"
        signature = hmac.new(
            webhook_secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        event = WebhookEvent(
            provider=PaymentMethod.PADDLE,
            event_type="transaction.completed",
            event_id="evt_123",
            data={},
            raw_body=raw_body,
            signature=f"ts={old_timestamp};h1={signature}",
        )
        
        result = await paddle_provider.verify_webhook(event)
        assert result is False


# ============================================================================
# Test process_webhook
# ============================================================================

class TestProcessWebhook:
    """Tests for webhook event processing."""
    
    @pytest.mark.asyncio
    async def test_transaction_completed(self, paddle_provider, webhook_secret):
        """Test processing of transaction.completed event."""
        data = {
            "data": {
                "id": "txn_paddle_123",
                "custom_data": json.dumps({
                    "user_id": "12345",
                    "amount_usd": "10.00",
                    "idempotency_key": "test_key",
                }),
                "details": {
                    "totals": {"total": "1000"}  # $10.00 in cents
                },
            }
        }
        event = create_signed_webhook(data, webhook_secret)
        event.event_type = "transaction.completed"
        event.data = data["data"]
        
        transaction = await paddle_provider.process_webhook(event)
        
        assert transaction is not None
        assert transaction.user_id == 12345
        assert transaction.amount_usd == Decimal("10.00")
        assert transaction.type == TransactionType.TOPUP
        assert transaction.source == "paddle"
    
    @pytest.mark.asyncio
    async def test_transaction_refunded(self, paddle_provider, webhook_secret):
        """Test processing of transaction.refunded event."""
        data = {
            "data": {
                "id": "txn_paddle_refund",
                "custom_data": json.dumps({
                    "user_id": "12345",
                }),
                "details": {
                    "totals": {"total": "500"}  # $5.00 in cents
                },
            }
        }
        event = create_signed_webhook(data, webhook_secret, "transaction.refunded")
        event.event_type = "transaction.refunded"
        event.data = data["data"]
        
        transaction = await paddle_provider.process_webhook(event)
        
        assert transaction is not None
        assert transaction.user_id == 12345
        assert transaction.amount_usd == Decimal("-5.00")  # Negative for refund
        assert transaction.type == TransactionType.REFUND
    
    @pytest.mark.asyncio
    async def test_payment_failed(self, paddle_provider, webhook_secret):
        """Test processing of transaction.payment_failed event."""
        data = {
            "data": {
                "id": "txn_failed",
                "custom_data": json.dumps({"user_id": "12345"}),
                "error": {"code": "card_declined"},
            }
        }
        event = create_signed_webhook(data, webhook_secret, "transaction.payment_failed")
        event.event_type = "transaction.payment_failed"
        event.data = data["data"]
        
        # Should return None (no transaction to record)
        transaction = await paddle_provider.process_webhook(event)
        assert transaction is None
    
    @pytest.mark.asyncio
    async def test_unknown_event_type(self, paddle_provider, webhook_secret):
        """Test processing of unknown event type."""
        data = {"data": {"id": "test"}}
        event = create_signed_webhook(data, webhook_secret, "subscription.created")
        event.event_type = "subscription.created"
        event.data = data["data"]
        
        transaction = await paddle_provider.process_webhook(event)
        assert transaction is None


# ============================================================================
# Test create_checkout
# ============================================================================

class TestCreateCheckout:
    """Tests for checkout creation."""
    
    @pytest.mark.asyncio
    async def test_create_checkout_success(self, paddle_provider, payment_request):
        """Test successful checkout creation with mocked API."""
        mock_response = {
            "data": {
                "id": "txn_123",
                "checkout": {"url": "https://checkout.paddle.com/123"},
            }
        }
        
        with patch.object(paddle_provider, "_request_with_retry", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await paddle_provider.create_checkout(
                request=payment_request,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
        
        assert result.payment_id == "txn_123"
        assert result.status == PaymentStatus.PENDING
        assert result.checkout_url == "https://checkout.paddle.com/123"
    
    @pytest.mark.asyncio
    async def test_create_checkout_api_error(self, paddle_provider, payment_request):
        """Test checkout creation when API returns error."""
        with patch.object(paddle_provider, "_request_with_retry", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ProviderError("paddle", "api_error", "Invalid request")
            
            with pytest.raises(ProviderError):
                await paddle_provider.create_checkout(
                    request=payment_request,
                    success_url="https://example.com/success",
                    cancel_url="https://example.com/cancel",
                )


# ============================================================================
# Test get_payment_status
# ============================================================================

class TestGetPaymentStatus:
    """Tests for payment status retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_status_completed(self, paddle_provider):
        """Test getting status of completed transaction."""
        with patch.object(paddle_provider, "_request_with_retry", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"data": {"status": "completed"}}
            
            status = await paddle_provider.get_payment_status("txn_123")
        
        assert status == PaymentStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_get_status_pending(self, paddle_provider):
        """Test getting status of pending transaction."""
        with patch.object(paddle_provider, "_request_with_retry", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"data": {"status": "draft"}}
            
            status = await paddle_provider.get_payment_status("txn_123")
        
        assert status == PaymentStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_get_status_not_found(self, paddle_provider):
        """Test getting status of non-existent transaction."""
        with patch.object(paddle_provider, "_request_with_retry", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ProviderError("paddle", "not_found", "Transaction not found")
            
            status = await paddle_provider.get_payment_status("txn_invalid")
        
        assert status == PaymentStatus.FAILED


# ============================================================================
# Integration tests (require Paddle sandbox)
# ============================================================================

@pytest.mark.skip(reason="Requires Paddle sandbox API key")
class TestPaddleIntegration:
    """Integration tests with Paddle sandbox."""
    
    @pytest.mark.asyncio
    async def test_real_checkout_creation(self):
        """Test creating real checkout with Paddle sandbox."""
        import os
        
        provider = PaddleProvider(
            api_key=os.getenv("PADDLE_API_KEY", ""),
            webhook_secret=os.getenv("PADDLE_WEBHOOK_SECRET", ""),
            sandbox=True,
        )
        
        request = PaymentRequest(
            user_id=99999,
            amount_usd=Decimal("5.00"),
            method=PaymentMethod.PADDLE,
        )
        
        result = await provider.create_checkout(
            request=request,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        
        assert result.payment_id
        assert result.checkout_url
        assert result.status == PaymentStatus.PENDING

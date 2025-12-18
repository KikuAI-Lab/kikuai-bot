"""Tests for TelegramStarsProvider."""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import json

from api.services.payment_engine import (
    TelegramStarsProvider,
    PaymentRequest,
    PaymentStatus,
    PaymentMethod,
    WebhookEvent,
    TransactionType,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def stars_provider():
    """Create TelegramStarsProvider instance for testing."""
    mock_redis = MagicMock()
    return TelegramStarsProvider(
        bot_token="test_bot_token",
        redis_client=mock_redis,
    )


@pytest.fixture
def payment_request():
    """Create sample payment request."""
    return PaymentRequest(
        user_id=12345,
        amount_usd=Decimal("5.00"),
        method=PaymentMethod.TELEGRAM_STARS,
        idempotency_key="test_idempotency_key",
    )


# ============================================================================
# Test USD/Stars conversion
# ============================================================================

class TestConversion:
    """Tests for USD/Stars conversion."""
    
    def test_usd_to_stars(self):
        """Test USD to Stars conversion."""
        assert TelegramStarsProvider.usd_to_stars(Decimal("1.00")) == 50
        assert TelegramStarsProvider.usd_to_stars(Decimal("5.00")) == 250
        assert TelegramStarsProvider.usd_to_stars(Decimal("10.00")) == 500
        assert TelegramStarsProvider.usd_to_stars(Decimal("20.00")) == 1000
    
    def test_stars_to_usd(self):
        """Test Stars to USD conversion."""
        assert TelegramStarsProvider.stars_to_usd(50) == Decimal("1")
        assert TelegramStarsProvider.stars_to_usd(250) == Decimal("5")
        assert TelegramStarsProvider.stars_to_usd(500) == Decimal("10")
        assert TelegramStarsProvider.stars_to_usd(1000) == Decimal("20")
    
    def test_get_package_for_usd(self):
        """Test finding Stars package by USD amount."""
        package = TelegramStarsProvider.get_package_for_usd(Decimal("5.00"))
        assert package is not None
        assert package["stars"] == 250
        
        package = TelegramStarsProvider.get_package_for_usd(Decimal("10.00"))
        assert package is not None
        assert package["stars"] == 500
        
        # Non-standard amount
        package = TelegramStarsProvider.get_package_for_usd(Decimal("7.50"))
        assert package is None


# ============================================================================
# Test create_checkout
# ============================================================================

class TestCreateCheckout:
    """Tests for checkout/invoice creation."""
    
    @pytest.mark.asyncio
    async def test_create_checkout_returns_invoice_data(self, stars_provider, payment_request):
        """Test that create_checkout returns invoice data (not URL)."""
        result = await stars_provider.create_checkout(
            request=payment_request,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        
        assert result.status == PaymentStatus.PENDING
        assert result.checkout_url is None  # Stars doesn't use URLs
        assert result.payment_id.startswith("topup:")
        assert result.metadata.get("stars") == 250  # $5 = 250 Stars
    
    @pytest.mark.asyncio
    async def test_create_checkout_stores_pending_in_redis(self, stars_provider, payment_request):
        """Test that create_checkout stores pending payment in Redis."""
        await stars_provider.create_checkout(
            request=payment_request,
            success_url="",
            cancel_url="",
        )
        
        # Check Redis setex was called
        stars_provider._redis.setex.assert_called_once()
        call_args = stars_provider._redis.setex.call_args
        key = call_args[0][0]
        ttl = call_args[0][1]
        
        assert key.startswith("pending_stars:")
        assert ttl == 3600  # 1 hour
    
    @pytest.mark.asyncio
    async def test_create_checkout_different_amounts(self, stars_provider):
        """Test create_checkout with various amounts."""
        for amount, expected_stars in [
            (Decimal("1.00"), 50),
            (Decimal("5.00"), 250),
            (Decimal("10.00"), 500),
            (Decimal("20.00"), 1000),
        ]:
            request = PaymentRequest(
                user_id=12345,
                amount_usd=amount,
                method=PaymentMethod.TELEGRAM_STARS,
            )
            
            result = await stars_provider.create_checkout(request, "", "")
            assert result.metadata.get("stars") == expected_stars


# ============================================================================
# Test process_webhook
# ============================================================================

class TestProcessWebhook:
    """Tests for processing successful_payment callbacks."""
    
    @pytest.mark.asyncio
    async def test_process_successful_payment(self, stars_provider):
        """Test processing successful Stars payment."""
        payload = "topup:12345:1234567890:abcd1234"
        
        # Mock Redis with pending data
        stars_provider._redis.get.return_value = json.dumps({
            "user_id": 12345,
            "stars": 250,
            "usd": "5.00",
        }).encode()
        
        event = WebhookEvent(
            provider=PaymentMethod.TELEGRAM_STARS,
            event_type="successful_payment",
            event_id="charge_123",
            data={
                "user_id": 12345,
                "payload": payload,
                "telegram_payment_charge_id": "charge_123",
                "total_amount": 250,
            },
            raw_body=b"",
            signature="",
        )
        
        transaction = await stars_provider.process_webhook(event)
        
        assert transaction is not None
        assert transaction.user_id == 12345
        assert transaction.amount_usd == Decimal("5.00")
        assert transaction.type == TransactionType.TOPUP
        assert transaction.source == "telegram_stars"
        assert transaction.external_id == "charge_123"
    
    @pytest.mark.asyncio
    async def test_process_payment_without_pending_data(self, stars_provider):
        """Test processing payment when pending data is missing."""
        stars_provider._redis.get.return_value = None
        
        event = WebhookEvent(
            provider=PaymentMethod.TELEGRAM_STARS,
            event_type="successful_payment",
            event_id="charge_123",
            data={
                "user_id": 12345,
                "payload": "topup:12345:123",
                "telegram_payment_charge_id": "charge_123",
                "total_amount": 100,
            },
            raw_body=b"",
            signature="",
        )
        
        transaction = await stars_provider.process_webhook(event)
        
        assert transaction is not None
        # Should calculate USD from stars
        assert transaction.amount_usd == Decimal("2")  # 100 stars / 50 = $2
    
    @pytest.mark.asyncio
    async def test_process_payment_missing_user_id(self, stars_provider):
        """Test processing payment without user_id returns None."""
        event = WebhookEvent(
            provider=PaymentMethod.TELEGRAM_STARS,
            event_type="successful_payment",
            event_id="charge_123",
            data={
                "payload": "topup:12345:123",
            },
            raw_body=b"",
            signature="",
        )
        
        transaction = await stars_provider.process_webhook(event)
        assert transaction is None


# ============================================================================
# Test get_payment_status
# ============================================================================

class TestGetPaymentStatus:
    """Tests for payment status retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_status_pending(self, stars_provider):
        """Test getting status of pending payment."""
        stars_provider._redis.exists.side_effect = lambda key: key.startswith("pending_stars:")
        
        status = await stars_provider.get_payment_status("topup:12345:123")
        assert status == PaymentStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_get_status_completed(self, stars_provider):
        """Test getting status of completed payment."""
        def check_exists(key):
            if key.startswith("stars_processed:"):
                return True
            return False
        
        stars_provider._redis.exists.side_effect = check_exists
        
        status = await stars_provider.get_payment_status("topup:12345:123")
        assert status == PaymentStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_get_status_unknown(self, stars_provider):
        """Test getting status of unknown payment defaults to pending."""
        stars_provider._redis.exists.return_value = False
        
        status = await stars_provider.get_payment_status("unknown")
        assert status == PaymentStatus.PENDING


# ============================================================================
# Test verify_webhook
# ============================================================================

class TestVerifyWebhook:
    """Tests for webhook verification (always true for Stars)."""
    
    @pytest.mark.asyncio
    async def test_verify_always_true(self, stars_provider):
        """Test that verify_webhook always returns True for Stars."""
        event = WebhookEvent(
            provider=PaymentMethod.TELEGRAM_STARS,
            event_type="successful_payment",
            event_id="evt_123",
            data={},
            raw_body=b"",
            signature="",
        )
        
        result = await stars_provider.verify_webhook(event)
        assert result is True

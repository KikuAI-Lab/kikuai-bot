"""Tests for webhook handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import json
import time
import hmac
import hashlib


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def webhook_secret():
    return "test_webhook_secret"


def create_paddle_signature(body: bytes, secret: str) -> str:
    """Create valid Paddle webhook signature."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}:{body.decode()}"
    signature = hmac.new(
        secret.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"ts={timestamp};h1={signature}"


# ============================================================================
# Test Paddle webhook endpoint
# ============================================================================

class TestPaddleWebhook:
    """Tests for Paddle webhook endpoint."""
    
    @pytest.mark.asyncio
    async def test_valid_webhook_processed(self, webhook_secret):
        """Test that valid webhook is processed."""
        from api.routes.webhooks import handle_paddle_webhook, set_payment_engine
        from api.services.payment_engine import (
            PaymentEngine, PaymentMethod, Transaction, TransactionType
        )
        
        # Create mock request
        event_data = {
            "event_type": "transaction.completed",
            "event_id": "evt_123",
            "data": {
                "id": "txn_123",
                "custom_data": json.dumps({"user_id": "12345", "amount_usd": "10.00"}),
                "details": {"totals": {"total": "1000"}},
            }
        }
        body = json.dumps(event_data).encode()
        signature = create_paddle_signature(body, webhook_secret)
        
        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        mock_request.json = AsyncMock(return_value=event_data)
        
        # Mock payment engine
        mock_transaction = MagicMock()
        mock_transaction.id = "txn_processed"
        
        mock_engine = MagicMock()
        mock_engine.process_webhook = AsyncMock(return_value=mock_transaction)
        mock_engine.get_provider = MagicMock()
        mock_engine.get_provider.return_value.verify_webhook = AsyncMock(return_value=True)
        
        set_payment_engine(mock_engine)
        
        result = await handle_paddle_webhook(mock_request, signature)
        
        assert result["status"] == "processed"
        assert result["transaction_id"] == "txn_processed"
    
    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, webhook_secret):
        """Test that invalid signature is rejected."""
        from api.routes.webhooks import handle_paddle_webhook, set_payment_engine
        
        event_data = {
            "event_type": "transaction.completed",
            "event_id": "evt_123",
            "data": {}
        }
        body = json.dumps(event_data).encode()
        invalid_signature = "ts=123;h1=invalid"
        
        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        mock_request.json = AsyncMock(return_value=event_data)
        
        mock_engine = MagicMock()
        mock_engine.get_provider = MagicMock()
        mock_engine.get_provider.return_value.verify_webhook = AsyncMock(return_value=False)
        mock_engine.process_webhook = AsyncMock(side_effect=Exception("Invalid signature"))
        
        set_payment_engine(mock_engine)
        
        from api.services.payment_engine import InvalidSignatureError
        mock_engine.process_webhook = AsyncMock(
            side_effect=InvalidSignatureError("Invalid signature")
        )
        
        result = await handle_paddle_webhook(mock_request, invalid_signature)
        
        assert result["status"] == "error"
        assert "signature" in result["message"].lower()
    
    @pytest.mark.asyncio
    async def test_duplicate_webhook_ignored(self, webhook_secret):
        """Test that duplicate webhook is ignored."""
        from api.routes.webhooks import handle_paddle_webhook, set_payment_engine
        
        event_data = {
            "event_type": "transaction.completed",
            "event_id": "evt_duplicate",
            "data": {}
        }
        body = json.dumps(event_data).encode()
        signature = create_paddle_signature(body, webhook_secret)
        
        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        mock_request.json = AsyncMock(return_value=event_data)
        
        mock_engine = MagicMock()
        mock_engine.process_webhook = AsyncMock(return_value=None)  # Already processed
        
        set_payment_engine(mock_engine)
        
        result = await handle_paddle_webhook(mock_request, signature)
        
        assert result["status"] == "ignored"
    
    @pytest.mark.asyncio
    async def test_missing_payment_engine_returns_503(self):
        """Test that missing payment engine returns 503."""
        from api.routes.webhooks import handle_paddle_webhook, set_payment_engine
        from fastapi import HTTPException
        
        set_payment_engine(None)
        
        mock_request = MagicMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_paddle_webhook(mock_request, "ts=123;h1=test")
        
        assert exc_info.value.status_code == 503


# ============================================================================
# Test Telegram Stars webhook endpoint
# ============================================================================

class TestTelegramStarsWebhook:
    """Tests for Telegram Stars webhook endpoint."""
    
    @pytest.mark.asyncio
    async def test_stars_webhook_returns_not_implemented(self):
        """Test that Stars webhook returns not_implemented."""
        from api.routes.webhooks import handle_telegram_stars_webhook
        
        mock_request = MagicMock()
        
        result = await handle_telegram_stars_webhook(mock_request)
        
        assert result["status"] == "not_implemented"


# ============================================================================
# Test webhook logging
# ============================================================================

class TestWebhookLogging:
    """Tests for webhook logging."""
    
    @pytest.mark.asyncio
    async def test_webhook_logs_event(self, webhook_secret, caplog):
        """Test that webhook events are logged."""
        import logging
        
        from api.routes.webhooks import handle_paddle_webhook, set_payment_engine
        
        event_data = {
            "event_type": "transaction.completed",
            "event_id": "evt_log_test",
            "data": {}
        }
        body = json.dumps(event_data).encode()
        signature = create_paddle_signature(body, webhook_secret)
        
        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        mock_request.json = AsyncMock(return_value=event_data)
        
        mock_engine = MagicMock()
        mock_engine.process_webhook = AsyncMock(return_value=None)
        
        set_payment_engine(mock_engine)
        
        with caplog.at_level(logging.INFO):
            await handle_paddle_webhook(mock_request, signature)
        
        # Check that event was logged
        assert any("evt_log_test" in record.message for record in caplog.records)

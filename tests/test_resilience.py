"""Tests for payment resilience and metrics."""

import pytest
import httpx
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from api.services.payment_engine import PaddleProvider, PaymentRequest, PaymentMethod, ProviderError

@pytest.mark.asyncio
async def test_paddle_rate_limit_retry():
    """Test that PaddleProvider retries when receiving 429."""
    provider = PaddleProvider(api_key="test_key", webhook_secret="test_secret")
    
    # Mock httpx client
    mock_client = AsyncMock()
    provider._client = mock_client
    
    # Mock responses: 429 once, then 200
    mock_resp_429 = MagicMock(spec=httpx.Response)
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "0"}  # Retry immediately for test
    
    mock_resp_200 = MagicMock(spec=httpx.Response)
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"data": {"id": "txn_123", "checkout": {"url": "https://test.com"}}}
    
    mock_client.request.side_effect = [mock_resp_429, mock_resp_200]
    
    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        request = PaymentRequest(user_id=123, amount_usd=Decimal("10"), method=PaymentMethod.PADDLE)
        result = await provider.create_checkout(request, "https://success", "https://cancel")
        
        assert result.is_success
        assert result.payment_id == "txn_123"
        assert mock_client.request.call_count == 2
        mock_sleep.assert_called_with(0)

@pytest.mark.asyncio
async def test_paddle_server_error_retry():
    """Test that PaddleProvider retries on 500 errors."""
    provider = PaddleProvider(api_key="test_key", webhook_secret="test_secret", max_retries=3)
    
    mock_client = AsyncMock()
    provider._client = mock_client
    
    mock_resp_500 = MagicMock(spec=httpx.Response)
    mock_resp_500.status_code = 500
    
    mock_client.request.return_value = mock_resp_500
    
    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        request = PaymentRequest(user_id=123, amount_usd=Decimal("10"), method=PaymentMethod.PADDLE)
        
        with pytest.raises(ProviderError) as excinfo:
            await provider.create_checkout(request, "https://success", "https://cancel")
        
        assert excinfo.value.code == "max_retries"
        assert mock_client.request.call_count == 3
        assert mock_sleep.call_count == 2

@pytest.mark.asyncio
async def test_metrics_recording():
    """Test that metrics are recorded during checkout creation."""
    from api.services.metrics import payment_requests_total
    
    provider = PaddleProvider(api_key="test_key", webhook_secret="test_secret")
    mock_client = AsyncMock()
    provider._client = mock_client
    
    mock_resp_200 = MagicMock(spec=httpx.Response)
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"data": {"id": "txn_123", "checkout": {"url": "https://test.com"}}}
    mock_client.request.return_value = mock_resp_200
    
    # Get initial values if possible (might be tricky with global registry)
    # We can just check if .inc() was called by patching the counter
    with patch("api.services.metrics.payment_requests_total.labels") as mock_labels:
        mock_counter = MagicMock()
        mock_labels.return_value = mock_counter
        
        request = PaymentRequest(user_id=123, amount_usd=Decimal("10"), method=PaymentMethod.PADDLE)
        await provider.create_checkout(request, "https://success", "https://cancel")
        
        mock_labels.assert_called_with(method="paddle", status="success")
        mock_counter.inc.assert_called_once()

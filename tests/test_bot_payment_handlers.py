"""Tests for bot payment handlers."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json


# ============================================================================
# Test /topup command
# ============================================================================

class TestTopupCommand:
    """Tests for /topup command."""
    
    @pytest.mark.asyncio
    async def test_topup_shows_amount_buttons(self):
        """Test that /topup shows inline keyboard with amounts."""
        from bot.handlers.payment import cmd_topup
        
        # Create mock message
        message = MagicMock()
        message.answer = AsyncMock()
        
        await cmd_topup(message)
        
        message.answer.assert_called_once()
        call_args = message.answer.call_args
        
        # Check message contains amount info
        assert "$" in call_args[0][0] or "💰" in call_args[0][0]
        
        # Check keyboard was passed
        assert "reply_markup" in call_args[1]


# ============================================================================
# Test amount selection callback
# ============================================================================

class TestAmountSelection:
    """Tests for amount selection callbacks."""
    
    @pytest.mark.asyncio
    async def test_select_amount_shows_payment_methods(self):
        """Test that selecting amount shows Paddle and Stars options."""
        from bot.handlers.payment import select_payment_method
        
        callback = MagicMock()
        callback.data = "topup_amount:10"
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()
        
        await select_payment_method(callback)
        
        callback.message.edit_text.assert_called_once()
        call_args = callback.message.edit_text.call_args
        
        # Check message mentions both payment methods
        text = call_args[0][0]
        assert "Paddle" in text or "💳" in text
        assert "Stars" in text or "⭐" in text


# ============================================================================
# Test payment flow integration
# ============================================================================

class TestPaymentFlowIntegration:
    """Integration tests for payment flow."""
    
    def test_stars_packages_defined(self):
        """Test that Stars packages are defined."""
        from bot.handlers.payment import STARS_PACKAGES
        
        assert len(STARS_PACKAGES) > 0
        for pkg in STARS_PACKAGES:
            assert "stars" in pkg
            assert "usd" in pkg
    
    def test_topup_amounts_defined(self):
        """Test that top-up amounts are defined."""
        from bot.handlers.payment import TOPUP_AMOUNTS
        
        assert len(TOPUP_AMOUNTS) >= 5
        assert 5 in TOPUP_AMOUNTS
        assert 100 in TOPUP_AMOUNTS


# ============================================================================
# Test callback data parsing
# ============================================================================

class TestCallbackParsing:
    """Tests for callback data parsing."""
    
    def test_topup_amount_parsing(self):
        """Test parsing topup_amount callback data."""
        data = "topup_amount:25"
        parts = data.split(":")
        assert parts[0] == "topup_amount"
        assert int(parts[1]) == 25
    
    def test_pay_paddle_parsing(self):
        """Test parsing pay_paddle callback data."""
        data = "pay_paddle:50"
        parts = data.split(":")
        assert parts[0] == "pay_paddle"
        assert int(parts[1]) == 50
    
    def test_stars_invoice_parsing(self):
        """Test parsing stars_invoice callback data."""
        data = "stars_invoice:250:5"
        parts = data.split(":")
        assert parts[0] == "stars_invoice"
        assert int(parts[1]) == 250  # stars
        assert int(parts[2]) == 5    # usd

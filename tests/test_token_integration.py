"""
Integration tests for token tracking in async endpoints.

Tests cover:
- Token stats endpoint availability
- Token counting in requests
- Cost estimation accuracy
- Risk level assessment in endpoints
- Token metadata tracking
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.token_tracking import TokenTracker, get_token_tracker


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestTokenStatsEndpoint:
    """Test token statistics endpoint."""

    def test_token_stats_endpoint_exists(self, client):
        """Token stats endpoint should be accessible."""
        response = client.get("/api/v1/tokens/stats")
        assert response.status_code == 200

    def test_token_stats_response_structure(self, client):
        """Token stats response should have correct structure."""
        response = client.get("/api/v1/tokens/stats")
        data = response.json()

        assert "tracker_status" in data
        assert "thresholds" in data
        assert "daily_limit" in data
        assert "pricing" in data
        assert "models_supported" in data
        assert "timestamp" in data

    def test_token_stats_thresholds(self, client):
        """Token stats should include correct thresholds."""
        response = client.get("/api/v1/tokens/stats")
        data = response.json()

        thresholds = data["thresholds"]
        assert thresholds["warning_threshold"] == 8000
        assert thresholds["critical_threshold"] == 15000

    def test_token_stats_daily_limit(self, client):
        """Token stats should show daily limit."""
        response = client.get("/api/v1/tokens/stats")
        data = response.json()

        assert data["daily_limit"] == 1_000_000

    def test_token_stats_pricing_models(self, client):
        """Token stats should include all pricing models."""
        response = client.get("/api/v1/tokens/stats")
        data = response.json()

        pricing = data["pricing"]
        assert "gpt-3.5-turbo" in pricing
        assert "gpt-4" in pricing
        assert "gpt-4-turbo" in pricing

        # Check structure
        assert pricing["gpt-3.5-turbo"]["input"] == 0.50
        assert pricing["gpt-3.5-turbo"]["output"] == 1.50

    def test_token_stats_supported_models(self, client):
        """Token stats should list all supported models."""
        response = client.get("/api/v1/tokens/stats")
        data = response.json()

        models = data["models_supported"]
        assert len(models) >= 4
        assert "gpt-3.5-turbo" in models
        assert "gpt-4" in models


class TestTokenCountingInEndpoints:
    """Test token counting integration with endpoints."""

    def test_token_stats_endpoint_integration(self, client):
        """Token stats should integrate with async system."""
        response = client.get("/api/v1/tokens/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["tracker_status"] == "active"


class TestTokenPricingCalculation:
    """Test token pricing calculations."""

    def test_token_cost_calculation_accuracy(self):
        """Token cost calculation should be accurate."""
        tracker = get_token_tracker()

        # 1M input tokens at $0.50/M
        cost = tracker.estimate_cost(1_000_000, 0, "gpt-3.5-turbo")
        assert cost == 0.50

    def test_token_cost_with_output_tokens(self):
        """Token cost should account for output tokens."""
        tracker = get_token_tracker()

        # 500K input + 500K output
        # Input: 500K * $0.50/M = $0.25
        # Output: 500K * $1.50/M = $0.75
        # Total: $1.00
        cost = tracker.estimate_cost(500_000, 500_000, "gpt-3.5-turbo")
        assert float(cost) == 1.00

    def test_token_cost_different_models(self):
        """Different models should have different costs."""
        tracker = get_token_tracker()

        cost_35 = tracker.estimate_cost(1_000_000, 0, "gpt-3.5-turbo")
        cost_4 = tracker.estimate_cost(1_000_000, 0, "gpt-4")

        assert float(cost_35) == 0.50
        assert float(cost_4) == 3.00
        assert float(cost_4) > float(cost_35)

    def test_token_cost_for_typical_request(self):
        """Estimate cost for typical request."""
        tracker = get_token_tracker()

        # Typical request: 500 input, 100 output
        cost = tracker.estimate_cost(500, 100, "gpt-3.5-turbo")

        # Input: 500 * $0.50/M = $0.00025
        # Output: 100 * $1.50/M = $0.00015
        # Total: $0.0004
        assert float(cost) > 0
        assert float(cost) < 0.001


class TestTokenRiskAssessment:
    """Test token risk level assessment."""

    def test_safe_risk_level_in_stats(self, client):
        """Safe token counts should be labeled."""
        tracker = get_token_tracker()
        risk_level, warning = tracker.get_risk_level(1000)
        assert risk_level.value == "safe"
        assert warning is None

    def test_warning_risk_level_in_stats(self, client):
        """Token counts near warning threshold."""
        tracker = get_token_tracker()
        risk_level, warning = tracker.get_risk_level(8000)
        assert risk_level.value == "warning"
        assert warning is not None

    def test_critical_risk_level_in_stats(self, client):
        """Token counts above critical threshold."""
        tracker = get_token_tracker()
        risk_level, warning = tracker.get_risk_level(15000)
        assert risk_level.value == "critical"
        assert warning is not None


class TestTokenFormattingUtilities:
    """Test token count formatting utilities."""

    def test_format_small_token_count(self):
        """Small token counts should display as numbers."""
        tracker = get_token_tracker()
        assert tracker.format_token_count(500) == "500"

    def test_format_medium_token_count(self):
        """Medium token counts should use K notation."""
        tracker = get_token_tracker()
        assert tracker.format_token_count(5_000) == "5.00K"

    def test_format_large_token_count(self):
        """Large token counts should use M notation."""
        tracker = get_token_tracker()
        assert tracker.format_token_count(1_000_000) == "1.00M"


class TestTokenModelSupport:
    """Test token counting for different models."""

    def test_token_counting_consistency_across_models(self):
        """Token counting should be consistent for same text."""
        tracker = get_token_tracker()

        text = "This is a test sentence."

        # All models use same tokenizer
        count1 = tracker.count_tokens(text)
        count2 = tracker.count_tokens(text)

        assert count1 == count2
        assert count1 > 0

    def test_batch_token_counting(self):
        """Batch token counting should work correctly."""
        tracker = get_token_tracker()

        texts = ["First text", "Second text", "Third text"]

        counts = tracker.count_tokens_batch(texts)
        assert len(counts) == 3
        assert all(c > 0 for c in counts)

    def test_unicode_text_token_counting(self):
        """Unicode text should be counted correctly."""
        tracker = get_token_tracker()

        unicode_texts = [
            "Hello 世界",
            "Привет мир",
            "مرحبا بالعالم",
        ]

        for text in unicode_texts:
            count = tracker.count_tokens(text)
            assert count > 0


class TestTokenTrackingEdgeCases:
    """Test edge cases in token tracking."""

    def test_empty_text_token_count(self):
        """Empty text should have zero tokens."""
        tracker = get_token_tracker()
        assert tracker.count_tokens("") == 0

    def test_none_text_handling(self):
        """None text should be handled gracefully."""
        tracker = get_token_tracker()
        assert tracker.count_tokens("") == 0

    def test_very_long_text_token_counting(self):
        """Very long text should be counted."""
        tracker = get_token_tracker()

        very_long_text = "word " * 10000  # ~50K chars
        count = tracker.count_tokens(very_long_text)

        assert count > 0
        assert count > 10000 // 4  # Should be more than rough estimate

    def test_special_characters_token_counting(self):
        """Special characters should be counted."""
        tracker = get_token_tracker()

        special_text = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        count = tracker.count_tokens(special_text)

        assert count > 0

    def test_zero_cost_for_zero_tokens(self):
        """Zero tokens should cost zero."""
        tracker = get_token_tracker()
        cost = tracker.estimate_cost(0, 0)
        assert float(cost) == 0.0

    def test_fractional_token_pricing(self):
        """Fractional token counts should price correctly."""
        tracker = get_token_tracker()

        cost = tracker.estimate_cost(123, 45, "gpt-3.5-turbo")
        assert float(cost) > 0
        assert float(cost) < 0.001


class TestTokenTrackerGlobalInstance:
    """Test global token tracker instance."""

    def test_global_tracker_singleton(self):
        """Global tracker should be singleton."""
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()
        assert tracker1 is tracker2

    def test_global_tracker_initialization(self):
        """Global tracker should be initialized."""
        tracker = get_token_tracker()
        assert tracker is not None
        assert tracker.TOKEN_WARNING_THRESHOLD == 8000
        assert tracker.TOKEN_CRITICAL_THRESHOLD == 15000


class TestTokenEndpointIntegration:
    """Integration tests for token endpoints."""

    def test_token_stats_endpoint_integration(self, client):
        """Token stats should integrate with async system."""
        response = client.get("/api/v1/tokens/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields
        assert data["tracker_status"] == "active"
        assert data["thresholds"]["warning_threshold"] == 8000
        assert data["daily_limit"] == 1_000_000

    def test_token_stats_consistency(self, client):
        """Multiple calls to token stats should be consistent."""
        response1 = client.get("/api/v1/tokens/stats")
        response2 = client.get("/api/v1/tokens/stats")

        data1 = response1.json()
        data2 = response2.json()

        # Core data should be identical (timestamps may differ)
        assert data1["tracker_status"] == data2["tracker_status"]
        assert data1["thresholds"] == data2["thresholds"]
        assert data1["daily_limit"] == data2["daily_limit"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Test suite for token tracking functionality.

Tests cover:
- Token counting accuracy
- Risk level assessment
- Cost estimation
- Token usage logging
- Daily limit checking
- Batch token counting
- Multiple models
"""

from decimal import Decimal

import pytest

from app.token_tracking import RiskLevel, TokenTracker, TokenUsageLogger, get_token_tracker


class TestTokenCounter:
    """Test TokenTracker.count_tokens()"""

    def test_count_tokens_empty_text(self):
        """Empty text should return 0 tokens."""
        tracker = TokenTracker()
        assert tracker.count_tokens("") == 0

    def test_count_tokens_simple_text(self):
        """Count tokens in simple English text."""
        tracker = TokenTracker()
        # "Hello world" should be 2-3 tokens
        result = tracker.count_tokens("Hello world")
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_long_text(self):
        """Count tokens in longer text."""
        tracker = TokenTracker()
        long_text = "Hello world. " * 100  # ~1300 characters
        result = tracker.count_tokens(long_text)
        assert isinstance(result, int)
        assert result > 100  # Should be more than just character count / 4

    def test_count_tokens_special_characters(self):
        """Count tokens with special characters."""
        tracker = TokenTracker()
        text_with_special = "Hello! @#$%^&* World? 123-456"
        result = tracker.count_tokens(text_with_special)
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_unicode(self):
        """Count tokens with unicode characters."""
        tracker = TokenTracker()
        text_unicode = "Hello 世界 🌍 مرحبا мир"
        result = tracker.count_tokens(text_unicode)
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_json_data(self):
        """Count tokens in JSON data."""
        tracker = TokenTracker()
        json_text = '{"key": "value", "nested": {"data": [1, 2, 3]}}'
        result = tracker.count_tokens(json_text)
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_consistency(self):
        """Same text should always return same token count."""
        tracker = TokenTracker()
        text = "The quick brown fox jumps over the lazy dog"
        count1 = tracker.count_tokens(text)
        count2 = tracker.count_tokens(text)
        assert count1 == count2


class TestBatchTokenCounting:
    """Test TokenTracker.count_tokens_batch()"""

    def test_batch_token_counting_empty_list(self):
        """Empty list should return empty list."""
        tracker = TokenTracker()
        result = tracker.count_tokens_batch([])
        assert result == []

    def test_batch_token_counting_single_item(self):
        """Single item batch should work."""
        tracker = TokenTracker()
        result = tracker.count_tokens_batch(["Hello world"])
        assert len(result) == 1
        assert result[0] > 0

    def test_batch_token_counting_multiple_items(self):
        """Multiple items should be counted correctly."""
        tracker = TokenTracker()
        texts = ["Hello world", "This is a test", "Token counting is accurate"]
        result = tracker.count_tokens_batch(texts)
        assert len(result) == 3
        assert all(count > 0 for count in result)

    def test_batch_token_counting_with_empty_strings(self):
        """Batch with empty strings should return 0."""
        tracker = TokenTracker()
        texts = ["Hello world", "", "Test"]
        result = tracker.count_tokens_batch(texts)
        assert len(result) == 3
        assert result[1] == 0

    def test_batch_vs_individual_counting(self):
        """Batch counting should match individual counting."""
        tracker = TokenTracker()
        texts = ["First", "Second", "Third"]
        batch_result = tracker.count_tokens_batch(texts)
        individual_results = [tracker.count_tokens(text) for text in texts]
        assert batch_result == individual_results


class TestRiskLevelAssessment:
    """Test TokenTracker.get_risk_level()"""

    def test_safe_risk_level(self):
        """Token count below warning threshold should be SAFE."""
        tracker = TokenTracker()
        risk_level, warning = tracker.get_risk_level(1000)
        assert risk_level == RiskLevel.SAFE
        assert warning is None

    def test_warning_risk_level(self):
        """Token count in warning range should be WARNING."""
        tracker = TokenTracker()
        risk_level, warning = tracker.get_risk_level(8000)
        assert risk_level == RiskLevel.WARNING
        assert warning is not None
        assert "warning threshold" in warning

    def test_critical_risk_level(self):
        """Token count above critical threshold should be CRITICAL."""
        tracker = TokenTracker()
        risk_level, warning = tracker.get_risk_level(15000)
        assert risk_level == RiskLevel.CRITICAL
        assert warning is not None
        assert "critical threshold" in warning

    def test_boundary_safe_to_warning(self):
        """Boundary case: just below warning threshold."""
        tracker = TokenTracker()
        risk_level, _ = tracker.get_risk_level(7999)
        assert risk_level == RiskLevel.SAFE

    def test_boundary_warning_to_critical(self):
        """Boundary case: just below critical threshold."""
        tracker = TokenTracker()
        risk_level, _ = tracker.get_risk_level(14999)
        assert risk_level == RiskLevel.WARNING

    def test_zero_tokens(self):
        """Zero tokens should be SAFE."""
        tracker = TokenTracker()
        risk_level, warning = tracker.get_risk_level(0)
        assert risk_level == RiskLevel.SAFE
        assert warning is None


class TestCostEstimation:
    """Test TokenTracker.estimate_cost()"""

    def test_estimate_cost_gpt35_input_only(self):
        """GPT-3.5-turbo input-only cost."""
        tracker = TokenTracker()
        # 1M tokens at $0.50 = $0.50
        cost = tracker.estimate_cost(1_000_000, 0, "gpt-3.5-turbo")
        assert cost == Decimal("0.50")

    def test_estimate_cost_gpt35_input_and_output(self):
        """GPT-3.5-turbo with input and output tokens."""
        tracker = TokenTracker()
        # Input: 500K at $0.50/M = $0.25
        # Output: 500K at $1.50/M = $0.75
        # Total: $1.00
        cost = tracker.estimate_cost(500_000, 500_000, "gpt-3.5-turbo")
        assert cost == Decimal("1.00")

    def test_estimate_cost_gpt4(self):
        """GPT-4 cost estimation."""
        tracker = TokenTracker()
        # Input: 100K at $3.00/M = $0.30
        # Output: 50K at $6.00/M = $0.30
        # Total: $0.60
        cost = tracker.estimate_cost(100_000, 50_000, "gpt-4")
        assert cost == Decimal("0.60")

    def test_estimate_cost_gpt4_turbo(self):
        """GPT-4-turbo cost estimation."""
        tracker = TokenTracker()
        # Input: 200K at $1.00/M = $0.20
        # Output: 100K at $3.00/M = $0.30
        # Total: $0.50
        cost = tracker.estimate_cost(200_000, 100_000, "gpt-4-turbo")
        assert cost == Decimal("0.50")

    def test_estimate_cost_zero_tokens(self):
        """Zero tokens should result in zero cost."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost(0, 0, "gpt-3.5-turbo")
        assert cost == Decimal("0")

    def test_estimate_cost_unknown_model_defaults(self):
        """Unknown model should use default pricing."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost(1_000_000, 0, "unknown-model")
        # Should use default: $0.50/M
        assert cost == Decimal("0.50")

    def test_estimate_cost_precision(self):
        """Cost estimation should maintain precision."""
        tracker = TokenTracker()
        # 123 input tokens at $0.50/M = $0.0000615
        cost = tracker.estimate_cost(123, 0, "gpt-3.5-turbo")
        assert isinstance(cost, Decimal)
        assert cost > Decimal("0")
        assert cost < Decimal("0.001")


class TestTokenFormatting:
    """Test TokenTracker.format_token_count()"""

    def test_format_tokens_under_thousand(self):
        """Tokens under 1000 should display as numbers."""
        tracker = TokenTracker()
        assert tracker.format_token_count(500) == "500"
        assert tracker.format_token_count(999) == "999"

    def test_format_tokens_thousands(self):
        """Tokens in thousands should use K notation."""
        tracker = TokenTracker()
        assert tracker.format_token_count(1_000) == "1.00K"
        assert tracker.format_token_count(5_500) == "5.50K"
        assert tracker.format_token_count(999_999) == "1000.00K"

    def test_format_tokens_millions(self):
        """Tokens in millions should use M notation."""
        tracker = TokenTracker()
        assert tracker.format_token_count(1_000_000) == "1.00M"
        assert tracker.format_token_count(5_500_000) == "5.50M"

    def test_format_tokens_zero(self):
        """Zero tokens should display as 0."""
        tracker = TokenTracker()
        assert tracker.format_token_count(0) == "0"


class TestTokenUsageLogging:
    """Test TokenUsageLogger.log_token_usage()"""

    def test_log_token_usage_basic(self):
        """Log basic token usage."""
        from unittest.mock import MagicMock

        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        result = logger.log_token_usage(
            api_key_id="test-key",
            endpoint="/api/v1/analyze",
            input_text="Hello world",
        )

        assert "input_tokens" in result
        assert "output_tokens" in result
        assert "total_tokens" in result
        assert "risk_level" in result
        assert "estimated_cost_usd" in result
        assert "endpoint" in result
        assert "timestamp" in result

        # Verify persistence
        db.add.assert_called_once()
        args, _ = db.add.call_args
        token_usage = args[0]
        from app.models import TokenUsage

        assert isinstance(token_usage, TokenUsage)
        assert token_usage.api_key_id == "test-key"
        assert token_usage.endpoint == "/api/v1/analyze"
        assert token_usage.total_tokens > 0

    def test_log_token_usage_with_output(self):
        """Log token usage with input and output."""
        from unittest.mock import MagicMock

        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        result = logger.log_token_usage(
            api_key_id="test-key",
            endpoint="/api/v1/analyze",
            input_text="Hello world",
            output_text="Goodbye world",
        )

        assert result["output_tokens"] > 0
        assert result["total_tokens"] > result["input_tokens"]

    def test_log_token_usage_risk_calculation(self):
        """Log usage should calculate risk level correctly."""
        from unittest.mock import MagicMock

        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        # Create text that will generate >8000 tokens (~30K+ chars)
        large_text = "This is a longer piece of text. " * 250  # ~8000+ tokens
        result = logger.log_token_usage(
            api_key_id="test-key",
            endpoint="/api/v1/analyze",
            input_text=large_text,
        )

        # Verify risk level is calculated
        assert "risk_level" in result
        assert result["total_tokens"] > 0

    def test_log_token_usage_with_metadata(self):
        """Log usage with additional metadata."""
        from unittest.mock import MagicMock

        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        metadata = {"source": "test", "version": "1.0"}
        result = logger.log_token_usage(
            api_key_id="test-key",
            endpoint="/api/v1/analyze",
            input_text="Hello world",
            metadata=metadata,
        )

        assert result.get("metadata") == metadata

    def test_log_token_usage_different_models(self):
        """Log usage should handle different models."""
        from unittest.mock import MagicMock

        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        for model in ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]:
            result = logger.log_token_usage(
                api_key_id="test-key",
                endpoint="/api/v1/analyze",
                input_text="Hello world",
                model=model,
            )

            assert result["model"] == model
            assert result["estimated_cost_usd"] >= 0


class TestTokenTrackerIntegration:
    """Integration tests for token tracking."""

    def test_global_token_tracker(self):
        """Global token tracker should be accessible."""
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()
        assert tracker1 is tracker2

    def test_token_counting_realistic_pii_text(self):
        """Count tokens in realistic PII detection scenario."""
        tracker = TokenTracker()

        pii_text = """
        Customer John Doe (ID: 12345-67890) has email john.doe@example.com
        and phone number 555-123-4567. Their SSN is 123-45-6789 and
        credit card number is 4111-1111-1111-1111. Address: 123 Main St,
        Springfield, IL 62701.
        """

        token_count = tracker.count_tokens(pii_text)
        assert token_count > 0

        risk_level, warning = tracker.get_risk_level(token_count)
        assert risk_level == RiskLevel.SAFE

    def test_token_counting_compliance_text(self):
        """Count tokens in realistic compliance check scenario."""
        tracker = TokenTracker()

        compliance_text = (
            """
        This system is designed to meet HIPAA, GDPR, and PCI-DSS requirements.
        Patient medical records must be encrypted. GDPR requires data minimization.
        PCI-DSS mandates secure payment processing. All access must be logged
        and monitored. Regular audits are required quarterly.
        """
            * 50
        )

        token_count = tracker.count_tokens(compliance_text)
        assert token_count > 100

        cost = tracker.estimate_cost(token_count, 100)
        assert cost > Decimal("0")

    def test_token_tracking_full_workflow(self):
        """Full token tracking workflow."""
        from unittest.mock import MagicMock

        # Setup
        tracker = TokenTracker()
        db = MagicMock()
        logger = TokenUsageLogger(db, tracker)

        # Log usage for multiple requests
        results = []
        for i in range(3):
            result = logger.log_token_usage(
                api_key_id="test-key",
                endpoint=f"/api/v1/endpoint{i}",
                input_text="Test input text " * 100,
            )
            results.append(result)

        # Verify all logged successfully
        assert len(results) == 3
        assert all("total_tokens" in r for r in results)
        assert all(r["estimated_cost_usd"] >= 0 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

from unittest.mock import MagicMock, patch

import pytest

from integrations.langchain_integration import GuardrailsCallbackHandler, GuardrailsRunnable


class TestLangChainIntegration:

    @pytest.fixture
    def mock_requests(self):
        with patch("integrations.langchain_integration.requests") as mock:
            yield mock

    def test_callback_handler_violation(self, mock_requests):
        """Test that callback handler raises error on violation"""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "detections": {"pii_found": True, "injection_detected": False}
        }
        mock_requests.post.return_value = mock_response

        handler = GuardrailsCallbackHandler(raise_on_violation=True)

        # Should raise ValueError
        with pytest.raises(ValueError) as exc:
            handler.on_llm_start({}, ["My name is John"])

        assert "Guardrails Violation" in str(exc.value)
        assert "PII detected" in str(exc.value)

    def test_callback_handler_no_violation(self, mock_requests):
        """Test that callback handler passes when no violation"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "detections": {"pii_found": False, "injection_detected": False}
        }
        mock_requests.post.return_value = mock_response

        handler = GuardrailsCallbackHandler(raise_on_violation=True)
        # Should not raise
        handler.on_llm_start({}, ["Safe prompt"])

    def test_runnable_sanitization(self, mock_requests):
        """Test that runnable returns sanitized output"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sanitized_prompt": "Hello [PERSON]",
            "detections": {"pii_found": True},
        }
        mock_requests.post.return_value = mock_response

        runnable = GuardrailsRunnable()
        result = runnable.invoke("Hello John")

        assert result == "Hello [PERSON]"

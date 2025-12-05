"""
Test suite for webhook notification functionality.

Tests cover:
- Webhook URL validation
- Payload construction and validation
- Successful webhook delivery
- Retry logic and exponential backoff
- Timeout handling
- Error scenarios
- Delivery logging
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import httpx
import pytest

from app.webhooks import WebhookEventType, WebhookNotifier, WebhookPayload, get_webhook_notifier


class TestWebhookURLValidation:
    """Test webhook URL validation."""

    def test_valid_http_url(self):
        """Valid HTTP URL should pass."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("http://example.com/webhook")
        assert is_valid is True
        assert error is None

    def test_valid_https_url(self):
        """Valid HTTPS URL should pass."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("https://example.com/webhook")
        assert is_valid is True
        assert error is None

    def test_empty_url(self):
        """Empty URL should fail."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_invalid_scheme(self):
        """Invalid scheme should fail."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("ftp://example.com/webhook")
        assert is_valid is False
        assert "scheme" in error.lower()

    def test_missing_domain(self):
        """Missing domain should fail."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("http:///webhook")
        assert is_valid is False
        assert "domain" in error.lower() or "netloc" in error.lower()

    def test_none_url(self):
        """None URL should fail."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url(None)
        assert is_valid is False

    def test_url_with_query_params(self):
        """URL with query parameters should pass."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("https://example.com/webhook?key=value")
        assert is_valid is True
        assert error is None

    def test_url_with_port(self):
        """URL with custom port should pass."""
        notifier = WebhookNotifier()
        is_valid, error = notifier.validate_webhook_url("https://example.com:8080/webhook")
        assert is_valid is True
        assert error is None


class TestWebhookPayload:
    """Test webhook payload construction."""

    def test_build_task_event_basic(self):
        """Build basic task event payload."""
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="detect_pii_async",
            status="SUCCESS",
        )

        assert payload["event_type"] == "task.completed"
        assert payload["timestamp"] is not None
        assert payload["task"]["id"] == "task-123"
        assert payload["task"]["name"] == "detect_pii_async"
        assert payload["task"]["status"] == "SUCCESS"

    def test_build_task_event_with_result(self):
        """Build task event with result data."""
        result_data = {"entities_found": 5, "risk_level": "HIGH"}
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="detect_pii_async",
            status="SUCCESS",
            result=result_data,
        )

        assert "result" in payload
        assert payload["result"]["entities_found"] == 5
        assert payload["result"]["risk_level"] == "HIGH"

    def test_build_task_event_with_error(self):
        """Build task event with error."""
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_FAILED,
            task_id="task-123",
            task_name="detect_pii_async",
            status="FAILURE",
            error="Timeout after 30s",
        )

        assert "error" in payload
        assert payload["error"] == "Timeout after 30s"

    def test_build_task_event_with_metadata(self):
        """Build task event with custom metadata."""
        metadata = {"user_id": "user-456", "api_key_id": "key-789"}
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="detect_pii_async",
            status="SUCCESS",
            metadata=metadata,
        )

        assert "metadata" in payload
        assert payload["metadata"]["user_id"] == "user-456"

    def test_payload_has_timestamp(self):
        """Payload should include ISO format timestamp."""
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        timestamp = payload["timestamp"]
        # Verify it's valid ISO format
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_all_event_types(self):
        """All event types should build valid payloads."""
        for event_type in WebhookEventType:
            payload = WebhookPayload.build_task_event(
                event_type=event_type,
                task_id="task-123",
                task_name="test_task",
                status="PENDING",
            )
            assert payload["event_type"] == event_type.value


class TestPayloadValidation:
    """Test webhook payload validation."""

    def test_validate_valid_payload(self):
        """Valid payload should pass validation."""
        payload = {
            "event_type": "task.completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": {"id": "task-123", "status": "SUCCESS"},
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is True
        assert error is None

    def test_validate_missing_event_type(self):
        """Missing event_type should fail."""
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": {"id": "task-123", "status": "SUCCESS"},
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is False
        assert "event_type" in error

    def test_validate_missing_timestamp(self):
        """Missing timestamp should fail."""
        payload = {
            "event_type": "task.completed",
            "task": {"id": "task-123", "status": "SUCCESS"},
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is False
        assert "timestamp" in error

    def test_validate_missing_task(self):
        """Missing task should fail."""
        payload = {
            "event_type": "task.completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is False
        assert "task" in error

    def test_validate_task_missing_id(self):
        """Task missing id should fail."""
        payload = {
            "event_type": "task.completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": {"status": "SUCCESS"},
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is False
        assert "id" in error

    def test_validate_task_missing_status(self):
        """Task missing status should fail."""
        payload = {
            "event_type": "task.completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": {"id": "task-123"},
        }
        is_valid, error = WebhookPayload.validate_payload(payload)
        assert is_valid is False
        assert "status" in error


class TestWebhookDelivery:
    """Test webhook delivery."""

    @patch("app.webhooks.httpx.Client.post")
    def test_successful_webhook_delivery(self, mock_post):
        """Successful webhook delivery should return success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is True
        assert error is None
        assert attempt == 1

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_delivery_201_response(self, mock_post):
        """201 response should be treated as success."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is True

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_delivery_202_response(self, mock_post):
        """202 Accepted response should be treated as success."""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is True

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_delivery_timeout(self, mock_post):
        """Timeout should return failure after retries."""
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        notifier = WebhookNotifier(max_retries=1, retry_delay=0.01)
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is False
        assert "Timeout" in error
        assert attempt > 0

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_delivery_request_error(self, mock_post):
        """Request error should return failure."""
        mock_post.side_effect = httpx.RequestError("Connection refused")

        notifier = WebhookNotifier(max_retries=1, retry_delay=0.01)
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is False
        assert "Request failed" in error

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_delivery_invalid_url(self, mock_post):
        """Invalid URL should not attempt delivery."""
        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("invalid://url", payload)

        assert success is False
        assert "Invalid" in error
        assert mock_post.call_count == 0

    def test_webhook_delivery_invalid_payload(self):
        """Invalid payload should not attempt delivery."""
        notifier = WebhookNotifier()
        invalid_payload = {"invalid": "payload"}  # Missing required fields

        success, error, attempt = notifier.send_webhook(
            "https://example.com/webhook", invalid_payload
        )

        assert success is False
        assert error is not None
        assert ("Missing required field" in error) or ("Invalid" in error)

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_retry_on_500_error(self, mock_post):
        """500 error should trigger retries."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.side_effect = [mock_response, mock_response, Mock(status_code=200)]

        notifier = WebhookNotifier(max_retries=3, retry_delay=0.01)
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is True
        assert attempt == 3

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_no_retry_on_400_error(self, mock_post):
        """400 error should not trigger retries."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        notifier = WebhookNotifier(max_retries=3, retry_delay=0.01)
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        success, error, attempt = notifier.send_webhook("https://example.com/webhook", payload)

        assert success is False
        assert attempt == 1  # Only one attempt


class TestWebhookLogging:
    """Test webhook delivery logging."""

    def test_delivery_log_empty_initially(self):
        """Delivery log should be empty initially."""
        notifier = WebhookNotifier()
        log = notifier.get_delivery_log()
        assert log == []

    @patch("app.webhooks.httpx.Client.post")
    def test_delivery_log_records_success(self, mock_post):
        """Successful delivery should be logged."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        notifier.send_webhook("https://example.com/webhook", payload)

        log = notifier.get_delivery_log()
        assert len(log) == 1
        assert log[0]["success"] is True
        assert log[0]["url"] == "https://example.com/webhook"
        assert log[0]["event_type"] == "task.completed"

    @patch("app.webhooks.httpx.Client.post")
    def test_delivery_log_records_failure(self, mock_post):
        """Failed delivery should be logged."""
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        notifier = WebhookNotifier(max_retries=1, retry_delay=0.01)
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        notifier.send_webhook("https://example.com/webhook", payload)

        log = notifier.get_delivery_log()
        assert len(log) >= 1
        assert any(entry["success"] is False for entry in log)

    @patch("app.webhooks.httpx.Client.post")
    def test_clear_delivery_log(self, mock_post):
        """Delivery log should be clearable."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = WebhookNotifier()
        payload = WebhookPayload.build_task_event(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        notifier.send_webhook("https://example.com/webhook", payload)
        assert len(notifier.get_delivery_log()) > 0

        notifier.clear_delivery_log()
        assert len(notifier.get_delivery_log()) == 0


class TestWebhookConfiguration:
    """Test webhook notifier configuration."""

    def test_custom_timeout(self):
        """Custom timeout should be configurable."""
        notifier = WebhookNotifier(timeout=10.0)
        assert notifier.timeout == 10.0

    def test_custom_max_retries(self):
        """Custom max retries should be configurable."""
        notifier = WebhookNotifier(max_retries=5)
        assert notifier.max_retries == 5

    def test_custom_retry_delay(self):
        """Custom retry delay should be configurable."""
        notifier = WebhookNotifier(retry_delay=2.0)
        assert notifier.retry_delay == 2.0

    def test_default_configuration(self):
        """Default configuration should have reasonable values."""
        notifier = WebhookNotifier()
        assert notifier.timeout == WebhookNotifier.DEFAULT_TIMEOUT
        assert notifier.max_retries == WebhookNotifier.MAX_RETRIES
        assert notifier.retry_delay == WebhookNotifier.RETRY_DELAY


class TestWebhookGlobalInstance:
    """Test global webhook notifier instance."""

    def test_global_webhook_notifier_singleton(self):
        """Global instance should be singleton."""
        notifier1 = get_webhook_notifier()
        notifier2 = get_webhook_notifier()
        assert notifier1 is notifier2

    def test_global_webhook_notifier_initialized(self):
        """Global instance should be properly initialized."""
        notifier = get_webhook_notifier()
        assert isinstance(notifier, WebhookNotifier)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

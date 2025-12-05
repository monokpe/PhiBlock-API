"""
Integration tests for webhook notifications with async endpoints.

Tests cover:
- Webhook URL parameter acceptance in async endpoints
- Request model validation with webhook parameters
- Webhook parameter combinations with other options
"""


from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.async_endpoints import AsyncAnalysisRequest
from app.main import app


# Auto-mock Celery task submission used by the async endpoints to avoid
# requiring a running Redis/Celery broker during integration tests.
@pytest.fixture(autouse=True)
def mock_celery_task(monkeypatch):
    # Return a new mock task with a unique id on each .delay() call
    import uuid

    class MockAnalyze:
        def delay(self, *args, **kwargs):
            t = Mock()
            t.id = f"mock-task-{uuid.uuid4().hex[:8]}"
            return t

    mock_analyze = MockAnalyze()
    # Patch the analyze_complete_async used by async_endpoints
    monkeypatch.setattr("app.async_endpoints.analyze_complete_async", mock_analyze)
    yield


client = TestClient(app)


class TestWebhookParameterAcceptance:
    """Test webhook parameter acceptance in request models."""

    def test_async_analysis_request_model_with_webhook(self):
        """AsyncAnalysisRequest model should accept webhook_url parameter."""
        request = AsyncAnalysisRequest(
            text="My email is john@example.com",
            webhook_url="https://example.com/webhook",
        )

        assert request.text == "My email is john@example.com"
        assert request.webhook_url == "https://example.com/webhook"

    def test_async_analysis_request_model_without_webhook(self):
        """AsyncAnalysisRequest model should work without webhook_url."""
        request = AsyncAnalysisRequest(text="My email is john@example.com")

        assert request.text == "My email is john@example.com"
        assert request.webhook_url is None

    def test_async_analysis_request_webhook_url_optional(self):
        """webhook_url field should be optional."""
        request = AsyncAnalysisRequest(
            text="Test text",
            frameworks=["HIPAA"],
            webhook_url=None,
        )

        assert request.webhook_url is None

    def test_async_analysis_request_all_parameters_with_webhook(self):
        """All parameters should work together with webhook_url."""
        request = AsyncAnalysisRequest(
            text="My email is john@example.com",
            frameworks=["HIPAA", "GDPR"],
            include_redaction=True,
            redaction_strategy="hash",
            webhook_url="https://example.com/webhook",
        )

        assert request.webhook_url == "https://example.com/webhook"
        assert request.frameworks == ["HIPAA", "GDPR"]
        assert request.include_redaction is True
        assert request.redaction_strategy == "hash"

    def test_async_analysis_request_webhook_url_https(self):
        """HTTPS webhook URLs should be accepted."""
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url="https://secure.example.com:8443/webhook",
        )

        assert request.webhook_url == "https://secure.example.com:8443/webhook"

    def test_async_analysis_request_webhook_url_http(self):
        """HTTP webhook URLs should be accepted."""
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url="http://example.com:8080/webhook",
        )

        assert request.webhook_url == "http://example.com:8080/webhook"

    def test_async_analysis_request_webhook_url_with_query_params(self):
        """Webhook URLs with query parameters should be accepted."""
        url = "https://example.com/webhook?key=value&user_id=123"
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url=url,
        )

        assert request.webhook_url == url

    def test_async_analysis_request_webhook_url_with_path(self):
        """Webhook URLs with paths should be accepted."""
        url = "https://example.com/api/v1/webhooks/guardrails"
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url=url,
        )

        assert request.webhook_url == url

    def test_async_analysis_request_webhook_url_long(self):
        """Long webhook URLs should be accepted."""
        url = "https://example.com/webhook?" + "&".join([f"param{i}=value{i}" for i in range(20)])
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url=url,
        )

        assert request.webhook_url == url

    def test_async_analysis_request_text_validation_with_webhook(self):
        """Text field validation should work with webhook_url."""
        with pytest.raises(ValueError):
            AsyncAnalysisRequest(
                text="",  # Empty text should fail
                webhook_url="https://example.com/webhook",
            )

    def test_async_analysis_request_missing_text_with_webhook(self):
        """Text is required even when webhook_url is provided."""
        # Pydantic will raise a validation error when required fields are missing.
        with pytest.raises(Exception):
            AsyncAnalysisRequest(
                webhook_url="https://example.com/webhook",
                # Missing text
            )

    def test_async_analysis_request_json_serialization(self):
        """Request model should serialize to JSON properly."""
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url="https://example.com/webhook",
        )

        json_data = request.model_dump()
        assert json_data["text"] == "Test text"
        assert json_data["webhook_url"] == "https://example.com/webhook"

    def test_async_analysis_request_json_deserialization(self):
        """Request model should deserialize from JSON properly."""
        json_data = {
            "text": "Test text",
            "webhook_url": "https://example.com/webhook",
            "frameworks": ["HIPAA"],
        }

        request = AsyncAnalysisRequest(**json_data)
        assert request.text == "Test text"
        assert request.webhook_url == "https://example.com/webhook"
        assert request.frameworks == ["HIPAA"]


class TestWebhookHelperFunction:
    """Test webhook notification helper function."""

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_helper_with_valid_url_and_payload(self, mock_post):
        """Helper function should send webhook with valid URL and payload."""
        from app.async_endpoints import _send_webhook_notification

        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Should not raise any exception
        _send_webhook_notification(
            webhook_url="https://example.com/webhook",
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

    def test_webhook_helper_with_none_url(self):
        """Helper function should handle None webhook URL gracefully."""
        from app.async_endpoints import _send_webhook_notification

        # Should not raise any exception
        _send_webhook_notification(
            webhook_url=None,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

    def test_webhook_helper_with_empty_url(self):
        """Helper function should handle empty webhook URL gracefully."""
        from app.async_endpoints import _send_webhook_notification

        # Should not raise any exception
        _send_webhook_notification(
            webhook_url="",
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_helper_with_result_data(self, mock_post):
        """Helper function should include result data in payload."""
        from app.async_endpoints import _send_webhook_notification

        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result_data = {"entities_found": 5, "risk_level": "HIGH"}

        _send_webhook_notification(
            webhook_url="https://example.com/webhook",
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
            result=result_data,
        )

    @patch("app.webhooks.httpx.Client.post")
    def test_webhook_helper_with_error(self, mock_post):
        """Helper function should include error message in payload."""
        from app.async_endpoints import _send_webhook_notification

        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        _send_webhook_notification(
            webhook_url="https://example.com/webhook",
            task_id="task-123",
            task_name="test_task",
            status="FAILURE",
            error="Task timeout after 30 seconds",
        )


class TestWebhookEndpointSchema:
    """Test that async endpoints have correct schema with webhook_url."""

    def test_analyze_async_endpoint_accepts_webhook_url_in_schema(self):
        """POST /api/v1/analyze/async should have webhook_url in schema."""
        # This tests the OpenAPI schema
        response = client.get("/openapi.json")

        if response.status_code == 200:
            schema = response.json()
            # Check that schema exists (endpoint is registered)
            assert "paths" in schema

    def test_webhook_parameter_not_breaking_other_parameters(self):
        """webhook_url parameter should not interfere with other parameters."""
        request = AsyncAnalysisRequest(
            text="Test text",
            frameworks=["HIPAA", "GDPR", "PCI_DSS"],
            include_redaction=False,
            redaction_strategy="partial",
            webhook_url="https://example.com/webhook",
        )

        assert request.frameworks == ["HIPAA", "GDPR", "PCI_DSS"]
        assert request.include_redaction is False
        assert request.redaction_strategy == "partial"
        assert request.webhook_url == "https://example.com/webhook"

    def test_request_model_backward_compatibility(self):
        """Request model should be backward compatible without webhook_url."""
        # Old code that doesn't use webhook_url should still work
        request = AsyncAnalysisRequest(text="Test text")

        assert request.text == "Test text"
        assert request.webhook_url is None  # Default to None
        assert request.include_redaction is True  # Other defaults work
        assert request.redaction_strategy == "token"  # Other defaults work


class TestWebhookParameterValidation:
    """Test webhook parameter validation."""

    def test_webhook_url_none_is_valid(self):
        """None should be valid for webhook_url."""
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url=None,
        )

        assert request.webhook_url is None

    def test_webhook_url_string_is_stored(self):
        """String webhook_url should be stored as-is."""
        url = "https://example.com/webhook"
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url=url,
        )

        assert request.webhook_url == url
        assert isinstance(request.webhook_url, str)

    def test_webhook_url_in_json_dump(self):
        """webhook_url should be included in model dump."""
        request = AsyncAnalysisRequest(
            text="Test text",
            webhook_url="https://example.com/webhook",
        )

        dump = request.model_dump()
        assert "webhook_url" in dump
        assert dump["webhook_url"] == "https://example.com/webhook"

    def test_webhook_url_in_json_schema(self):
        """webhook_url should be in JSON schema."""
        schema = AsyncAnalysisRequest.model_json_schema()

        assert "properties" in schema
        assert "webhook_url" in schema["properties"]
        # schema shapes may vary by pydantic version; ensure type is a string when present
        prop = schema["properties"]["webhook_url"]
        assert isinstance(prop, dict)
        assert prop.get("type") in ("string", None) or "$ref" in prop

    def test_webhook_url_schema_is_optional(self):
        """webhook_url should be marked as optional in schema."""
        schema = AsyncAnalysisRequest.model_json_schema()

        # webhook_url should not be in required fields (or should be optional)
        required_fields = schema.get("required", [])
        # text should be required
        assert "text" in required_fields
        # webhook_url should not be required
        assert "webhook_url" not in required_fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestWebhookIntegrationWithAsyncEndpoints:
    """Test webhook integration with async endpoints."""

    @patch("app.webhooks.get_webhook_notifier")
    def test_analyze_async_with_webhook_url(self, mock_get_notifier):
        """Async analysis endpoint should accept webhook_url parameter."""
        # Mock notifier so HTTP calls aren't made and TestClient internals are unaffected
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (True, None, 1)
        mock_get_notifier.return_value = mock_notifier

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://example.com/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] in ["PENDING", "STARTED"]

    def test_analyze_async_without_webhook_url(self):
        """Async analysis should work without webhook_url."""
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "My email is john@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] in ["PENDING", "STARTED"]

    @patch("app.webhooks.get_webhook_notifier")
    def test_analyze_async_webhook_url_validation(self, mock_get_notifier):
        """Invalid webhook URL should be rejected gracefully."""
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (False, "Invalid URL", 0)
        mock_get_notifier.return_value = mock_notifier

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "invalid://url",
            },
        )

        # Should still accept the request (webhook validation happens later)
        assert response.status_code == 200

    def test_analyze_async_webhook_url_optional(self):
        """Webhook URL should be optional in request."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                # No webhook_url
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_analyze_async_webhook_url_with_query_params(self):
        """Webhook URL with query parameters should be accepted."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://example.com/webhook?key=value&user=123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    @patch("app.webhooks.get_webhook_notifier")
    def test_webhook_notification_on_task_submission(self, mock_get_notifier):
        """Webhook notification task should be scheduled on submission."""
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (True, None, 1)
        mock_get_notifier.return_value = mock_notifier

        with patch("app.async_endpoints._send_webhook_notification") as mock_send:
            response = client.post(
                "/api/v1/analyze/async",
                json={
                    "text": "My email is john@example.com",
                    "webhook_url": "https://example.com/webhook",
                },
            )

            assert response.status_code == 200
            mock_send.assert_called_once()

    def test_multiple_async_requests_with_different_webhooks(self):
        """Multiple requests with different webhooks should each track separately."""
        webhook1 = "https://example1.com/webhook"
        webhook2 = "https://example2.com/webhook"

        response1 = client.post(
            "/api/v1/analyze/async",
            json={"text": "Email: john@example.com", "webhook_url": webhook1},
        )

        response2 = client.post(
            "/api/v1/analyze/async",
            json={"text": "Email: jane@example.com", "webhook_url": webhook2},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        assert data1["task_id"] != data2["task_id"]

    def test_analyze_async_request_model_validation(self):
        """Request model should validate all fields."""
        # Valid request
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "Valid text",
                "webhook_url": "https://example.com/webhook",
                "frameworks": ["HIPAA", "GDPR"],
                "include_redaction": True,
                "redaction_strategy": "token",
            },
        )

        assert response.status_code == 200

    def test_analyze_async_empty_text_rejected(self):
        """Empty text should be rejected."""
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "", "webhook_url": "https://example.com/webhook"},
        )

        assert response.status_code == 422  # Validation error

    def test_analyze_async_missing_text_rejected(self):
        """Missing required text field should be rejected."""
        response = client.post(
            "/api/v1/analyze/async",
            json={"webhook_url": "https://example.com/webhook"},
        )

        assert response.status_code == 422  # Validation error

    @patch("app.webhooks.get_webhook_notifier")
    def test_webhook_url_with_https(self, mock_get_notifier):
        """HTTPS webhook URLs should be accepted."""
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (True, None, 1)
        mock_get_notifier.return_value = mock_notifier

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://secure.example.com:8443/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    @patch("app.webhooks.get_webhook_notifier")
    def test_webhook_url_with_http(self, mock_get_notifier):
        """HTTP webhook URLs should be accepted."""
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (True, None, 1)
        mock_get_notifier.return_value = mock_notifier

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "http://example.com:8080/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_webhook_url_with_special_characters(self):
        """Webhook URL with special characters (valid in URLs) should be accepted."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://example.com/webhook?key=value&user_id=123-456&env=prod",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_response_includes_task_metadata(self):
        """Response should include all required task metadata."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://example.com/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "task_id" in data
        assert "status" in data
        assert "submitted_at" in data
        assert "message" in data

        # Status should be PENDING or STARTED
        assert data["status"] in ["PENDING", "STARTED"]

    @patch("app.webhooks.get_webhook_notifier")
    def test_webhook_url_none_is_handled(self, mock_get_notifier):
        """Explicit None for webhook_url should be handled gracefully."""
        mock_notifier = Mock()
        mock_notifier.send_webhook.return_value = (True, None, 1)
        mock_get_notifier.return_value = mock_notifier

        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "My email is john@example.com", "webhook_url": None},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_long_webhook_url_accepted(self):
        """Long webhook URLs should be accepted."""
        long_url = "https://example.com/webhook?" + "&".join(
            [f"param{i}=value{i}" for i in range(20)]
        )

        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "My email is john@example.com", "webhook_url": long_url},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_analyze_async_response_format_consistency(self):
        """Response format should be consistent with or without webhook_url."""
        response_with = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "webhook_url": "https://example.com/webhook",
            },
        )

        response_without = client.post(
            "/api/v1/analyze/async",
            json={"text": "My email is john@example.com"},
        )

        assert response_with.status_code == 200
        assert response_without.status_code == 200

        data_with = response_with.json()
        data_without = response_without.json()

        # Both should have the same keys
        assert set(data_with.keys()) == set(data_without.keys())

        # Status should be same type in both
        assert type(data_with["status"]) is type(data_without["status"])

    def test_analyze_async_frameworks_parameter_with_webhook(self):
        """Frameworks parameter should work together with webhook_url."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "frameworks": ["HIPAA", "GDPR"],
                "webhook_url": "https://example.com/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_analyze_async_redaction_strategy_with_webhook(self):
        """Redaction strategy parameter should work with webhook_url."""
        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "My email is john@example.com",
                "redaction_strategy": "hash",
                "webhook_url": "https://example.com/webhook",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    @patch("app.webhooks.get_webhook_notifier")
    def test_webhook_helper_function_handles_missing_url(self, mock_get_notifier):
        """Helper function should handle None webhook URL gracefully."""
        from app.async_endpoints import _send_webhook_notification

        # Ensure notifier is mocked so no HTTP calls are made
        mock_notifier = Mock()
        mock_get_notifier.return_value = mock_notifier

        # Should not raise any exception
        _send_webhook_notification(
            webhook_url=None,
            task_id="task-123",
            task_name="test_task",
            status="SUCCESS",
        )

        # Should not attempt any HTTP calls
        assert mock_notifier.send_webhook.call_count == 0


class TestWebhookEndpointAvailability:
    """Test that webhook-related endpoints are available."""

    def test_analyze_async_endpoint_exists(self):
        """POST /api/v1/analyze/async should exist."""
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "test@example.com"},
        )

        # Should not return 404
        assert response.status_code != 404

    def test_task_status_endpoint_exists(self):
        """GET /api/v1/tasks/{task_id} should exist."""
        # First submit a task
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "test@example.com"},
        )

        if response.status_code == 200:
            task_id = response.json()["task_id"]

            # Try to get status
            status_response = client.get(f"/api/v1/tasks/{task_id}")

            # Should not return 404
            assert status_response.status_code != 404

    def test_task_result_endpoint_exists(self):
        """GET /api/v1/tasks/{task_id}/result should exist."""
        # First submit a task
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "test@example.com"},
        )

        if response.status_code == 200:
            task_id = response.json()["task_id"]

            # Try to get result
            result_response = client.get(f"/api/v1/tasks/{task_id}/result")

            # Should not return 404
            assert result_response.status_code != 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Integration tests for async endpoints.

Tests cover:
- Async task submission
- Task status checking
- Result retrieval
- Endpoint error handling
- Request validation
- Response formats
"""

from datetime import datetime
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.async_endpoints import (
    AsyncAnalysisRequest,
    AsyncTaskResponse,
    TaskStatusResponse,
)
from app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class TestAsyncEndpointsAvailable:
    """Test that async endpoints are available in the API"""

    def test_async_analysis_endpoint_exists(self, client):
        """Test POST /api/v1/analyze/async endpoint exists"""
        # This should return 422 due to missing required body, not 404
        response = client.post("/api/v1/analyze/async")
        assert response.status_code in [422, 400]  # Validation error, not 404

    def test_pii_detection_async_endpoint_exists(self, client):
        """Test POST /api/v1/detect/pii/async endpoint exists"""
        response = client.post("/api/v1/detect/pii/async")
        assert response.status_code in [422, 400]  # Query param required

    def test_compliance_check_async_endpoint_exists(self, client):
        """Test POST /api/v1/compliance/check/async endpoint exists"""
        response = client.post("/api/v1/compliance/check/async")
        assert response.status_code in [422, 400]  # Query param required

    def test_redact_async_endpoint_exists(self, client):
        """Test POST /api/v1/redact/async endpoint exists"""
        response = client.post("/api/v1/redact/async")
        assert response.status_code in [422, 400]  # Query param required

    def test_task_status_endpoint_exists(self, client):
        """Test GET /api/v1/tasks/{task_id} endpoint exists"""
        response = client.get("/api/v1/tasks/dummy_id")
        # Should return actual status, not 404
        assert response.status_code in [200, 400, 500]

    def test_task_result_endpoint_exists(self, client):
        """Test GET /api/v1/tasks/{task_id}/result endpoint exists"""
        response = client.get("/api/v1/tasks/dummy_id/result")
        # Should return actual result or error, not 404
        assert response.status_code in [200, 400, 500, 202]

    def test_task_cancel_endpoint_exists(self, client):
        """Test DELETE /api/v1/tasks/{task_id} endpoint exists"""
        response = client.delete("/api/v1/tasks/dummy_id")
        # Should attempt cancellation, not 404
        assert response.status_code in [200, 400, 500]

    def test_pending_tasks_endpoint_exists(self, client):
        """Test GET /api/v1/tasks/stats/pending endpoint exists"""
        response = client.get("/api/v1/tasks/stats/pending")
        assert response.status_code in [200, 500]  # Should exist

    def test_worker_stats_endpoint_exists(self, client):
        """Test GET /api/v1/tasks/workers endpoint exists"""
        response = client.get("/api/v1/tasks/workers")
        assert response.status_code in [200, 500]  # Should exist


class TestAsyncAnalysisSubmission:
    """Test async analysis task submission"""

    @patch("app.async_endpoints.analyze_complete_async")
    def test_submit_analysis_task(self, mock_task, client):
        """Test submitting analysis task"""
        mock_task.delay.return_value = MagicMock(id="task_123")

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "John Doe lives in NYC",
                "frameworks": ["HIPAA"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert data["status"] == "PENDING"
        assert "submitted_at" in data

    @patch("app.async_endpoints.analyze_complete_async")
    def test_submit_analysis_with_defaults(self, mock_task, client):
        """Test analysis submission with default parameters"""
        mock_task.delay.return_value = MagicMock(id="task_456")

        response = client.post("/api/v1/analyze/async", json={"text": "Test text"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_456"

    def test_submit_analysis_validation_min_length(self, client):
        """Test text minimum length validation"""
        response = client.post("/api/v1/analyze/async", json={"text": ""})  # Empty string

        assert response.status_code == 422  # Validation error

    def test_submit_analysis_validation_max_length(self, client):
        """Test text maximum length validation"""
        long_text = "x" * 60001  # Over max 50000

        response = client.post("/api/v1/analyze/async", json={"text": long_text})

        assert response.status_code == 422  # Validation error

    @patch("app.async_endpoints.analyze_complete_async")
    def test_submit_analysis_invalid_framework(self, mock_task, client):
        """Test with invalid framework parameter"""
        mock_task.delay.return_value = MagicMock(id="task_789")

        # Should still accept, framework validation happens in task
        response = client.post(
            "/api/v1/analyze/async",
            json={"text": "Test text", "frameworks": ["INVALID"]},
        )

        assert response.status_code == 200


class TestPIIDetectionAsyncSubmission:
    """Test async PII detection submission"""

    @patch("app.async_endpoints.detect_pii_async")
    def test_submit_pii_detection(self, mock_task, client):
        """Test submitting PII detection task"""
        mock_task.delay.return_value = MagicMock(id="pii_task_1")

        response = client.post(
            "/api/v1/detect/pii/async", params={"text": "John Doe's SSN is 123-45-6789"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "pii_task_1"
        assert data["status"] == "PENDING"

    def test_submit_pii_missing_text(self, client):
        """Test missing required text parameter"""
        response = client.post("/api/v1/detect/pii/async")
        assert response.status_code == 422

    @patch("app.async_endpoints.detect_pii_async")
    def test_submit_pii_max_length(self, mock_task, client):
        """Test PII detection max length"""
        mock_task.delay.return_value = MagicMock(id="pii_task_2")

        long_text = "x" * 50000  # At max

        response = client.post("/api/v1/detect/pii/async", params={"text": long_text})

        assert response.status_code == 200


class TestComplianceCheckAsyncSubmission:
    """Test async compliance checking submission"""

    @patch("app.async_endpoints.check_compliance_async")
    def test_submit_compliance_check(self, mock_task, client):
        """Test submitting compliance check task"""
        mock_task.delay.return_value = MagicMock(id="compliance_task_1")

        response = client.post(
            "/api/v1/compliance/check/async",
            params={"text": "Patient SSN: 123-45-6789"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "compliance_task_1"

    @patch("app.async_endpoints.check_compliance_async")
    def test_submit_compliance_with_frameworks(self, mock_task, client):
        """Test compliance check with specific frameworks"""
        mock_task.delay.return_value = MagicMock(id="compliance_task_2")

        response = client.post(
            "/api/v1/compliance/check/async",
            params={"text": "Test text", "frameworks": ["HIPAA", "GDPR"]},
        )

        assert response.status_code == 200
        mock_task.delay.assert_called_once()


class TestRedactionAsyncSubmission:
    """Test async redaction submission"""

    @patch("app.async_endpoints.redact_async")
    def test_submit_redaction(self, mock_task, client):
        """Test submitting redaction task"""
        mock_task.delay.return_value = MagicMock(id="redact_task_1")

        response = client.post("/api/v1/redact/async", params={"text": "John Doe lives in NYC"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "redact_task_1"

    @patch("app.async_endpoints.redact_async")
    def test_submit_redaction_with_strategy(self, mock_task, client):
        """Test redaction with specific strategy"""
        mock_task.delay.return_value = MagicMock(id="redact_task_2")

        response = client.post(
            "/api/v1/redact/async", params={"text": "Test text", "strategy": "token"}
        )

        assert response.status_code == 200
        call_args = mock_task.delay.call_args
        assert call_args is not None


class TestTaskStatusEndpoint:
    """Test task status retrieval endpoint"""

    @patch("app.async_endpoints.get_task_result")
    def test_get_pending_task_status(self, mock_get, client):
        """Test getting status of pending task"""
        mock_get.return_value = {"status": "pending", "task_id": "task_123"}

        response = client.get("/api/v1/tasks/task_123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["task_id"] == "task_123"

    @patch("app.async_endpoints.get_task_result")
    def test_get_completed_task_status(self, mock_get, client):
        """Test getting status of completed task"""
        mock_get.return_value = {"status": "success", "result": {"entities": []}}

        response = client.get("/api/v1/tasks/task_456")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "result" in data

    @patch("app.async_endpoints.get_task_result")
    def test_get_failed_task_status(self, mock_get, client):
        """Test getting status of failed task"""
        mock_get.return_value = {"status": "error", "error": "Task failed"}

        response = client.get("/api/v1/tasks/task_789")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "error" in data


class TestTaskResultEndpoint:
    """Test task result retrieval endpoint"""

    @patch("app.async_endpoints.get_task_result")
    def test_get_completed_result(self, mock_get, client):
        """Test getting result of completed task"""
        expected_result = {
            "status": "success",
            "entities": [{"type": "PERSON", "value": "John"}],
        }
        mock_get.return_value = {"status": "success", "result": expected_result}

        response = client.get("/api/v1/tasks/task_123/result")

        assert response.status_code == 200
        data = response.json()
        assert "entities" in data

    @patch("app.async_endpoints.get_task_result")
    def test_get_pending_result_returns_202(self, mock_get, client):
        """Test getting result of pending task returns 202"""
        mock_get.return_value = {"status": "pending", "task_id": "task_456"}

        response = client.get("/api/v1/tasks/task_456/result")

        # Should return 202 Accepted (still processing)
        assert response.status_code == 202

    @patch("app.async_endpoints.get_task_result")
    def test_get_failed_result_returns_error(self, mock_get, client):
        """Test getting result of failed task returns error"""
        mock_get.return_value = {"status": "error", "error": "Task execution failed"}

        response = client.get("/api/v1/tasks/task_789/result")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data


class TestTaskCancellation:
    """Test task cancellation"""

    @patch("app.async_endpoints.AsyncResult")
    def test_cancel_task(self, mock_async_result_cls, client):
        """Test cancelling a task"""
        mock_task_instance = MagicMock()
        mock_async_result_cls.return_value = mock_task_instance

        response = client.delete("/api/v1/tasks/task_123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["task_id"] == "task_123"

    @patch("app.async_endpoints.AsyncResult")
    def test_cancel_nonexistent_task(self, mock_async_result_cls, client):
        """Test cancelling non-existent task"""
        mock_task_instance = MagicMock()
        mock_async_result_cls.return_value = mock_task_instance

        response = client.delete("/api/v1/tasks/nonexistent")

        # Should still return success (task just wasn't found, nothing to cancel)
        assert response.status_code == 200


class TestPendingTasksStats:
    """Test pending tasks statistics endpoint"""

    @patch("app.async_endpoints.app.control.inspect")
    def test_get_pending_tasks_stats(self, mock_inspect, client):
        """Test getting pending tasks statistics"""
        mock_inspect_instance = MagicMock()
        mock_inspect_instance.active.return_value = {
            "worker1": [{"id": "task_1"}, {"id": "task_2"}],
            "worker2": [{"id": "task_3"}],
        }
        mock_inspect.return_value = mock_inspect_instance

        response = client.get("/api/v1/tasks/stats/pending")

        assert response.status_code == 200
        data = response.json()
        assert "pending_count" in data
        assert data["pending_count"] >= 0

    @patch("app.async_endpoints.app.control.inspect")
    def test_get_pending_tasks_no_workers(self, mock_inspect, client):
        """Test pending stats when no workers running"""
        mock_inspect_instance = MagicMock()
        mock_inspect_instance.active.return_value = None
        mock_inspect.return_value = mock_inspect_instance

        response = client.get("/api/v1/tasks/stats/pending")

        assert response.status_code == 200
        data = response.json()
        assert data["pending_count"] == 0


class TestWorkerStats:
    """Test worker statistics endpoint"""

    def test_get_worker_stats(self, client):
        """Test getting worker statistics"""
        # Note: This endpoint requires active Redis connection and workers
        # In testing without actual workers running, we just verify the endpoint responds
        response = client.get("/api/v1/tasks/workers")

        # Should return 200 with either stats or error message
        assert response.status_code == 200
        data = response.json()
        # Either has workers or has error message
        assert "error" in data or "workers" in data

    def test_get_worker_stats_response_format(self, client):
        """Test worker stats response format when no workers"""
        response = client.get("/api/v1/tasks/workers")

        assert response.status_code == 200
        data = response.json()
        # Should be a dict with status info
        assert isinstance(data, dict)


class TestRequestValidation:
    """Test request validation"""

    def test_analyze_request_validation_no_text(self, client):
        """Test analysis request requires text"""
        response = client.post("/api/v1/analyze/async", json={"frameworks": ["HIPAA"]})

        assert response.status_code == 422

    def test_analyze_request_validation_invalid_type(self, client):
        """Test analysis request text must be string"""
        response = client.post("/api/v1/analyze/async", json={"text": 123})

        assert response.status_code == 422

    @patch("app.async_endpoints.analyze_complete_async")
    def test_analyze_request_optional_frameworks(self, mock_task, client):
        """Test frameworks parameter is optional"""
        mock_task.delay.return_value = MagicMock(id="task_123")

        response = client.post("/api/v1/analyze/async", json={"text": "Test"})

        assert response.status_code == 200

    @patch("app.async_endpoints.analyze_complete_async")
    def test_analyze_request_optional_redaction(self, mock_task, client):
        """Test redaction parameters are optional"""
        mock_task.delay.return_value = MagicMock(id="task_123")

        response = client.post(
            "/api/v1/analyze/async",
            json={
                "text": "Test",
                "include_redaction": False,
                "redaction_strategy": "mask",
            },
        )

        assert response.status_code == 200


class TestResponseFormats:
    """Test response formats"""

    @patch("app.async_endpoints.analyze_complete_async")
    def test_task_submission_response_format(self, mock_task, client):
        """Test task submission response has correct format"""
        mock_task.delay.return_value = MagicMock(id="task_123")

        response = client.post("/api/v1/analyze/async", json={"text": "Test text"})

        assert response.status_code == 200
        data = response.json()

        # Check all required fields present
        assert "task_id" in data
        assert "status" in data
        assert "submitted_at" in data
        assert "message" in data

        # Check types
        assert isinstance(data["task_id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["submitted_at"], str)  # ISO format

    @patch("app.async_endpoints.get_task_result")
    def test_task_status_response_format(self, mock_get, client):
        """Test task status response has correct format"""
        mock_get.return_value = {
            "status": "success",
            "result": {"status": "success", "entities": []},
        }

        response = client.get("/api/v1/tasks/task_123")

        assert response.status_code == 200
        data = response.json()

        # Check all required fields present
        assert "task_id" in data
        assert "status" in data
        assert "submitted_at" in data


class TestErrorHandling:
    """Test error handling in endpoints"""

    @patch("app.async_endpoints.analyze_complete_async")
    def test_task_submission_error(self, mock_task, client):
        """Test error during task submission"""
        mock_task.delay.side_effect = Exception("Redis connection failed")

        response = client.post("/api/v1/analyze/async", json={"text": "Test text"})

        # Should return 500
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    @patch("app.async_endpoints.get_task_result")
    def test_task_result_retrieval_error(self, mock_get, client):
        """Test error during result retrieval"""
        mock_get.side_effect = Exception("Database error")

        response = client.get("/api/v1/tasks/task_123")

        # Should return 500
        assert response.status_code == 500

    @patch("app.async_endpoints.app.control.inspect")
    def test_stats_retrieval_error(self, mock_inspect, client):
        """Test error getting stats"""
        mock_inspect.side_effect = Exception("Inspection failed")

        response = client.get("/api/v1/tasks/stats/pending")

        # Should gracefully return empty stats
        assert response.status_code in [200, 500]


class TestHTTPStatusCodes:
    """Test correct HTTP status codes"""

    @patch("app.async_endpoints.analyze_complete_async")
    def test_task_submission_returns_200(self, mock_task, client):
        """Test task submission returns 200"""
        mock_task.delay.return_value = MagicMock(id="task_123")

        response = client.post("/api/v1/analyze/async", json={"text": "Test"})

        assert response.status_code == 200

    @patch("app.async_endpoints.get_task_result")
    def test_pending_result_returns_202(self, mock_get, client):
        """Test pending result returns 202"""
        mock_get.return_value = {"status": "pending", "task_id": "task_123"}

        response = client.get("/api/v1/tasks/task_123/result")

        assert response.status_code == 202

    def test_invalid_request_returns_422(self, client):
        """Test invalid request returns 422"""
        response = client.post("/api/v1/analyze/async", json={"invalid_field": "value"})

        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

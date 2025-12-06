"""
Webhook Notifications Module

Handles callback notifications for task completion events.
Implements retry logic, error handling, and audit logging.

Features:
- HTTP POST to webhook URLs
- Retry logic with exponential backoff
- Timeout handling
- Error logging and recovery
- Webhook payload validation
- Event type support
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from . import webhook_security

logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Supported webhook event types."""

    TASK_SUBMITTED = "task.submitted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"


class WebhookStatus(str, Enum):
    """Webhook delivery status."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookPayload:
    """
    Webhook payload builder.
    """

    @staticmethod
    def build_task_event(
        event_type: WebhookEventType,
        task_id: str,
        task_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build task event webhook payload.
        """
        payload = {
            "event_type": event_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": {
                "id": task_id,
                "name": task_name,
                "status": status,
            },
        }

        if result:
            payload["result"] = result

        if error:
            payload["error"] = error

        if metadata:
            payload["metadata"] = metadata

        return payload

    @staticmethod
    def validate_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate webhook payload structure.

        Args:
            payload: Payload to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["event_type", "timestamp", "task"]

        for field in required_fields:
            if field not in payload:
                return (False, f"Missing required field: {field}")

        if "id" not in payload["task"] or "status" not in payload["task"]:
            return (False, "Task must have 'id' and 'status' fields")

        return (True, None)


class WebhookNotifier:
    """
    Sends HTTP webhook notifications for task events.
    """

    DEFAULT_TIMEOUT = 5.0
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    RETRY_BACKOFF = 2
    DEFAULT_HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Guardrails-Webhook/1.0",
    }

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        retry_delay: float = RETRY_DELAY,
    ):
        """
        Initialize WebhookNotifier.
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.delivery_log: List[Dict[str, Any]] = []

    def validate_webhook_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate webhook URL format.

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return (False, "Webhook URL cannot be empty")

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return (
                    False,
                    f"Invalid scheme: {parsed.scheme}. Must be http or https.",
                )
            if not parsed.netloc:
                return (False, "Invalid URL: missing domain/netloc")
            return (True, None)
        except Exception as e:
            return (False, f"URL validation error: {str(e)}")

    def send_webhook(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        event_type: WebhookEventType = WebhookEventType.TASK_COMPLETED,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, Optional[str], int]:
        """
        Send webhook notification with retry logic.
        """
        is_valid, error = self.validate_webhook_url(webhook_url)
        if not is_valid:
            logger.error(f"Invalid webhook URL: {error}")
            return (False, error, 0)

        is_valid, error = WebhookPayload.validate_payload(payload)
        if not is_valid:
            logger.error(f"Invalid webhook payload: {error}")
            return (False, error, 0)

        try:
            if not webhook_security.is_allowed_webhook(webhook_url):
                err = "Webhook destination not allowed by server allowlist"
                logger.error(err)
                self._log_delivery(webhook_url, event_type, False, err, 0)
                return (False, err, 0)
        except Exception:
            logger.exception("Allowlist check failed; rejecting webhook")
            err = "Allowlist check error"
            self._log_delivery(webhook_url, event_type, False, err, 0)
            return (False, err, 0)

        try:
            if webhook_security.is_rate_limited(webhook_url):
                err = "Rate limit exceeded for webhook destination"
                logger.warning(err)
                self._log_delivery(webhook_url, event_type, False, err, 0)
                return (False, err, 0)
        except Exception:
            logger.exception("Rate limit check encountered an error; failing open")

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._post_webhook(webhook_url, payload, extra_headers=extra_headers)

                if response.status_code in (200, 201, 202, 204):
                    logger.info(
                        f"Webhook delivered successfully: {webhook_url} "
                        f"(attempt {attempt}, status {response.status_code})"
                    )
                    self._log_delivery(webhook_url, event_type, True, None, attempt)
                    return (True, None, attempt)

                if attempt < self.max_retries and response.status_code >= 500:
                    logger.warning(
                        f"Webhook server error {response.status_code}, "
                        f"retrying (attempt {attempt}/{self.max_retries})"
                    )
                    self._wait_with_backoff(attempt)
                    continue

                error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
                logger.error(f"Webhook failed: {error_msg}")
                self._log_delivery(webhook_url, event_type, False, error_msg, attempt)
                return (False, error_msg, attempt)

            except httpx.TimeoutException:
                error_msg = f"Timeout after {self.timeout}s"
                if attempt < self.max_retries:
                    logger.warning(f"{error_msg}, retrying (attempt {attempt}/{self.max_retries})")
                    self._wait_with_backoff(attempt)
                    continue
                logger.error(f"Webhook failed: {error_msg}")
                self._log_delivery(webhook_url, event_type, False, error_msg, attempt)
                return (False, error_msg, attempt)

            except httpx.RequestError as e:
                error_msg = f"Request failed: {str(e)[:100]}"
                if attempt < self.max_retries:
                    logger.warning(f"{error_msg}, retrying (attempt {attempt}/{self.max_retries})")
                    self._wait_with_backoff(attempt)
                    continue
                logger.error(f"Webhook failed: {error_msg}")
                self._log_delivery(webhook_url, event_type, False, error_msg, attempt)
                return (False, error_msg, attempt)

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)[:100]}"
                logger.error(f"Webhook failed: {error_msg}")
                self._log_delivery(webhook_url, event_type, False, error_msg, attempt)
                return (False, error_msg, attempt)

        return (False, "Max retries exceeded", self.max_retries)

    def _post_webhook(
        self,
        url: str,
        payload: Dict[str, Any],
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Perform HTTP POST to webhook URL.

        Args:
            url: Webhook URL
            payload: Payload data

        Returns:
            HTTP response object
        """
        headers = self.DEFAULT_HEADERS.copy()
        if extra_headers:
            headers.update(extra_headers)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                url,
                json=payload,
                headers=headers,
            )
            return response

    def _wait_with_backoff(self, attempt: int) -> None:
        """
        Wait before retry with exponential backoff.
        """
        import time

        wait_time = self.retry_delay * (self.RETRY_BACKOFF ** (attempt - 1))
        logger.debug(f"Waiting {wait_time:.1f}s before retry...")
        time.sleep(wait_time)

    def _log_delivery(
        self,
        webhook_url: str,
        event_type: WebhookEventType,
        success: bool,
        error: Optional[str],
        attempt: int,
    ) -> None:
        """
        Log webhook delivery attempt.

        Args:
            webhook_url: Webhook URL
            event_type: Event type
            success: Whether delivery was successful
            error: Error message if failed
            attempt: Attempt number
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": webhook_url,
            "event_type": event_type.value,
            "success": success,
            "error": error,
            "attempt": attempt,
        }
        self.delivery_log.append(log_entry)

    def get_delivery_log(self) -> list:
        """Get all delivery log entries."""
        return self.delivery_log.copy()

    def clear_delivery_log(self) -> None:
        """Clear delivery log."""
        self.delivery_log.clear()


# Global webhook notifier instance
_webhook_notifier: Optional[WebhookNotifier] = None


def get_webhook_notifier() -> WebhookNotifier:
    """Get or create global WebhookNotifier instance."""
    global _webhook_notifier
    if _webhook_notifier is None:
        _webhook_notifier = WebhookNotifier()
    return _webhook_notifier

import types
from unittest.mock import Mock

from workers.celery_app import analyze_complete_async


def make_mock_with_get(result):
    m = Mock()
    m.get = Mock(return_value=result)
    return Mock(delay=Mock(return_value=m))


def test_worker_sends_webhook_on_success(monkeypatch):
    # Mock subtask calls to return successful results
    mock_pii = make_mock_with_get({"status": "success", "entities": ["x"], "entity_count": 1})
    mock_compliance = make_mock_with_get(
        {
            "status": "success",
            "compliant": True,
            "violation_count": 0,
            "frameworks_checked": [],
            "violations": [],
        }
    )
    mock_risk = make_mock_with_get(
        {
            "status": "success",
            "overall_score": 1.0,
            "overall_level": "low",
            "recommendations": [],
        }
    )

    monkeypatch.setattr("workers.celery_app.detect_pii_async", mock_pii)
    monkeypatch.setattr("workers.celery_app.check_compliance_async", mock_compliance)
    monkeypatch.setattr("workers.celery_app.score_risk_async", mock_risk)

    # Mock notifier
    notifier_mock = Mock()
    notifier_mock.send_webhook = Mock(return_value=(True, None, 1))

    monkeypatch.setattr("app.webhooks.get_webhook_notifier", lambda: notifier_mock)

    # Dummy self with request id
    self = types.SimpleNamespace()
    self.request = types.SimpleNamespace()
    self.request.id = "task-xyz"

    # Call the underlying wrapped function to avoid Celery Task wrapper signature differences
    func = analyze_complete_async
    # Unwrap Celery task decorators to get to the underlying function
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__

    # Underlying function may be unbound (no self parameter), so call without passing task self
    try:
        res = func("hello", None, "https://example.com/hook", False)
    except TypeError:
        # Fallback: call with the dummy self if the underlying function expects it
        res = func(self, "hello", None, "https://example.com/hook", False)

    assert isinstance(res, dict)
    assert res.get("status") == "success"

    # Notifier should have been called once
    assert notifier_mock.send_webhook.called

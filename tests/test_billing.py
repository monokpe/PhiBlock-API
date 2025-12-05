from unittest.mock import patch

import pytest

from app.billing import BillingService


@pytest.fixture
def mock_stripe():
    with patch("app.billing.stripe") as mock:
        yield mock


def test_create_customer(mock_stripe):
    # Setup
    mock_stripe.Customer.create.return_value.id = "cus_test123"
    service = BillingService()
    service.api_key = "sk_test_123"

    # Execute
    customer_id = service.create_customer("test@example.com", "Test User")

    # Verify
    assert customer_id == "cus_test123"
    mock_stripe.Customer.create.assert_called_once_with(email="test@example.com", name="Test User")


def test_create_subscription(mock_stripe):
    # Setup
    mock_stripe.Subscription.create.return_value.id = "sub_test123"
    service = BillingService()
    service.api_key = "sk_test_123"

    # Execute
    sub_id = service.create_subscription("cus_test123", "price_123")

    # Verify
    assert sub_id == "sub_test123"
    mock_stripe.Subscription.create.assert_called_once_with(
        customer="cus_test123", items=[{"price": "price_123"}]
    )


def test_report_usage(mock_stripe):
    # Setup
    service = BillingService()
    service.api_key = "sk_test_123"

    # Execute
    success = service.report_usage("si_test123", 100)

    # Verify
    assert success is True
    mock_stripe.SubscriptionItem.create_usage_record.assert_called_once()
    args, kwargs = mock_stripe.SubscriptionItem.create_usage_record.call_args
    assert args[0] == "si_test123"
    assert kwargs["quantity"] == 100
    assert kwargs["action"] == "increment"


def test_billing_service_no_key():
    # Setup
    with patch.dict("os.environ", {}, clear=True):
        service = BillingService()
        service.api_key = None

        # Execute & Verify
        assert service.create_customer("test@example.com", "Test") is None
        assert service.create_subscription("cus_123", "price_123") is None
        assert service.report_usage("si_123", 100) is False

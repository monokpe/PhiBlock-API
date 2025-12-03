import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import Tenant, TokenUsage
from workers.celery_app import sync_usage_to_stripe

# Mock data
TENANT_ID = str(uuid.uuid4())
STRIPE_SUB_ID = "sub_123"
STRIPE_ITEM_ID = "si_123"


@pytest.fixture
def mock_db_session():
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def mock_billing_service():
    with patch("app.billing.billing_service") as mock:
        mock.api_key = "sk_test_123"
        yield mock


@pytest.fixture
def mock_stripe():
    with patch("stripe.Subscription") as mock:
        yield mock


def test_sync_usage_to_stripe_success(mock_db_session, mock_billing_service, mock_stripe):
    # Setup DB mocks
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        # 1. Mock Tenants
        tenant = Tenant(id=TENANT_ID, slug="test-tenant", stripe_subscription_id=STRIPE_SUB_ID)
        mock_db_session.query.return_value.filter.return_value.all.return_value = [tenant]

        # 2. Mock Usage Stats
        # We need to mock the chain: db.query(...).filter(...).first()
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value

        # Mock the result object (needs total_tokens and request_count attributes)
        mock_result = MagicMock()
        mock_result.total_tokens = 150
        mock_result.request_count = 10
        mock_filter.first.return_value = mock_result

        # 3. Mock Stripe Subscription Retrieval
        mock_sub = MagicMock()
        mock_item = MagicMock()
        mock_item.id = STRIPE_ITEM_ID
        mock_sub.__getitem__.side_effect = lambda k: {"data": [mock_item]} if k == "items" else None
        # Also support dot access for items if needed, but the code uses ['items']
        # The code uses: subscription['items']['data'][0].id
        # subscription is mock_sub.
        # subscription['items'] returns {"data": [mock_item]}
        # subscription['items']['data'][0] returns mock_item
        # mock_item.id works.

        mock_stripe.retrieve.return_value = mock_sub

        # 4. Mock Billing Service Report
        mock_billing_service.report_usage.return_value = True

        # Run the task
        sync_usage_to_stripe()

        # Verify Stripe Report called
        mock_billing_service.report_usage.assert_called_once_with(STRIPE_ITEM_ID, 150)

        # Verify DB Update
        # Check if update was called on the query
        assert mock_filter.update.called
        mock_filter.update.assert_called_with({TokenUsage.reported_to_stripe: True})

        # Verify Commit
        assert mock_db_session.commit.called


def test_sync_usage_no_usage(mock_db_session, mock_billing_service, mock_stripe):
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        tenant = Tenant(id=TENANT_ID, slug="test-tenant", stripe_subscription_id=STRIPE_SUB_ID)
        mock_db_session.query.return_value.filter.return_value.all.return_value = [tenant]

        mock_result = MagicMock()
        mock_result.total_tokens = 0  # No tokens
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_result

        sync_usage_to_stripe()

        # Verify NO report to Stripe
        mock_billing_service.report_usage.assert_not_called()


def test_sync_usage_stripe_failure(mock_db_session, mock_billing_service, mock_stripe):
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        tenant = Tenant(id=TENANT_ID, slug="test-tenant", stripe_subscription_id=STRIPE_SUB_ID)
        mock_db_session.query.return_value.filter.return_value.all.return_value = [tenant]

        mock_result = MagicMock()
        mock_result.total_tokens = 100
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_result

        mock_sub = MagicMock()
        mock_item = MagicMock()
        mock_item.id = STRIPE_ITEM_ID
        mock_sub.__getitem__.side_effect = lambda k: {"data": [mock_item]} if k == "items" else None
        mock_stripe.retrieve.return_value = mock_sub

        # Simulate Failure
        mock_billing_service.report_usage.return_value = False

        sync_usage_to_stripe()

        # Verify report called
        mock_billing_service.report_usage.assert_called()

        # Verify NO DB Update (should not mark as reported)
        mock_db_session.query.return_value.filter.return_value.update.assert_not_called()

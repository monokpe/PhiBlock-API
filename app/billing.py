import logging
import os
import time
from typing import Optional

import stripe

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        if self.api_key:
            stripe.api_key = self.api_key
        else:
            logger.warning("STRIPE_SECRET_KEY not set. Billing features will be disabled.")

    def create_customer(self, email: str, name: str) -> Optional[str]:
        """
        Creates a Stripe customer and returns the customer ID.
        """
        if not self.api_key:
            return None

        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
            )
            return customer.id
        except Exception as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            return None

    def create_subscription(self, customer_id: str, price_id: str) -> Optional[str]:
        """
        Creates a subscription for the customer.
        """
        if not self.api_key:
            return None

        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
            )
            return subscription.id
        except Exception as e:
            logger.error(f"Failed to create Stripe subscription: {e}")
            return None

    def report_usage(self, subscription_item_id: str, quantity: int, timestamp: int = None) -> bool:
        """
        Reports metered usage to Stripe.
        """
        if not self.api_key:
            return False

        try:
            # Idempotency key to prevent duplicate reports
            idempotency_key = f"usage_{subscription_item_id}_{timestamp}" if timestamp else None

            stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                timestamp=timestamp or int(time.time()),
                action="increment",
                idempotency_key=idempotency_key,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to report usage to Stripe: {e}")
            return False


billing_service = BillingService()

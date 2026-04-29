import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PaymentIntentResult:
    intent_id: str
    client_secret: Optional[str]  # None for mock (no frontend confirmation needed)
    status: str  # "pending" | "succeeded"


class PaymentProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: dict,
    ) -> PaymentIntentResult: ...

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        """Parse and verify a webhook payload. Raises on invalid signature."""
        ...


# ── Stripe ─────────────────────────────────────────────────────────────

class StripePaymentProvider(PaymentProvider):
    def __init__(self) -> None:
        try:
            import stripe as _stripe
        except ImportError:
            raise RuntimeError("stripe package is not installed. Run: pip install stripe")

        self._stripe = _stripe
        self._stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        self._webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self._publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

        if not self._stripe.api_key:
            raise RuntimeError("STRIPE_SECRET_KEY env var is not set")
        if not self._webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET env var is not set")

    @property
    def name(self) -> str:
        return "stripe"

    @property
    def publishable_key(self) -> str:
        return self._publishable_key

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: dict,
    ) -> PaymentIntentResult:
        # Stripe amounts are in smallest currency unit (cents for EUR)
        amount_cents = int(amount * 100)
        intent = self._stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency.lower(),
            metadata=metadata,
            payment_method_types=["card"],
        )
        logger.info("Stripe PaymentIntent created: %s amount=%s %s", intent.id, amount, currency)
        return PaymentIntentResult(
            intent_id=intent.id,
            client_secret=intent.client_secret,
            status="pending",
        )

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        event = self._stripe.Webhook.construct_event(
            payload, signature, self._webhook_secret
        )
        return dict(event)


# ── Mock ────────────────────────────────────────────────────────────────

class MockPaymentProvider(PaymentProvider):
    """Simulates a payment provider for local development without credentials.

    Payments are immediately "succeeded" — no frontend confirmation or webhook needed.
    """

    @property
    def name(self) -> str:
        return "mock"

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: dict,
    ) -> PaymentIntentResult:
        intent_id = f"mock_{uuid.uuid4().hex}"
        logger.info("Mock payment intent created: %s amount=%s %s", intent_id, amount, currency)
        return PaymentIntentResult(
            intent_id=intent_id,
            client_secret=None,
            status="succeeded",
        )

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        return json.loads(payload)


# ── Factory ─────────────────────────────────────────────────────────────

def get_payment_provider() -> PaymentProvider:
    provider_name = os.getenv("PAYMENT_PROVIDER", "mock").lower()
    if provider_name == "stripe":
        return StripePaymentProvider()
    logger.info("Using MockPaymentProvider (PAYMENT_PROVIDER=%s)", provider_name)
    return MockPaymentProvider()

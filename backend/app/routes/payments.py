import logging

from fastapi import APIRouter, HTTPException, Request

from app.services import payment_provider as pp_module
from app.services import wallet_service as ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# Stripe event types that trigger a wallet credit
CREDIT_EVENTS = {"payment_intent.succeeded"}


@router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(request: Request):
    """Stripe webhook receiver.

    Verifies the Stripe-Signature header and processes payment_intent.succeeded
    events to credit the user's wallet idempotently.
    Stripe retries unacknowledged webhooks — returning 200 always stops retries.
    """
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        provider = pp_module.get_payment_provider()
    except RuntimeError as exc:
        logger.error("Payment provider unavailable during webhook: %s", exc)
        raise HTTPException(status_code=503, detail="Payment provider not configured")

    if provider.name != "stripe":
        raise HTTPException(
            status_code=400,
            detail="Stripe webhook received but PAYMENT_PROVIDER is not stripe",
        )

    try:
        event = provider.verify_webhook(payload, signature)
    except Exception as exc:
        logger.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type: str = event.get("type", "")
    event_id: str = event.get("id", "")
    logger.info("Stripe webhook received: type=%s id=%s", event_type, event_id)

    if event_type not in CREDIT_EVENTS:
        return {"received": True, "action": "ignored", "event_type": event_type}

    payment_intent: dict = event.get("data", {}).get("object", {})
    intent_id: str = payment_intent.get("id", "")
    email: str = payment_intent.get("metadata", {}).get("email", "")

    if not intent_id or not email:
        logger.error(
            "Webhook payload missing intent_id or email: event=%s intent=%s email=%s",
            event_id, intent_id, email,
        )
        # Return 200 to prevent Stripe from retrying a malformed event
        return {"received": True, "action": "skipped", "reason": "missing_fields"}

    credited = await ws.credit_wallet(provider_payment_id=intent_id)

    action = "credited" if credited else "skipped"
    logger.info("Webhook %s: intent=%s email=%s", action, intent_id, email)
    return {"received": True, "action": action, "intent_id": intent_id}

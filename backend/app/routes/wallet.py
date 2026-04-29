import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_email
from app.models.wallet import (
    TopUpRequest,
    TopUpResponse,
    TransactionListResponse,
    TransactionResponse,
    WalletResponse,
)
from app.services import payment_provider as pp_module
from app.services import wallet_service as ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])

CurrentEmail = Annotated[str, Depends(get_current_email)]


@router.get("", response_model=WalletResponse)
async def get_wallet(email: CurrentEmail):
    """Return the authenticated user's wallet balance."""
    data = await ws.get_wallet(email)
    return WalletResponse(**data)


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    email: CurrentEmail,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return paginated transaction history for the authenticated user."""
    data = await ws.get_transactions(email, page=page, limit=limit)
    return TransactionListResponse(
        transactions=[TransactionResponse(**t) for t in data["transactions"]],
        total=data["total"],
        page=data["page"],
        limit=data["limit"],
    )


@router.post("/topup", response_model=TopUpResponse)
async def create_topup(body: TopUpRequest, email: CurrentEmail):
    """Initiate a wallet top-up.

    - **Mock mode** (PAYMENT_PROVIDER=mock): credits wallet immediately; returns status="completed".
    - **Stripe mode** (PAYMENT_PROVIDER=stripe): creates a PaymentIntent and returns the
      client_secret for frontend confirmation. Wallet is credited via the Stripe webhook.
    """
    try:
        provider = pp_module.get_payment_provider()
    except RuntimeError as exc:
        logger.error("Payment provider init failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    idempotency_key = f"topup:{email}:{body.amount}:{provider.name}"

    try:
        intent = await provider.create_payment_intent(
            amount=body.amount,
            currency="EUR",
            metadata={"email": email},
        )
    except Exception as exc:
        logger.exception("Payment intent creation failed for %s: %s", email, exc)
        raise HTTPException(status_code=502, detail="Payment provider error")

    await ws.create_pending_transaction(
        email=email,
        amount=body.amount,
        provider=provider.name,
        provider_payment_id=intent.intent_id,
        idempotency_key=idempotency_key,
        metadata={"amount_requested": str(body.amount)},
    )

    # Mock provider: intent is already succeeded — credit immediately
    if intent.status == "succeeded":
        credited_tx = await ws.credit_wallet(provider_payment_id=intent.intent_id)
        wallet = await ws.get_wallet(email)
        return TopUpResponse(
            mode="mock",
            transaction_id=credited_tx["id"] if credited_tx else None,
            status="completed",
            balance=wallet["balance"],
        )

    # Stripe: return client_secret for frontend card confirmation
    publishable_key = getattr(provider, "publishable_key", "")
    return TopUpResponse(
        mode="stripe",
        client_secret=intent.client_secret,
        payment_intent_id=intent.intent_id,
        publishable_key=publishable_key,
    )

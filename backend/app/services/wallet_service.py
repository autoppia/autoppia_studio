import logging
from datetime import datetime, timezone
from decimal import Decimal

from bson import Decimal128
from pymongo import ReturnDocument

from app.database import wallet_transactions_collection, wallets_collection

logger = logging.getLogger(__name__)

DEFAULT_CURRENCY = "EUR"


# ── BSON ↔ Decimal helpers ──────────────────────────────────────────────

def _d128(v: Decimal) -> Decimal128:
    return Decimal128(str(v))


def _to_decimal(v) -> Decimal:
    if isinstance(v, Decimal128):
        return Decimal(str(v))
    return Decimal(str(v))


# ── Formatting ──────────────────────────────────────────────────────────

def _fmt_transaction(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "type": doc["type"],
        "amount": str(_to_decimal(doc["amount"])),
        "currency": doc["currency"],
        "status": doc["status"],
        "provider": doc["provider"],
        "provider_payment_id": doc.get("provider_payment_id"),
        "idempotency_key": doc.get("idempotency_key", ""),
        "metadata": doc.get("metadata", {}),
        "created_at": doc["created_at"].isoformat(),
        "updated_at": doc["updated_at"].isoformat(),
    }


# ── Wallet CRUD ─────────────────────────────────────────────────────────

async def get_or_create_wallet(email: str) -> dict:
    now = datetime.now(timezone.utc)
    wallet = await wallets_collection.find_one_and_update(
        {"email": email},
        {
            "$setOnInsert": {
                "email": email,
                "balance_available": _d128(Decimal("0.00")),
                "currency": DEFAULT_CURRENCY,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return wallet


async def get_wallet(email: str) -> dict:
    wallet = await wallets_collection.find_one({"email": email})
    if not wallet:
        wallet = await get_or_create_wallet(email)
    updated = wallet.get("updated_at") or wallet.get("created_at")
    return {
        "balance": str(_to_decimal(wallet["balance_available"])),
        "currency": wallet["currency"],
        "updated_at": updated.isoformat() if updated else None,
    }


# ── Transaction creation ─────────────────────────────────────────────────

async def create_pending_transaction(
    *,
    email: str,
    amount: Decimal,
    provider: str,
    provider_payment_id: str,
    idempotency_key: str,
    metadata: dict,
) -> dict:
    wallet = await get_or_create_wallet(email)
    now = datetime.now(timezone.utc)
    doc = {
        "email": email,
        "wallet_id": wallet["_id"],
        "type": "topup_credit",
        "amount": _d128(amount),
        "currency": DEFAULT_CURRENCY,
        "status": "pending",
        "provider": provider,
        "provider_payment_id": provider_payment_id,
        "idempotency_key": idempotency_key,
        "metadata": metadata,
        "created_at": now,
        "updated_at": now,
    }
    result = await wallet_transactions_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "Pending transaction created: id=%s email=%s amount=%s provider_payment_id=%s",
        result.inserted_id, email, amount, provider_payment_id,
    )
    return _fmt_transaction(doc)


# ── Wallet crediting (idempotent) ────────────────────────────────────────

async def credit_wallet(*, provider_payment_id: str) -> dict | None:
    """Idempotently complete a pending top-up and credit the wallet.

    Uses the provider_payment_id as the unique guard:
    - Atomically transitions the transaction from pending → completed.
    - Only the first caller wins; subsequent calls are no-ops (idempotent).
    - Then reads the current balance, adds the amount, and writes back.

    Returns the formatted transaction on first credit, None if already processed.
    """
    now = datetime.now(timezone.utc)

    # Atomic guard: only one caller can transition pending → completed
    tx = await wallet_transactions_collection.find_one_and_update(
        {"provider_payment_id": provider_payment_id, "status": "pending"},
        {"$set": {"status": "completed", "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )

    if not tx:
        # Check whether it was already completed (idempotent call)
        existing = await wallet_transactions_collection.find_one(
            {"provider_payment_id": provider_payment_id}
        )
        if existing and existing["status"] == "completed":
            logger.info("Idempotent skip: payment_id=%s already completed", provider_payment_id)
        else:
            logger.warning(
                "credit_wallet: no pending transaction for payment_id=%s", provider_payment_id
            )
        return None

    amount = _to_decimal(tx["amount"])

    # Read-modify-write the balance.
    # Safe because only one caller reaches this point per provider_payment_id.
    wallet = await wallets_collection.find_one({"email": tx["email"]})
    if not wallet:
        wallet = await get_or_create_wallet(tx["email"])

    current = _to_decimal(wallet["balance_available"])
    new_balance = (current + amount).quantize(Decimal("0.01"))

    await wallets_collection.update_one(
        {"email": tx["email"]},
        {"$set": {"balance_available": _d128(new_balance), "updated_at": now}},
    )

    logger.info(
        "Wallet credited: email=%s amount=%s %s new_balance=%s payment_id=%s",
        tx["email"], amount, tx["currency"], new_balance, provider_payment_id,
    )
    return _fmt_transaction(tx)


# ── Transaction history ──────────────────────────────────────────────────

async def get_transactions(email: str, page: int = 1, limit: int = 20) -> dict:
    skip = (page - 1) * limit
    cursor = wallet_transactions_collection.find(
        {"email": email},
        sort=[("created_at", -1)],
        skip=skip,
        limit=limit,
    )
    docs = await cursor.to_list(length=limit)
    total = await wallet_transactions_collection.count_documents({"email": email})
    return {
        "transactions": [_fmt_transaction(d) for d in docs],
        "total": total,
        "page": page,
        "limit": limit,
    }

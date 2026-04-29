"""Wallet service and payment-provider tests.

Covers:
- Wallet creation and retrieval
- Successful top-up (mock provider)
- Idempotency: repeated credit does not double the balance
- Provider failure does not change balance
- Transaction listing
"""
import pytest
import pytest_asyncio
from decimal import Decimal

from tests.conftest import TEST_EMAIL


# ── Helpers ─────────────────────────────────────────────────────────────

def _patch_collections(monkeypatch, wallets_col, txns_col):
    """Redirect service module collections to the test-DB collections."""
    import app.services.wallet_service as ws
    monkeypatch.setattr(ws, "wallets_collection", wallets_col)
    monkeypatch.setattr(ws, "wallet_transactions_collection", txns_col)


@pytest_asyncio.fixture
async def cols():
    """Return test-DB collection handles."""
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_CONNECTION_URI"])
    db = client.get_default_database(default="automata_test")
    yield db["wallets"], db["wallet_transactions"]
    client.close()


# ── get_or_create_wallet ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_creates_wallet_on_first_call(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import get_or_create_wallet, _to_decimal
    wallet = await get_or_create_wallet(TEST_EMAIL)

    assert wallet["email"] == TEST_EMAIL
    assert _to_decimal(wallet["balance_available"]) == Decimal("0.00")
    assert wallet["currency"] == "EUR"


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import get_or_create_wallet
    w1 = await get_or_create_wallet(TEST_EMAIL)
    w2 = await get_or_create_wallet(TEST_EMAIL)

    assert str(w1["_id"]) == str(w2["_id"])
    count = await wallets.count_documents({"email": TEST_EMAIL})
    assert count == 1


# ── get_wallet ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_wallet_returns_formatted_balance(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import get_wallet
    data = await get_wallet(TEST_EMAIL)

    assert data["balance"] == "0.00"
    assert data["currency"] == "EUR"


# ── credit_wallet ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_credit_wallet_increases_balance(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import (
        create_pending_transaction, credit_wallet, get_wallet
    )
    await create_pending_transaction(
        email=TEST_EMAIL,
        amount=Decimal("25.00"),
        provider="mock",
        provider_payment_id="mock_abc123",
        idempotency_key="topup:test@x.com:25.00:mock",
        metadata={},
    )

    tx = await credit_wallet(provider_payment_id="mock_abc123")

    assert tx is not None
    assert tx["status"] == "completed"
    assert tx["amount"] == "25.00"

    wallet = await get_wallet(TEST_EMAIL)
    assert wallet["balance"] == "25.00"


@pytest.mark.asyncio
async def test_credit_wallet_is_idempotent(monkeypatch, cols):
    """Sending the same payment_id twice must not double the balance."""
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import (
        create_pending_transaction, credit_wallet, get_wallet
    )
    await create_pending_transaction(
        email=TEST_EMAIL,
        amount=Decimal("50.00"),
        provider="mock",
        provider_payment_id="mock_idem_test",
        idempotency_key="topup:test@x.com:50.00:mock",
        metadata={},
    )

    first = await credit_wallet(provider_payment_id="mock_idem_test")
    second = await credit_wallet(provider_payment_id="mock_idem_test")

    assert first is not None
    assert second is None  # idempotent skip

    wallet = await get_wallet(TEST_EMAIL)
    assert wallet["balance"] == "50.00"  # credited exactly once


@pytest.mark.asyncio
async def test_credit_unknown_payment_returns_none(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import credit_wallet, get_wallet
    result = await credit_wallet(provider_payment_id="nonexistent_payment")

    assert result is None
    wallet = await get_wallet(TEST_EMAIL)
    assert wallet["balance"] == "0.00"  # unchanged


# ── Cumulative top-ups ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_topups_accumulate_correctly(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import (
        create_pending_transaction, credit_wallet, get_wallet
    )
    payments = [
        ("mock_p1", "key1", Decimal("10.00")),
        ("mock_p2", "key2", Decimal("20.50")),
        ("mock_p3", "key3", Decimal("5.75")),
    ]
    for pid, key, amt in payments:
        await create_pending_transaction(
            email=TEST_EMAIL, amount=amt, provider="mock",
            provider_payment_id=pid, idempotency_key=key, metadata={},
        )
        await credit_wallet(provider_payment_id=pid)

    wallet = await get_wallet(TEST_EMAIL)
    assert Decimal(wallet["balance"]) == Decimal("36.25")


# ── Transaction listing ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_transactions_paginated(monkeypatch, cols):
    wallets, txns = cols
    _patch_collections(monkeypatch, wallets, txns)

    from app.services.wallet_service import (
        create_pending_transaction, credit_wallet, get_transactions
    )
    for i in range(5):
        pid = f"mock_list_{i}"
        await create_pending_transaction(
            email=TEST_EMAIL, amount=Decimal("1.00"), provider="mock",
            provider_payment_id=pid, idempotency_key=f"key_list_{i}", metadata={},
        )
        await credit_wallet(provider_payment_id=pid)

    page1 = await get_transactions(TEST_EMAIL, page=1, limit=3)
    assert len(page1["transactions"]) == 3
    assert page1["total"] == 5

    page2 = await get_transactions(TEST_EMAIL, page=2, limit=3)
    assert len(page2["transactions"]) == 2


# ── MockPaymentProvider ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_provider_returns_succeeded_intent():
    from app.services.payment_provider import MockPaymentProvider
    provider = MockPaymentProvider()
    intent = await provider.create_payment_intent(
        amount=Decimal("15.00"), currency="EUR", metadata={}
    )
    assert intent.status == "succeeded"
    assert intent.client_secret is None
    assert intent.intent_id.startswith("mock_")

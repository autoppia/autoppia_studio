"""Pytest configuration and shared fixtures for wallet tests.

Tests use a real MongoDB on localhost:27017 (test database) and the MockPaymentProvider.
Run with:  cd backend && pytest tests/ -v
"""
import asyncio
import os
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Point at a throwaway test DB
os.environ.setdefault("MONGO_CONNECTION_URI", "mongodb://localhost:27017/automata_test")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET", "test-secret")

TEST_EMAIL = "wallet_test@example.com"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Drop wallet collections before each test."""
    client = AsyncIOMotorClient(os.environ["MONGO_CONNECTION_URI"])
    db = client.get_default_database(default="automata_test")
    await db["wallets"].delete_many({})
    await db["wallet_transactions"].delete_many({})
    # Ensure indexes exist (idempotent)
    await db["wallets"].create_index("email", unique=True)
    await db["wallet_transactions"].create_index("provider_payment_id", unique=True, sparse=True)
    await db["wallet_transactions"].create_index("idempotency_key", unique=True)
    yield
    client.close()

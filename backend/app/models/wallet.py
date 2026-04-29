from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

MIN_TOPUP = Decimal("1.00")
MAX_TOPUP = Decimal("1000.00")
DEFAULT_CURRENCY = "EUR"


class TopUpRequest(BaseModel):
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v < MIN_TOPUP:
            raise ValueError(f"Minimum top-up is {MIN_TOPUP}")
        if v > MAX_TOPUP:
            raise ValueError(f"Maximum top-up is {MAX_TOPUP}")
        return v.quantize(Decimal("0.01"))


class WalletResponse(BaseModel):
    balance: str
    currency: str
    updated_at: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    type: str
    amount: str
    currency: str
    status: str
    provider: str
    provider_payment_id: Optional[str] = None
    created_at: str
    metadata: dict = {}


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int
    page: int
    limit: int


class TopUpResponse(BaseModel):
    mode: str  # "stripe" | "mock"
    transaction_id: Optional[str] = None
    # Stripe-specific
    client_secret: Optional[str] = None
    payment_intent_id: Optional[str] = None
    publishable_key: Optional[str] = None
    # Mock — already completed
    status: Optional[str] = None
    balance: Optional[str] = None

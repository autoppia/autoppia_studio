# Wallet & Payments — Architecture

## Overview

A credit-based wallet system that lets users add funds and tracks every movement with a full audit trail. Built provider-agnostic: works in local dev with a **Mock** provider and in production with **Stripe**.

---

## Architecture

```
Frontend (React + Redux)
    │
    ├── GET  /wallet                 ← balance
    ├── GET  /wallet/transactions    ← paginated history
    ├── POST /wallet/topup           ← initiate top-up
    └── POST /payments/webhooks/stripe ← Stripe event (backend-only)

Backend (FastAPI + Motor + MongoDB)
    │
    ├── app/routes/wallet.py         ← JWT-authenticated wallet endpoints
    ├── app/routes/payments.py       ← Stripe webhook receiver
    ├── app/services/wallet_service.py ← business logic (credit, read, list)
    ├── app/services/payment_provider.py ← PaymentProvider interface
    │   ├── StripePaymentProvider    ← real Stripe
    │   └── MockPaymentProvider      ← instant success, no credentials
    ├── app/models/wallet.py         ← Pydantic request/response models
    └── app/deps.py                  ← JWT auth dependency
```

---

## Data Model

### `wallets` collection (one per user)

| Field               | Type        | Notes                         |
|---------------------|-------------|-------------------------------|
| `email`             | string      | Unique, matches users.email   |
| `balance_available` | Decimal128  | Exact decimal, never float    |
| `currency`          | string      | Default: `"EUR"`              |
| `created_at`        | datetime    |                               |
| `updated_at`        | datetime    |                               |

### `wallet_transactions` collection (append-only ledger)

| Field                | Type        | Notes                                      |
|----------------------|-------------|--------------------------------------------|
| `email`              | string      | Owner                                      |
| `wallet_id`          | ObjectId    | Reference to wallets._id                   |
| `type`               | string      | `topup_credit` \| `topup_refund` \| `adjustment` |
| `amount`             | Decimal128  | Always positive; sign is encoded in `type` |
| `currency`           | string      |                                            |
| `status`             | string      | `pending` \| `completed` \| `failed` \| `refunded` |
| `provider`           | string      | `stripe` \| `mock` \| `manual`             |
| `provider_payment_id`| string      | Stripe `pi_…` or `mock_<uuid>` — **unique index** |
| `idempotency_key`    | string      | Client-generated guard — **unique index**  |
| `metadata`           | object      | Free-form context                          |
| `created_at`         | datetime    |                                            |
| `updated_at`         | datetime    |                                            |

---

## Event Flow

### Mock provider (local dev)

```
Frontend                          Backend
   │                                 │
   │──POST /wallet/topup ──────────► │ 1. MockPaymentProvider.create_payment_intent()
   │                                 │    → intent.status = "succeeded" immediately
   │                                 │ 2. create_pending_transaction()
   │                                 │ 3. credit_wallet() — atomic pending→completed
   │                                 │ 4. Return { mode: "mock", balance, status: "completed" }
   │◄─────────────────────────────── │
   │  Show success, update balance   │
```

### Stripe provider (production)

```
Frontend                          Backend                    Stripe
   │                                 │                          │
   │──POST /wallet/topup ──────────► │ 1. PaymentIntent.create() ──────────► │
   │                                 │ 2. create_pending_transaction()        │
   │◄── { client_secret, pk } ─────  │                                        │
   │                                 │                                        │
   │  stripe.confirmCardPayment()    │                                        │
   │─────────────────────────────────────────────────────────────────────────►│
   │◄── payment_intent.succeeded ────│◄── POST /payments/webhooks/stripe ─── │
   │                                 │ 3. verify_webhook() (signature check)  │
   │                                 │ 4. credit_wallet(provider_payment_id)  │
   │                                 │    → atomic pending→completed          │
   │                                 │    → balance += amount                 │
   │  Poll GET /wallet for balance   │                                        │
   │─────────────────────────────────►                                        │
```

---

## Idempotency

Two-layer guard to ensure exactly-once crediting:

1. **`provider_payment_id` unique index** on `wallet_transactions` — prevents duplicate transaction documents at the DB level.
2. **Atomic status transition** — `find_one_and_update` with `{status: "pending"}` filter: only one caller can win the race to `completed`. Subsequent calls find no matching document and skip the balance update.

If Stripe retries a webhook (network hiccup), the second call returns `None` from `credit_wallet()` and the balance is untouched.

---

## Security

- All wallet endpoints require a valid JWT (extracted from `Authorization: Bearer` header or `access_token` cookie).
- The Stripe webhook verifies the `Stripe-Signature` header using `stripe.Webhook.construct_event()`.
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are never exposed to the client.
- The Stripe Publishable Key is exposed to the frontend (this is intentional and safe — it cannot create charges).

---

## Environment Variables

```env
# Select provider: "mock" (default) or "stripe"
PAYMENT_PROVIDER=mock

# Required when PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Frontend:
```env
# Optional — enables Stripe card element instead of mock flow
REACT_APP_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

---

## Running Locally (end-to-end)

### Mock provider (no credentials needed)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm start
```

1. Log in → Settings → Credit tab
2. Enter an amount (€1–€1,000) → click "Add funds"
3. Balance updates immediately (mock credits synchronously)

### Stripe provider

```bash
# Install Stripe CLI: https://stripe.com/docs/stripe-cli
stripe listen --forward-to localhost:8000/payments/webhooks/stripe

# Set in backend .env:
PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=<from stripe listen output>

# Set in frontend .env.development:
REACT_APP_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

Use test card `4242 4242 4242 4242`, any future expiry, any CVC.

### Running tests

```bash
cd backend
pip install pytest pytest-asyncio
# MongoDB must be running on localhost:27017
pytest tests/ -v
```

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| MongoDB Decimal128 for amounts | Exact decimal arithmetic — no float rounding errors |
| `provider_payment_id` as idempotency guard | Provider IDs are globally unique; no key generation needed |
| Read-modify-write balance (not `$inc` with Decimal128) | Safer cross-driver compatibility; protected by the single-caller guarantee from the status transition |
| Mock provider completes synchronously | No webhook infrastructure needed for local dev |
| JWT in `Authorization` header for wallet endpoints | Wallet endpoints are the first in the codebase to enforce server-side JWT verification — other endpoints use email as a param (existing pattern) |
| Single configurable currency (EUR) | Simplest correct MVP; multi-currency is a future concern |

---

## Pending: Future Spending Logic

When spending logic is added (e.g., billing per automation run), the following is already in place:

- `wallet_transactions.type` supports `adjustment` and any future `spend_debit` type
- `balance_available` tracks net balance; a `balance_held` field can be added for holds
- The `wallet_service` can be extended with a `debit_wallet(email, amount, reason)` function following the same idempotency pattern
- Consider MongoDB transactions (requires replica set) for production-grade atomicity between the debit and the session record creation

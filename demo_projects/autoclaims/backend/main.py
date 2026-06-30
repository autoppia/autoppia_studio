from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "index.html"
DOCS = ROOT / "docs"

app = FastAPI(title="AutoClaims API", version="0.1.0")


ClaimStatus = Literal["open", "approved", "manual_review", "rejected"]


class Customer(BaseModel):
    customerId: str
    name: str
    email: str
    tier: str = "standard"


class Claim(BaseModel):
    claimId: str
    customerId: str
    title: str
    status: ClaimStatus
    amount: float
    fraudFlag: bool = False
    notes: list[str] = Field(default_factory=list)


class ClaimNoteRequest(BaseModel):
    note: str


class ClaimDecisionRequest(BaseModel):
    decision: ClaimStatus
    reason: str


CUSTOMERS: dict[str, Customer] = {
    "cust-ada": Customer(customerId="cust-ada", name="Ada Lovelace", email="ada@example.com", tier="gold"),
    "cust-grace": Customer(customerId="cust-grace", name="Grace Hopper", email="grace@example.com", tier="standard"),
    "cust-katherine": Customer(customerId="cust-katherine", name="Katherine Johnson", email="katherine@example.com", tier="gold"),
}

CLAIMS: dict[str, Claim] = {
    "CLM-1001": Claim(
        claimId="CLM-1001",
        customerId="cust-ada",
        title="Laptop screen damage",
        status="open",
        amount=420.0,
        notes=["Photos received", "Warranty active"],
    ),
    "CLM-2002": Claim(
        claimId="CLM-2002",
        customerId="cust-grace",
        title="High-value equipment loss",
        status="open",
        amount=7200.0,
        fraudFlag=True,
        notes=["Police report pending"],
    ),
    "CLM-3003": Claim(
        claimId="CLM-3003",
        customerId="cust-katherine",
        title="Travel delay compensation",
        status="open",
        amount=180.0,
        notes=["Customer requested phone follow-up"],
    ),
}


def require_demo_auth(authorization: str = Header(default="")) -> None:
    if authorization and authorization == "Bearer autoclaims-demo-token":
        return
    raise HTTPException(status_code=401, detail="Use Authorization: Bearer autoclaims-demo-token")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/docs/{name}", response_class=PlainTextResponse, include_in_schema=False)
async def read_doc(name: str) -> str:
    path = DOCS / name
    if not path.exists() or path.suffix != ".md":
        raise HTTPException(status_code=404, detail="Document not found")
    return path.read_text(encoding="utf-8")


@app.get("/customers/search", operation_id="searchCustomers")
async def search_customers(query: str, authorization: str = Header(default="")) -> list[Customer]:
    require_demo_auth(authorization)
    q = query.lower().strip()
    return [customer for customer in CUSTOMERS.values() if q in customer.name.lower() or q in customer.email.lower()]


@app.get("/claims", operation_id="listClaims")
async def list_claims(customerId: str = "", status: str = "", authorization: str = Header(default="")) -> list[Claim]:
    require_demo_auth(authorization)
    claims = list(CLAIMS.values())
    if customerId:
        claims = [claim for claim in claims if claim.customerId == customerId]
    if status:
        claims = [claim for claim in claims if claim.status == status]
    return claims


@app.get("/claims/{claim_id}", operation_id="getClaim")
async def get_claim(claim_id: str, authorization: str = Header(default="")) -> Claim:
    require_demo_auth(authorization)
    claim = CLAIMS.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@app.post("/claims/{claim_id}/notes", operation_id="addClaimNote")
async def add_claim_note(claim_id: str, body: ClaimNoteRequest, authorization: str = Header(default="")) -> Claim:
    require_demo_auth(authorization)
    claim = CLAIMS.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.notes.append(body.note)
    return claim


@app.post("/claims/{claim_id}/decision", operation_id="setClaimDecision")
async def set_claim_decision(claim_id: str, body: ClaimDecisionRequest, authorization: str = Header(default="")) -> Claim:
    require_demo_auth(authorization)
    claim = CLAIMS.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.status = body.decision
    claim.notes.append(f"Decision: {body.decision}. Reason: {body.reason}")
    return claim

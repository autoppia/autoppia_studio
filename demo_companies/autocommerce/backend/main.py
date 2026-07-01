from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AutoCommerce API", version="0.1.0")

ORDERS = {
    "ORD-1001": {
        "orderId": "ORD-1001",
        "status": "in_transit",
        "carrier": "DHL",
        "latestCustomerNote": "Customer asked for delivery ETA this morning.",
    },
    "ORD-2002": {
        "orderId": "ORD-2002",
        "status": "delayed",
        "carrier": "UPS",
        "latestCustomerNote": "Promised ship date was more than 72 hours ago.",
    },
}

INVENTORY_NOTES: dict[str, list[str]] = {"SKU-RED-MUG": []}
REFUND_DRAFTS: list[dict[str, object]] = []


class RefundDraft(BaseModel):
    reason: str
    amount: float = 0
    policyReference: str


class InventoryNote(BaseModel):
    note: str


@app.get("/orders/{orderId}", operation_id="getOrder")
def get_order(orderId: str) -> dict[str, object]:
    order = ORDERS.get(orderId)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/orders/{orderId}/refund-drafts", operation_id="draftRefund", status_code=201)
def draft_refund(orderId: str, payload: RefundDraft) -> dict[str, object]:
    if orderId not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    draft = {"orderId": orderId, **payload.model_dump()}
    REFUND_DRAFTS.append(draft)
    return draft


@app.post("/inventory/{sku}/notes", operation_id="addInventoryNote", status_code=201)
def add_inventory_note(sku: str, payload: InventoryNote) -> dict[str, object]:
    INVENTORY_NOTES.setdefault(sku, []).append(payload.note)
    return {"sku": sku, "notes": INVENTORY_NOTES[sku]}

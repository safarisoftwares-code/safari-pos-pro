"""
Safari POS Pro - Purchase Orders router (multi-item)
Each PO has one supplier and N line items.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
from database import get_db
from models import PurchaseOrder, PurchaseOrderItem, Product
from schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItemResponse,
)
from auth import get_current_user

router = APIRouter()


# ============================================================
#  Helpers
# ============================================================

def _generate_po_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    count = db.query(PurchaseOrder).filter(
        PurchaseOrder.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ).count()
    return f"PO-{today}-{count + 1:04d}"


def _serialize_po(po: PurchaseOrder, items: List[PurchaseOrderItem]) -> dict:
    return {
        "id": po.id,
        "supplier": po.supplier,
        "notes": getattr(po, "notes", None),
        "status": po.status,
        "total_cost": po.total_cost,
        "created_at": po.created_at.isoformat(),
        "items": [
            {
                "id": it.id,
                "product_id": it.product_id,
                "product_name": it.product_name,
                "unit": it.unit,
                "quantity": it.quantity,
                "unit_cost": it.unit_cost,
                "line_total": it.line_total,
                "received": bool(it.received),
                "received_at": it.received_at.isoformat() if it.received_at else None,
            }
            for it in items
        ],
    }


# ============================================================
#  Endpoints
# ============================================================

@router.post("/")
async def create_po(
    po_data: PurchaseOrderCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a multi-item PO. One supplier, N items."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not po_data.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    supplier_name = (po_data.supplier or "").strip()
    if not supplier_name:
        raise HTTPException(status_code=400, detail="Supplier name is required")

    # Build item rows first (validate products)
    prepared_items = []
    total = 0.0
    for item in po_data.items:
        if item.quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity must be at least 1")
        if item.unit_cost < 0:
            raise HTTPException(status_code=400, detail="Unit cost cannot be negative")

        product = None
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")

        pname = product.name if product else "Unknown Product"
        punit = product.unit if product else None
        line_total = item.quantity * item.unit_cost
        total += line_total

        prepared_items.append({
            "product_id": product.id if product else None,
            "product_name": pname,
            "unit": punit,
            "quantity": item.quantity,
            "unit_cost": item.unit_cost,
            "line_total": line_total,
        })

    # Create PO header
    po = PurchaseOrder(
        supplier=supplier_name,
        product_name=prepared_items[0]["product_name"],  # legacy column, first item
        unit=prepared_items[0]["unit"],
        quantity=prepared_items[0]["quantity"],
        unit_cost=prepared_items[0]["unit_cost"],
        total_cost=total,
        status="pending",
        created_by=current_user.id,
    )
    db.add(po)
    db.flush()  # get po.id

    # Create items
    for pit in prepared_items:
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=pit["product_id"],
            product_name=pit["product_name"],
            unit=pit["unit"],
            quantity=pit["quantity"],
            unit_cost=pit["unit_cost"],
            line_total=pit["line_total"],
        ))

    db.commit()
    db.refresh(po)

    items = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po.id
    ).all()

    return _serialize_po(po, items)


@router.get("/")
async def list_pos(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all POs with their items nested."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    pos = db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).all()
    result = []
    for po in pos:
        items = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.purchase_order_id == po.id
        ).all()
        result.append(_serialize_po(po, items))
    return result


@router.get("/{po_id}")
async def get_po(
    po_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    items = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po.id
    ).all()
    return _serialize_po(po, items)


@router.post("/{po_id}/receive-item/{item_id}")
async def receive_item(
    po_id: int,
    item_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive ONE item from a PO. Updates stock + weighted-average cost for that product only."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot receive a cancelled PO")

    item = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.id == item_id,
        PurchaseOrderItem.purchase_order_id == po_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found on this PO")

    if item.received:
        return {"message": "Item already received", "item_id": item_id}

    # Update product stock + weighted-average cost
    if item.product_id:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            old_stock = product.stock or 0
            old_cost = product.cost or 0
            new_qty = item.quantity
            new_cost = item.unit_cost

            total_units = old_stock + new_qty
            if total_units > 0:
                product.cost = round(
                    ((old_stock * old_cost) + (new_qty * new_cost)) / total_units, 2
                )
            product.stock = total_units

    item.received = True
    item.received_at = datetime.now()

    # Recompute PO status
    remaining = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po_id,
        PurchaseOrderItem.received == False,
    ).count()
    po.status = "received" if remaining == 0 else "partial"

    db.commit()
    return {
        "message": "Item received",
        "item_id": item_id,
        "po_status": po.status,
    }


@router.post("/{po_id}/receive")
async def receive_all(
    po_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive ALL pending items on this PO in one action."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot receive a cancelled PO")

    items = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po_id,
        PurchaseOrderItem.received == False,
    ).all()

    count = 0
    for item in items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                old_stock = product.stock or 0
                old_cost = product.cost or 0
                new_qty = item.quantity
                new_cost = item.unit_cost
                total_units = old_stock + new_qty
                if total_units > 0:
                    product.cost = round(
                        ((old_stock * old_cost) + (new_qty * new_cost)) / total_units, 2
                    )
                product.stock = total_units

        item.received = True
        item.received_at = datetime.now()
        count += 1

    po.status = "received"
    db.commit()

    return {
        "message": f"Received {count} item(s)",
        "po_id": po_id,
        "items_received": count,
    }


@router.post("/{po_id}/cancel")
async def cancel_po(
    po_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a PO. Refuses if already received."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status == "received":
        raise HTTPException(status_code=400, detail="Cannot cancel a fully received PO")

    po.status = "cancelled"
    db.commit()
    return {"message": f"PO #{po_id} cancelled"}


@router.delete("/{po_id}")
async def delete_po(
    po_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanent delete. Admin only. Refuses if any item was received."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete POs")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    received_count = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po_id,
        PurchaseOrderItem.received == True,
    ).count()
    if received_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a PO with received items. Cancel it instead.",
        )

    db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == po_id
    ).delete()
    db.delete(po)
    db.commit()
    return {"message": f"PO #{po_id} deleted"}

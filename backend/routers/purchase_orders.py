from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import PurchaseOrder, Product
from auth import get_current_user
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter()


class PurchaseOrderCreate(BaseModel):
    supplier: str
    product_id: int
    quantity: int
    unit_cost: float


@router.post("/")
async def create_po(
    po_data: PurchaseOrderCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    product = db.query(Product).filter(Product.id == po_data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    total = po_data.quantity * po_data.unit_cost
    po = PurchaseOrder(
        supplier=po_data.supplier,
        product_name=product.name,
        unit=product.unit,
        quantity=po_data.quantity,
        unit_cost=po_data.unit_cost,
        total_cost=total,
        created_by=current_user.id,
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


@router.get("/")
async def get_pos(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).all()


@router.get("/by-date")
async def get_pos_by_date(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    pos = db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).all()

    grouped = {}
    for po in pos:
        date_key = po.created_at.strftime("%Y-%m-%d")
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append({
            "id": po.id,
            "supplier": po.supplier,
            "product_name": po.product_name,
            "unit": po.unit,
            "quantity": po.quantity,
            "unit_cost": po.unit_cost,
            "total_cost": po.total_cost,
            "status": po.status,
        })
    return grouped


@router.get("/by-date/{date}")
async def get_pos_for_date(
    date: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        start = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    end = start + timedelta(days=1)

    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end)
        .order_by(PurchaseOrder.created_at.desc())
        .all()
    )

    return [
        {
            "id": p.id,
            "supplier": p.supplier,
            "product_name": p.product_name,
            "unit": p.unit,
            "quantity": p.quantity,
            "unit_cost": p.unit_cost,
            "total_cost": p.total_cost,
            "status": p.status,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for p in pos
    ]


@router.put("/{po_id}/status")
async def update_po_status(
    po_id: int,
    status: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    old_status = po.status
    po.status = status

    new_stock_value = None

    if status == "received" and old_status != "received":
        product = db.query(Product).filter(
            Product.name == po.product_name,
            Product.unit == po.unit,
        ).first()

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product '{po.product_name}' ({po.unit}) not found.",
            )

        old_stock = product.stock
        old_cost = product.cost or 0
        new_qty = po.quantity
        new_cost = po.unit_cost

        total_old_value = old_stock * old_cost
        total_new_value = new_qty * new_cost
        total_units = old_stock + new_qty

        if total_units > 0:
            # Weighted-average cost
            product.cost = round((total_old_value + total_new_value) / total_units, 2)

        product.stock = total_units
        new_stock_value = product.stock

    db.commit()
    return {
        "message": f"PO marked as {status}",
        "product": po.product_name,
        "unit": po.unit,
        "new_stock": new_stock_value,
    }


@router.delete("/delete-day/{date}")
async def delete_pos_by_date(
    date: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete POs")

    try:
        start = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    end = start + timedelta(days=1)

    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end)
        .all()
    )
    count = len(pos)
    for po in pos:
        db.delete(po)

    db.commit()
    return {"message": f"Deleted {count} POs for {date}"}


@router.delete("/{po_id}")
async def delete_po(
    po_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete POs")

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    db.delete(po)
    db.commit()
    return {"message": f"PO #{po_id} deleted"}

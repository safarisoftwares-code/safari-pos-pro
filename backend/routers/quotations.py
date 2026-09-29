from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Quotation, QuotationItem, Product
from auth import get_current_user
from pydantic import BaseModel

router = APIRouter()


def generate_quote_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    count = db.query(Quotation).filter(Quotation.quote_no.like(f"QTE-{today}-%")).count()
    return f"QTE-{today}-{count + 1:04d}"


class QuoteItemIn(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class QuoteIn(BaseModel):
    items: list[QuoteItemIn]
    discount: float = 0
    customer_id: int | None = None
    notes: str = ""


@router.post("/")
async def create_quotation(
    data: QuoteIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subtotal = 0.0
    total_tax = 0.0
    items_data = []
    for it in data.items:
        product = db.query(Product).filter(Product.id == it.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {it.product_id} not found")
        line_total = it.quantity * it.unit_price
        rate = product.tax_rate or 0
        line_tax = line_total - (line_total / (1 + rate/100)) if rate > 0 else 0.0
        subtotal += line_total
        total_tax += line_tax
        items_data.append({
            "product_id": product.id,
            "product_name": product.name,
            "unit": product.unit,
            "quantity": it.quantity,
            "unit_price": it.unit_price,
            "tax_rate": rate,
            "tax_amount": line_tax,
            "total_price": line_total,
        })
    discount = data.discount or 0.0
    total = subtotal - discount

    q = Quotation(
        quote_no=generate_quote_no(db),
        customer_id=data.customer_id,
        cashier_id=current_user.id,
        cashier_name=current_user.name,
        subtotal=subtotal,
        tax_amount=total_tax,
        discount=discount,
        total_amount=total,
        notes=data.notes or None,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    for it in items_data:
        db.add(QuotationItem(quotation_id=q.id, **it))
    db.commit()
    return {"id": q.id, "quote_no": q.quote_no, "total_amount": total}


@router.get("/")
async def list_quotations(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    qs = (
        db.query(Quotation)
        .filter(Quotation.cashier_id == current_user.id)
        .order_by(Quotation.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": q.id,
            "quote_no": q.quote_no,
            "total_amount": q.total_amount,
            "cashier": q.cashier_name or "Unknown",
            "created_at": q.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for q in qs
    ]


@router.get("/{quote_id}")
async def get_quotation(quote_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Quotation).filter(Quotation.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if q.cashier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quotation")
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == q.id).all()
    return {
        "id": q.id,
        "quote_no": q.quote_no,
        "subtotal": q.subtotal,
        "tax_amount": q.tax_amount,
        "discount": q.discount,
        "total_amount": q.total_amount,
        "cashier": q.cashier_name,
        "created_at": q.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "notes": q.notes,
        "items": [
            {
                "product_name": i.product_name,
                "unit": i.unit,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "tax_rate": i.tax_rate,
                "tax_amount": i.tax_amount,
                "total_price": i.total_price,
            }
            for i in items
        ],
    }


@router.delete("/{quote_id}")
async def delete_quotation(quote_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Quotation).filter(Quotation.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if q.cashier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quotation")
    db.delete(q)
    db.commit()
    return {"message": f"Quotation {q.quote_no} deleted"}

@router.put("/{quote_id}")
async def update_quotation(
    quote_id: int,
    data: QuoteIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Quotation).filter(Quotation.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if q.cashier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quotation")

    # Delete old items
    db.query(QuotationItem).filter(QuotationItem.quotation_id == q.id).delete()

    # Recompute items from payload
    subtotal = 0.0
    total_tax = 0.0
    items_data = []
    for it in data.items:
        product = db.query(Product).filter(Product.id == it.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {it.product_id} not found")
        line_total = it.quantity * it.unit_price
        rate = product.tax_rate or 0
        line_tax = line_total - (line_total / (1 + rate/100)) if rate > 0 else 0.0
        subtotal += line_total
        total_tax += line_tax
        items_data.append({
            "product_id": product.id,
            "product_name": product.name,
            "unit": product.unit,
            "quantity": it.quantity,
            "unit_price": it.unit_price,
            "tax_rate": rate,
            "tax_amount": line_tax,
            "total_price": line_total,
        })

    discount = data.discount or 0.0
    total = subtotal - discount

    q.subtotal = subtotal
    q.tax_amount = total_tax
    q.discount = discount
    q.total_amount = total
    if data.notes is not None:
        q.notes = data.notes

    for it in items_data:
        db.add(QuotationItem(quotation_id=q.id, **it))
    db.commit()
    return {"id": q.id, "quote_no": q.quote_no, "total_amount": total, "updated": True}


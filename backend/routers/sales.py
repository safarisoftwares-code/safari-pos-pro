from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db, DB_PATH
from models import Sale, SaleItem, Product, User
from schemas import SaleCreate
from auth import get_current_user
from pydantic import BaseModel
import sqlite3

router = APIRouter()


def generate_receipt_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    count = db.query(Sale).filter(Sale.receipt_no.like(f"INV-{today}-%")).count()
    return f"INV-{today}-{count + 1:04d}"


def _write_tax_ledger(receipt_no: str, items: list, payment_method: str, cashier: str, when: datetime):
    """Write tax records for audit. Same format as v3.0 (Phase 2 will archive)."""
    with sqlite3.connect(DB_PATH) as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO tax_ledger
                (receipt_no, product_name, quantity, unit_price, tax_rate,
                 tax_amount, payment_method, cashier, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_no,
                    item["name"],
                    item["quantity"],
                    item["unit_price"],
                    item["tax_rate"],
                    item["tax_amount"],
                    payment_method,
                    cashier,
                    when.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.commit()


@router.post("/")
async def create_sale(
    sale_data: SaleCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subtotal = 0.0
    total_tax = 0.0
    sale_items_data = []

    # Validate + compute
    for item in sale_data.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name} (have {product.stock})",
            )

        line_total = item.quantity * item.unit_price

        # INCLUSIVE tax: tax = price - (price / (1 + rate))
        if product.tax_rate and product.tax_rate > 0:
            rate = product.tax_rate / 100
            line_tax = line_total - (line_total / (1 + rate))
        else:
            line_tax = 0.0

        subtotal += line_total
        total_tax += line_tax

        sale_items_data.append({
            "product": product,
            "name": product.name,
            "unit": product.unit,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "tax_rate": product.tax_rate or 0,
            "tax_amount": line_tax,
            "total_price": line_total,
        })

    discount = sale_data.discount or 0.0
    total = subtotal - discount

    # Create sale
    sale = Sale(
        receipt_no=generate_receipt_no(db),
        customer_id=sale_data.customer_id,
        cashier_id=current_user.id,
        cashier_name=current_user.name,
        subtotal=subtotal,
        tax_amount=total_tax,
        discount=discount,
        total_amount=total,
        payment_method=sale_data.payment_method,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)

    # Create sale items + decrement stock
    for item in sale_items_data:
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item["product"].id,
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            tax_rate=item["tax_rate"],
            tax_amount=item["tax_amount"],
            total_price=item["total_price"],
        ))
        item["product"].stock -= item["quantity"]

    db.commit()

    # Write tax ledger
    _write_tax_ledger(
        sale.receipt_no,
        sale_items_data,
        sale.payment_method,
        current_user.name,
        sale.created_at,
    )

    return {
        "id": sale.id,
        "receipt_no": sale.receipt_no,
        "subtotal": subtotal,
        "tax_amount": total_tax,
        "discount": discount,
        "total_amount": total,
        "payment_method": sale.payment_method,
        "created_at": sale.created_at.isoformat(),
        "items": [
            {
                "name": item["name"],
                "unit": item["unit"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "tax_rate": item["tax_rate"],
                "tax_amount": item["tax_amount"],
                "total_price": item["total_price"],
            }
            for item in sale_items_data
        ],
    }


@router.get("/today")
async def get_today_sales(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if current_user.role in ["admin", "manager"]:
        sales = db.query(Sale).filter(Sale.created_at >= today).all()
    else:
        sales = db.query(Sale).filter(
            Sale.created_at >= today,
            Sale.cashier_id == current_user.id,
        ).all()

    return {
        "count": len(sales),
        "total_amount": sum(s.total_amount for s in sales),
        "sales": [
            {
                "receipt_no": s.receipt_no,
                "subtotal": s.subtotal,
                "tax_amount": s.tax_amount,
                "total_amount": s.total_amount,
                "payment_method": s.payment_method,
                "created_at": s.created_at.strftime("%H:%M:%S"),
                "cashier": s.cashier_name or "Unknown",
            }
            for s in sales
        ],
    }


@router.get("/all")
async def get_all_sales(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    sales = db.query(Sale).order_by(Sale.created_at.desc()).limit(100).all()

    return [
        {
            "receipt_no": s.receipt_no,
            "subtotal": s.subtotal,
            "tax_amount": s.tax_amount,
            "total_amount": s.total_amount,
            "payment_method": s.payment_method,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "cashier": s.cashier_name or "Unknown",
        }
        for s in sales
    ]


@router.get("/daily-close")
async def daily_close(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if current_user.role in ["admin", "manager"]:
        sales = db.query(Sale).filter(Sale.created_at >= today).all()
    else:
        sales = db.query(Sale).filter(
            Sale.created_at >= today,
            Sale.cashier_id == current_user.id,
        ).all()

    cash_total = sum(s.total_amount for s in sales if s.payment_method == "cash")
    mpesa_total = sum(s.total_amount for s in sales if s.payment_method == "mpesa")
    card_total = sum(s.total_amount for s in sales if s.payment_method == "card")
    credit_total = sum(s.total_amount for s in sales if s.payment_method == "credit")
    total = sum(s.total_amount for s in sales)

    return {
        "date": today.strftime("%Y-%m-%d"),
        "total_transactions": len(sales),
        "cash_total": cash_total,
        "mpesa_total": mpesa_total,
        "card_total": card_total,
        "credit_total": credit_total,
        "grand_total": total,
    }


@router.get("/history")
async def receipt_history(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role in ["admin", "manager"]:
        sales = db.query(Sale).order_by(Sale.created_at.desc()).limit(50).all()
    else:
        sales = db.query(Sale).filter(
            Sale.cashier_id == current_user.id,
        ).order_by(Sale.created_at.desc()).limit(50).all()

    result = []
    for sale in sales:
        items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
        result.append({
            "receipt_no": sale.receipt_no,
            "total_amount": sale.total_amount,
            "subtotal": sale.subtotal,
            "tax_amount": sale.tax_amount,
            "discount": sale.discount,
            "payment_method": sale.payment_method,
            "created_at": sale.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "cashier": sale.cashier_name or "Deleted User",
            "items": [
                {
                    "name": (
                        db.query(Product).filter(Product.id == item.product_id).first().name
                        if db.query(Product).filter(Product.id == item.product_id).first()
                        else "Unknown"
                    ),
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "tax_rate": item.tax_rate or 0,
                    "tax_amount": item.tax_amount or 0,
                    "total_price": item.total_price,
                }
                for item in items
            ],
        })
    return result


@router.get("/last-receipt")
async def get_last_receipt(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role in ["admin", "manager"]:
        sale = db.query(Sale).order_by(Sale.created_at.desc()).first()
    else:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sale = db.query(Sale).filter(
            Sale.cashier_id == current_user.id,
            Sale.created_at >= today,
        ).order_by(Sale.created_at.desc()).first()

    if not sale:
        return {"message": "No receipt found"}

    items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()

    return {
        "receipt_no": sale.receipt_no,
        "total_amount": sale.total_amount,
        "subtotal": sale.subtotal,
        "tax_amount": sale.tax_amount,
        "discount": sale.discount,
        "payment_method": sale.payment_method,
        "created_at": sale.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "cashier": sale.cashier_name or "Deleted User",
        "items": [
            {
                "name": (
                    db.query(Product).filter(Product.id == item.product_id).first().name
                    if db.query(Product).filter(Product.id == item.product_id).first()
                    else "Unknown"
                ),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
            for item in items
        ],
    }


@router.delete("/receipt/{receipt_no}")
async def delete_receipt(
    receipt_no: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete receipts")

    sale = db.query(Sale).filter(Sale.receipt_no == receipt_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Receipt not found")

    db.query(SaleItem).filter(SaleItem.sale_id == sale.id).delete()
    db.delete(sale)
    db.commit()

    return {"message": f"Receipt {receipt_no} deleted. Tax records preserved."}


@router.delete("/delete-before/{date}")
async def delete_sales_before(
    date: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete sales")

    try:
        cutoff = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    sales_to_delete = db.query(Sale).filter(Sale.created_at < cutoff).all()
    count = len(sales_to_delete)

    for sale in sales_to_delete:
        db.query(SaleItem).filter(SaleItem.sale_id == sale.id).delete()
        db.delete(sale)

    db.commit()
    return {"message": f"Deleted {count} receipts before {date}. Tax records preserved."}



# ============================================================
#  QR Code for receipt
# ============================================================

@router.get("/receipt-qr/{receipt_no}")
async def receipt_qr(receipt_no: str, db: Session = Depends(get_db)):
    # Public endpoint — no auth required (browsers can't send auth on <img src>)
    """Return a QR code PNG containing the receipt summary."""
    import io
    import qrcode
    from fastapi.responses import Response

    # Get the sale
    sale = db.query(Sale).filter(Sale.receipt_no == receipt_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # Get business info
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings WHERE key IN ('store_name','reg_no','business_tax_pin')")
        settings = dict(cur.fetchall())

    store_name = settings.get("store_name", "") or "MAIN"
    reg_no = settings.get("reg_no", "") or ""
    tax_pin = settings.get("business_tax_pin", "") or ""

    # Build QR text
    qr_text = (
        f"PIN: {tax_pin} | "
        f"SAFARI POS RECEIPT | "
        f"{sale.receipt_no} | "
        f"{sale.created_at.strftime('%Y-%m-%d %H:%M')} | "
        f"{store_name} {reg_no} | "
        f"{sale.cashier_name or 'Unknown'} | "
        f"KSh {sale.total_amount:.2f} | "
        f"Tax KSh {sale.tax_amount:.2f} | "
        f"{sale.payment_method.upper()}"
    )

    # Generate QR
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=15,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Return as PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")



# ============================================================
#  Barcode for receipt serial
# ============================================================

@router.get("/receipt-barcode/{receipt_no}")
async def receipt_barcode(receipt_no: str, db: Session = Depends(get_db)):
    """Public endpoint — returns a barcode PNG with the receipt number."""
    import io
    try:
        import barcode
        from barcode.writer import ImageWriter
    except ImportError:
        raise HTTPException(status_code=500, detail="python-barcode not installed")

    # Generate Code128 barcode
    try:
        CODE128 = barcode.get_barcode_class("code128")
        code = CODE128(receipt_no, writer=ImageWriter())

        buf = io.BytesIO()
        # write() writes a PNG by default; options control size
        code.write(buf, options={
            "module_width": 0.3,
            "module_height": 8.0,
            "font_size": 0,
            "text_distance": 0,
            "quiet_zone": 1.0,
            "dpi": 300,
        })
        buf.seek(0)
        from fastapi.responses import Response
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Barcode generation failed: {e}")



# ============================================================
#  M-Pesa Relay Flow: pending / confirm / fail
# ============================================================

class PendingSaleItem(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class PendingSaleRequest(BaseModel):
    items: list[PendingSaleItem]
    discount: float = 0
    phone_number: str = ""
    customer_id: int | None = None


@router.post("/pending")
async def create_pending_sale(
    req: PendingSaleRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a pending M-Pesa sale. Does NOT decrement stock or write tax ledger.
    Called when cashier sends an STK push. Sale is finalized only on confirm.
    """
    subtotal = 0.0
    total_tax = 0.0
    items_data = []

    for item in req.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")

        line_total = item.quantity * item.unit_price
        if product.tax_rate and product.tax_rate > 0:
            rate = product.tax_rate / 100
            line_tax = line_total - (line_total / (1 + rate))
        else:
            line_tax = 0.0

        subtotal += line_total
        total_tax += line_tax
        items_data.append({
            "product": product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "tax_rate": product.tax_rate or 0,
            "tax_amount": line_tax,
            "total_price": line_total,
        })

    discount = req.discount or 0.0
    total = subtotal - discount

    sale = Sale(
        receipt_no=generate_receipt_no(db),
        customer_id=req.customer_id,
        cashier_id=current_user.id,
        cashier_name=current_user.name,
        subtotal=subtotal,
        tax_amount=total_tax,
        discount=discount,
        total_amount=total,
        payment_method="mpesa",
        payment_ref=req.phone_number,
        status="pending",
        payment_status="pending",
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)

    # Save items as pending (they'll be validated/deducted on confirm)
    for item in items_data:
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item["product"].id,
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            tax_rate=item["tax_rate"],
            tax_amount=item["tax_amount"],
            total_price=item["total_price"],
        ))
    db.commit()

    return {
        "id": sale.id,
        "receipt_no": sale.receipt_no,
        "total_amount": total,
        "payment_status": "pending",
        "message": "Sale created. Awaiting M-Pesa confirmation.",
    }


@router.post("/{sale_id}/confirm")
async def confirm_sale(
    sale_id: int,
    mpesa_receipt: str = "",
    db: Session = Depends(get_db),
):
    """
    Called by the M-Pesa poller when Safaricom confirms a payment.
    Decrements stock, writes tax ledger, marks sale as paid.
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    if sale.payment_status == "paid":
        return {"message": "Sale already paid", "sale_id": sale_id}

    # Decrement stock for each item
    items = db.query(SaleItem).filter(SaleItem.sale_id == sale_id).all()
    items_for_ledger = []
    for item in items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock -= item.quantity
        items_for_ledger.append({
            "name": product.name if product else "Unknown",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "tax_rate": item.tax_rate or 0,
            "tax_amount": item.tax_amount or 0,
        })

    # Write tax ledger
    _write_tax_ledger(
        sale.receipt_no,
        items_for_ledger,
        sale.payment_method,
        sale.cashier_name or "Unknown",
        sale.created_at,
    )

    # Update sale
    sale.payment_status = "paid"
    sale.status = "completed"
    sale.mpesa_receipt = mpesa_receipt or None
    sale.paid_at = datetime.now()
    db.commit()

    return {
        "message": "Sale confirmed and paid",
        "sale_id": sale_id,
        "receipt_no": sale.receipt_no,
        "mpesa_receipt": mpesa_receipt,
    }


@router.post("/{sale_id}/fail")
async def fail_sale(
    sale_id: int,
    reason: str = "failed",
    db: Session = Depends(get_db),
):
    """
    Mark a pending sale as failed or timeout. No stock change.
    Called by the M-Pesa poller or frontend on error/timeout.
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    if sale.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Cannot fail a paid sale")

    sale.payment_status = reason  # "failed" or "timeout"
    sale.status = reason
    db.commit()

    return {
        "message": f"Sale marked as {reason}",
        "sale_id": sale_id,
        "receipt_no": sale.receipt_no,
    }


@router.get("/{sale_id}/status")
async def get_sale_status(
    sale_id: int,
    db: Session = Depends(get_db),
):
    """Frontend polls this to check if the sale has been confirmed."""
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    return {
        "sale_id": sale.id,
        "receipt_no": sale.receipt_no,
        "payment_status": sale.payment_status or "paid",
        "mpesa_receipt": sale.mpesa_receipt,
        "paid_at": sale.paid_at.strftime("%Y-%m-%d %H:%M:%S") if sale.paid_at else None,
    }


# ============================================================
#  Cleanup: delete failed/timeout M-Pesa sales older than 7 days
# ============================================================
@router.post("/cleanup-pending")
async def cleanup_pending_sales(
    days: int = 7,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Admin-only. Deletes orphaned pending-flow sales that failed or timed out.
    Never touches 'paid', 'pending' (still-active), or 'completed' sales.
    Stock was never deducted for these, so no inventory correction is needed.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can cleanup sales")

    cutoff = datetime.now() - timedelta(days=days)

    # Find candidates
    candidates = (
        db.query(Sale)
        .filter(
            Sale.payment_status.in_(["failed", "timeout"]),
            Sale.created_at < cutoff,
        )
        .all()
    )

    sale_ids = [s.id for s in candidates]
    if not sale_ids:
        return {"deleted_sales": 0, "deleted_items": 0, "message": "Nothing to clean up"}

    # Delete items first, then sales
    items_deleted = (
        db.query(SaleItem)
        .filter(SaleItem.sale_id.in_(sale_ids))
        .delete(synchronize_session=False)
    )
    sales_deleted = (
        db.query(Sale)
        .filter(Sale.id.in_(sale_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "deleted_sales": int(sales_deleted),
        "deleted_items": int(items_deleted),
        "cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"Cleaned up {sales_deleted} sale(s) and {items_deleted} item(s)",
    }


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from database import get_db
from models import Sale, SaleItem, Product
from auth import get_current_user

router = APIRouter()


@router.get("/overview")
async def analytics_overview(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    thirty_days_ago = datetime.now() - timedelta(days=30)

    # Top sellers (last 30 days)
    top_sellers = (
        db.query(
            Product.name,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.sum(SaleItem.total_price).label("total_revenue"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= thirty_days_ago)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(5)
        .all()
    )

    # Worst sellers — v4.0 FIX: only products that actually sold (qty > 0)
    worst_sellers = (
        db.query(
            Product.name,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.sum(SaleItem.total_price).label("total_revenue"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= thirty_days_ago)
        .group_by(Product.id, Product.name)
        .having(func.sum(SaleItem.quantity) > 0)
        .order_by(func.sum(SaleItem.quantity).asc())
        .limit(5)
        .all()
    )

    # Profit analysis
    profit_data = []
    all_products = db.query(Product).filter(Product.is_active == True).all()
    for p in all_products:
        if p.cost and p.cost > 0:
            tax_rate = p.tax_rate or 16
            net_selling = p.price / (1 + tax_rate / 100)
            profit = net_selling - p.cost
            margin = (profit / net_selling * 100) if net_selling > 0 else 0
            profit_data.append({
                "name": p.name,
                "profit": round(profit, 2),
                "margin": round(margin, 1),
                "stock": p.stock,
            })

    profit_champions = sorted(profit_data, key=lambda x: x["profit"], reverse=True)[:5]
    loss_makers = [p for p in profit_data if p["profit"] < 0][:5]

    # Slow movers — high stock, low 30-day sales
    slow_movers = []
    for p in all_products:
        sold_qty = (
            db.query(func.sum(SaleItem.quantity))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(SaleItem.product_id == p.id, Sale.created_at >= thirty_days_ago)
            .scalar()
            or 0
        )
        if p.stock > 50 and sold_qty < 10:
            slow_movers.append({
                "name": p.name,
                "stock": p.stock,
                "sold_30days": int(sold_qty),
            })
    slow_movers = slow_movers[:5]

    return {
        "top_sellers": [
            {"name": t[0], "qty": int(t[1]), "revenue": round(t[2], 2)}
            for t in top_sellers
        ],
        "worst_sellers": [
            {"name": t[0], "qty": int(t[1]), "revenue": round(t[2], 2)}
            for t in worst_sellers
        ],
        "profit_champions": profit_champions,
        "loss_makers": loss_makers,
        "slow_movers": slow_movers,
    }


@router.get("/expiry")
async def expiry_report(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    today = datetime.now().date()
    products = (
        db.query(Product)
        .filter(Product.expiry_date.isnot(None), Product.is_active == True)
        .all()
    )

    expired = []
    expiring = []

    for p in products:
        try:
            expiry = datetime.strptime(p.expiry_date, "%Y-%m-%d").date()
            days_left = (expiry - today).days
            if days_left < 0:
                expired.append({
                    "name": p.name,
                    "expiry": p.expiry_date,
                    "days": days_left,
                    "stock": p.stock,
                })
            elif days_left <= 7:
                expiring.append({
                    "name": p.name,
                    "expiry": p.expiry_date,
                    "days": days_left,
                    "stock": p.stock,
                })
        except (ValueError, TypeError):
            pass

    return {"expired": expired, "expiring_soon": expiring}

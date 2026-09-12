from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Sale, Product
from auth import get_current_user

router = APIRouter()


@router.get("/daily")
async def daily_report(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sales = db.query(Sale).filter(Sale.created_at >= today).all()
    total = sum(s.total_amount for s in sales)

    return {
        "total_transactions": len(sales),
        "total_sales": total,
        "average_sale": total / len(sales) if sales else 0,
    }


@router.get("/low-stock")
async def low_stock(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    return (
        db.query(Product)
        .filter(Product.stock <= Product.low_stock_alert, Product.is_active == True)
        .all()
    )


@router.get("/profit")
async def profit_report(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Profit per product with inclusive-tax math.

    Inclusive tax: price includes tax, so:
      net_selling = price / (1 + rate/100)
      gross_profit = net_selling - cost
      margin = gross_profit / net_selling * 100
    """
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    products = db.query(Product).filter(Product.is_active == True).all()

    profit_data = []
    for product in products:
        if product.cost and product.cost > 0:
            tax_rate = product.tax_rate or 16
            net_selling = product.price / (1 + tax_rate / 100)
            cost = product.cost or 0
            gross_profit = net_selling - cost
            profit_margin = (gross_profit / net_selling * 100) if net_selling > 0 else 0

            profit_data.append({
                "product": product.name,
                "selling_price": product.price,
                "tax_rate": tax_rate,
                "net_selling": round(net_selling, 2),
                "cost": product.cost,
                "gross_profit": round(gross_profit, 2),
                "profit_margin": round(profit_margin, 1),
            })

    return profit_data

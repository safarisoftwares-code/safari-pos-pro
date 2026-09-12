from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import Product, Category
from schemas import ProductCreate, ProductResponse, CategoryCreate, CategoryResponse
from auth import get_current_user

router = APIRouter()


# ============================================================
#  Categories
# ============================================================

@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Category).all()


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    category_data: CategoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Category).filter(Category.name == category_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")

    category = Category(name=category_data.name, description=category_data.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete categories")

    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(category)
    db.commit()
    return {"message": "Category deleted"}


# ============================================================
#  Products
# ============================================================

@router.get("", response_model=List[ProductResponse])
async def get_products(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.is_active == True).all()


@router.post("", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    product = Product(**product_data.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    product_data: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    v4.0 FIX: Updates ALL product fields when present.
    Previously only name/unit/price/tax_rate/stock were saved.
    Now category_id, cost, barcode, expiry_date, low_stock_alert
    are also persisted.
    """
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    editable_fields = [
        "name", "unit", "barcode", "category_id",
        "price", "cost", "stock", "low_stock_alert",
        "tax_rate", "expiry_date",
    ]

    for field in editable_fields:
        if field in product_data:
            setattr(product, field, product_data[field])

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete products")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Soft delete: keeps sales history intact
    product.is_active = False
    db.commit()
    return {"message": "Product deactivated"}


@router.put("/{product_id}/stock")
async def adjust_stock(
    product_id: int,
    adjustment: int,
    reason: str = "manual",
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adjust stock manually (positive = add, negative = remove)."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    new_stock = product.stock + adjustment
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")

    old_stock = product.stock
    product.stock = new_stock
    db.commit()
    db.refresh(product)

    return {
        "message": "Stock adjusted",
        "product": product.name,
        "old_stock": old_stock,
        "adjustment": adjustment,
        "new_stock": product.stock,
        "reason": reason,
    }

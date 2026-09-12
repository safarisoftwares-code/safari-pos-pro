from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ============================================================
#  Users
# ============================================================

class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    password: str
    phone: Optional[str] = None
    role: str = "cashier"


class UserLogin(BaseModel):
    email: str  # accepts email OR phone
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ============================================================
#  Categories & Products
# ============================================================

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    unit: Optional[str] = None
    category_id: Optional[int] = None
    price: float
    cost: Optional[float] = None
    stock: int = 0
    low_stock_alert: int = 5
    tax_rate: float = 0
    expiry_date: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    barcode: Optional[str] = None
    unit: Optional[str] = None
    category_id: Optional[int] = None
    price: float
    tax_rate: Optional[float] = 0
    expiry_date: Optional[str] = None
    stock: int
    low_stock_alert: int
    class Config:
        from_attributes = True


# ============================================================
#  Customers
# ============================================================

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    credit_limit: float = 0


# ============================================================
#  Sales
# ============================================================

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class SaleCreate(BaseModel):
    customer_id: Optional[int] = None
    items: List[SaleItemCreate]
    payment_method: str
    discount: float = 0

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True, index=True)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="cashier")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    sales = relationship("Sale", back_populates="cashier")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    barcode = Column(String, unique=True, nullable=True)
    unit = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    price = Column(Float, nullable=False)
    cost = Column(Float, nullable=True)
    stock = Column(Integer, default=0)
    low_stock_alert = Column(Integer, default=5)
    tax_rate = Column(Float, default=0)
    expiry_date = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    category = relationship("Category", back_populates="products")
    sale_items = relationship("SaleItem", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=True)
    credit_limit = Column(Float, default=0)
    credit_balance = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.now)
    sales = relationship("Sale", back_populates="customer")


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    receipt_no = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    # IMPORTANT: ondelete="SET NULL" so user delete never orphans sales.
    # cashier_name keeps history even after user is removed.
    cashier_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cashier_name = Column(String, nullable=True)
    subtotal = Column(Float, default=0)
    tax_amount = Column(Float, default=0)
    discount = Column(Float, default=0)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False)
    payment_ref = Column(String, nullable=True)
    status = Column(String, default="completed")
    # v4.0 M-Pesa relay fields
    payment_status = Column(String, default="paid")  # pending | paid | failed | timeout | completed
    mpesa_checkout_id = Column(String, nullable=True)  # Safaricom CheckoutRequestID
    mpesa_receipt = Column(String, nullable=True)  # M-Pesa receipt number from callback
    paid_at = Column(DateTime, nullable=True)  # when payment was confirmed
    created_at = Column(DateTime, default=datetime.now)
    customer = relationship("Customer", back_populates="sales")
    cashier = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0)
    tax_amount = Column(Float, default=0)
    total_price = Column(Float, nullable=False)
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    supplier = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    status = Column(String, default="pending")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ====================================================================
# v4.0 PRO - PHASE 2 (Tax Ledger v2) will add these tables:
#   - tax_ledger            (live, rolling 12 months)
#   - tax_ledger_archive    (gzip JSON per month, up to 5 years)
#   - tax_ledger_purged     (permanent manifest with SHA-256 chain)
# For now, tax_ledger is created via raw SQL in routers/sales.py
# (same as v3.0) so the transition to v2 is seamless.
# ====================================================================


# ====================================================================
#  Suppliers — registry for Purchase Orders
# ====================================================================
class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    kra_pin = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

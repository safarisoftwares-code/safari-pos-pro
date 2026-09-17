"""
Safari POS Pro - Suppliers router
CRUD for the supplier registry used by Purchase Orders.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import Supplier
from schemas import SupplierCreate, SupplierUpdate, SupplierResponse
from auth import get_current_user

router = APIRouter()


@router.get("/", response_model=List[SupplierResponse])
async def list_suppliers(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active suppliers, alphabetically."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return (
        db.query(Supplier)
        .filter(Supplier.is_active == True)
        .order_by(Supplier.name.asc())
        .all()
    )


@router.post("/", response_model=SupplierResponse)
async def create_supplier(
    data: SupplierCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Supplier name is required")

    existing = db.query(Supplier).filter(Supplier.name == name).first()
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=400, detail="Supplier already exists")
        # Reactivate a soft-deleted supplier with the same name
        existing.phone = data.phone
        existing.email = data.email
        existing.address = data.address
        existing.kra_pin = data.kra_pin
        existing.notes = data.notes
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    supplier = Supplier(
        name=name,
        phone=data.phone,
        email=data.email,
        address=data.address,
        kra_pin=data.kra_pin,
        notes=data.notes,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Supplier name cannot be empty")
        # Ensure uniqueness if name changed
        if new_name != supplier.name:
            conflict = db.query(Supplier).filter(
                Supplier.name == new_name, Supplier.id != supplier_id
            ).first()
            if conflict:
                raise HTTPException(status_code=400, detail="Another supplier already uses that name")
        supplier.name = new_name

    if data.phone is not None:
        supplier.phone = data.phone
    if data.email is not None:
        supplier.email = data.email
    if data.address is not None:
        supplier.address = data.address
    if data.kra_pin is not None:
        supplier.kra_pin = data.kra_pin
    if data.notes is not None:
        supplier.notes = data.notes

    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft delete — keeps the name available for historical POs."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    supplier.is_active = False
    db.commit()
    return {"message": f"Supplier '{supplier.name}' deactivated"}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import User
from schemas import UserCreate, UserResponse
from auth import hash_password, get_current_user

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def get_users(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == "admin":
        return db.query(User).filter(User.is_active == True).all()
    elif current_user.role == "manager":
        return db.query(User).filter(User.is_active == True, User.role == "cashier").all()
    else:
        raise HTTPException(status_code=403, detail="Only admin or manager can view users")


@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create users")

    email = user_data.email.strip() if user_data.email and user_data.email.strip() else None
    phone = user_data.phone.strip() if user_data.phone and user_data.phone.strip() else None

    if not email and not phone:
        raise HTTPException(status_code=400, detail="Either Email or Phone number is required")

    # Auto-generate hidden email for phone-only users
    if not email and phone:
        email = f"{phone}@safari-pos.local"

    # Re-activate a soft-deleted user with same email/phone
    existing = None
    if email:
        existing = db.query(User).filter(User.email == email).first()
    if not existing and phone:
        existing = db.query(User).filter(User.phone == phone).first()

    if existing:
        if existing.is_active:
            raise HTTPException(status_code=400, detail="Email or phone already registered")
        # Reactivate
        existing.name = user_data.name
        existing.password_hash = hash_password(user_data.password)
        existing.email = email
        existing.phone = phone
        existing.role = user_data.role
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    user = User(
        name=user_data.name,
        email=email,
        password_hash=hash_password(user_data.password),
        phone=phone,
        role=user_data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanent delete.

    Sales keep working because:
      - The FK cashier_id is set to NULL automatically (ondelete="SET NULL")
      - Sales store cashier_name, which is preserved forever
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete users")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
    if user.role == "admin" and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only admin account")

    # Null out cashier_id in sales before delete (belt + suspenders with the FK rule)
    from models import Sale
    db.query(Sale).filter(Sale.cashier_id == user_id).update({"cashier_id": None})

    db.delete(user)
    db.commit()
    return {"message": "User permanently deleted. Sales preserved via cashier_name."}


@router.put("/{user_id}/admin-edit")
async def admin_edit_user(
    user_id: int,
    data: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only admin or manager can edit users")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "manager" and user.role != "cashier":
        raise HTTPException(status_code=403, detail="Managers can only edit cashiers")

    if "name" in data and data["name"]:
        user.name = data["name"]

    if "email" in data and data["email"]:
        existing = db.query(User).filter(User.email == data["email"], User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = data["email"]

    if "phone" in data and data["phone"]:
        existing_phone = db.query(User).filter(User.phone == data["phone"], User.id != user_id).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone already in use")
        user.phone = data["phone"]

    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])

    if "role" in data and data["role"]:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admin can change roles")
        user.role = data["role"]

    db.commit()
    db.refresh(user)
    return {"message": "User updated", "user_id": user.id}


@router.put("/me")
async def update_my_profile(
    data: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "name" in data and data["name"]:
        current_user.name = data["name"]

    if "email" in data and data["email"]:
        existing = db.query(User).filter(User.email == data["email"], User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = data["email"]

    if "phone" in data and data["phone"]:
        existing = db.query(User).filter(User.phone == data["phone"], User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone already in use")
        current_user.phone = data["phone"]

    if "password" in data and data["password"]:
        current_user.password_hash = hash_password(data["password"])

    db.commit()
    db.refresh(current_user)
    return {"message": "Profile updated"}

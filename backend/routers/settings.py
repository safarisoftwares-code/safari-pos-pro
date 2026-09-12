from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user, hash_password
from models import Product, User
import sqlite3
import os
import secrets
import hashlib
import shutil
from datetime import datetime

router = APIRouter()


def get_setting(key):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
    return result[0] if result else None


def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


@router.get("/")
async def get_settings(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "default_tax_rate": float(get_setting("default_tax_rate") or 16),
        "business_name": get_setting("business_name") or "My Business",
        "business_po_box": get_setting("business_po_box") or "",
        "business_location": get_setting("business_location") or "",
        "business_phone": get_setting("business_phone") or "",
        "business_tax_pin": get_setting("business_tax_pin") or "",
        "receipt_footer": get_setting("receipt_footer") or "Thank you! Karibu Tena!",
        "mpesa_enabled": get_setting("mpesa_enabled") or "false",
        "mpesa_consumer_key": get_setting("mpesa_consumer_key") or "",
        "mpesa_consumer_secret": get_setting("mpesa_consumer_secret") or "",
        "mpesa_passkey": get_setting("mpesa_passkey") or "",
        "mpesa_shortcode": get_setting("mpesa_shortcode") or "",
        "block_expired": get_setting("block_expired") or "false",
        "backup_location": get_setting("backup_location") or "",
        "warn_expiring": get_setting("warn_expiring") or "false",
    }


@router.put("/tax-rate")
async def update_tax_rate(rate: float, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can update tax rate")

    set_setting("default_tax_rate", str(rate))

    products = db.query(Product).all()
    for product in products:
        product.tax_rate = rate

    db.commit()
    return {"message": "Tax rate updated"}


@router.put("/business")
async def update_business_info(data: dict, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can update settings")

    editable_keys = [
        "business_name", "business_po_box", "business_location",
        "business_phone", "business_tax_pin", "receipt_footer",
        "block_expired", "warn_expiring", "backup_location",
        "mpesa_enabled", "mpesa_consumer_key", "mpesa_consumer_secret",
        "mpesa_passkey", "mpesa_shortcode",
    ]

    for key in editable_keys:
        if key in data:
            set_setting(key, str(data[key]))

    return {"message": "Settings updated"}


@router.post("/reset-demo")
async def reset_demo_data(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can reset demo data")

    backup_dir = os.path.join(os.path.dirname(DB_PATH), "..", "backups")
    backup_dir = os.path.abspath(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)

    backup_name = f"safaripos_before_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(DB_PATH, backup_path)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for table in ["sale_items", "sales", "tax_ledger", "purchase_orders",
                      "products", "categories", "customers"]:
            try:
                cursor.execute(f"DELETE FROM {table}")
            except Exception as e:
                print(f"[reset-demo] warning clearing {table}: {e}")
        cursor.execute("DELETE FROM users WHERE role != 'admin'")
        conn.commit()

    return {
        "message": "Demo data reset. Admin and settings preserved.",
        "backup_created": backup_path,
    }


# ============================================================
#  Recovery code (one-time use, hashed)
# ============================================================

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@router.post("/generate-recovery-code")
async def generate_recovery_code(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin")

    parts = [secrets.token_hex(2).upper() for _ in range(3)]
    code = "SAFARI-" + "-".join(parts)

    set_setting("recovery_code_hash", _hash_code(code))
    set_setting("recovery_code_used", "false")

    return {
        "message": "Recovery code generated. WRITE IT DOWN NOW — it will not be shown again!",
        "code": code,
    }


@router.post("/verify-recovery-code")
async def verify_recovery_code(data: dict, db: Session = Depends(get_db)):
    code = (data.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    stored_hash = get_setting("recovery_code_hash")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="No recovery code set")

    if _hash_code(code) != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid recovery code")

    return {"valid": True}


@router.post("/reset-password-with-code")
async def reset_password_with_code(data: dict, db: Session = Depends(get_db)):
    code = (data.get("code") or "").strip().upper()
    new_password = data.get("new_password") or ""
    target_email = (data.get("email") or "").strip()

    if not code or not new_password or not target_email:
        raise HTTPException(status_code=400, detail="Code, email, and new password required")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    stored_hash = get_setting("recovery_code_hash")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="No recovery code set")

    if get_setting("recovery_code_used") == "true":
        raise HTTPException(status_code=400, detail="Recovery code already used")

    if _hash_code(code) != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid recovery code")

    user = db.query(User).filter(
        ((User.email == target_email) | (User.phone == target_email)),
        User.role == "admin",
        User.is_active == True,
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Admin account not found")

    user.password_hash = hash_password(new_password)
    db.commit()

    set_setting("recovery_code_used", "true")
    return {"message": "Password reset successful. Login with new password."}

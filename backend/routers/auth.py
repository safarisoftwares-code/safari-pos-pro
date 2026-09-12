from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User
from schemas import UserCreate, UserLogin, Token
from auth import hash_password, verify_password, create_access_token

router = APIRouter()


def _normalize_phone(raw: str) -> list:
    """Return candidate phone formats to try during login."""
    cleaned = "".join(c for c in raw if c.isdigit())
    candidates = {cleaned}

    if cleaned.startswith("0"):
        candidates.add(cleaned[1:])           # 0741676521 -> 741676521
        candidates.add("254" + cleaned[1:])   # 0741676521 -> 254741676521
    elif cleaned.startswith("254"):
        candidates.add("0" + cleaned[3:])     # 254741676521 -> 0741676521
        candidates.add(cleaned[3:])           # 254741676521 -> 741676521
    else:
        candidates.add("0" + cleaned)         # 741676521 -> 0741676521
        candidates.add("254" + cleaned)       # 741676521 -> 254741676521

    return [c for c in candidates if c]


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    identifier = (user_data.email or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Email or phone is required")

    # Try email first
    user = db.query(User).filter(User.email == identifier).first()

    # If not found, try phone variants
    if not user:
        for phone in _normalize_phone(identifier):
            user = db.query(User).filter(User.phone == phone).first()
            if user:
                break

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=token, user=user)


@router.post("/signup", response_model=Token)
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    email = (user_data.email or "").strip() or None
    phone = (user_data.phone or "").strip() or None

    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email or phone required")

    if email:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

    if phone:
        existing = db.query(User).filter(User.phone == phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone already registered")

    user = User(
        name=user_data.name,
        email=email,
        phone=phone,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=token, user=user)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user
from datetime import datetime
import sqlite3

router = APIRouter()


@router.get("/summary")
async def tax_summary(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COALESCE(SUM(tax_amount), 0) FROM tax_ledger WHERE created_at LIKE ?",
            (today + "%",),
        )
        today_tax = cursor.fetchone()[0]

        month = datetime.now().strftime("%Y-%m")
        cursor.execute(
            "SELECT COALESCE(SUM(tax_amount), 0) FROM tax_ledger WHERE created_at LIKE ?",
            (month + "%",),
        )
        month_tax = cursor.fetchone()[0]

        year = datetime.now().strftime("%Y")
        cursor.execute(
            "SELECT COALESCE(SUM(tax_amount), 0) FROM tax_ledger WHERE created_at LIKE ?",
            (year + "%",),
        )
        year_tax = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(tax_amount), 0) FROM tax_ledger")
        total_tax = cursor.fetchone()[0]

    return {
        "today_tax": round(today_tax, 2),
        "month_tax": round(month_tax, 2),
        "year_tax": round(year_tax, 2),
        "total_tax": round(total_tax, 2),
    }


@router.get("/transactions")
async def tax_transactions(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT receipt_no, created_at, product_name, quantity, unit_price,
                   tax_rate, tax_amount, payment_method, cashier
            FROM tax_ledger
            ORDER BY id DESC
            LIMIT 100
        """)
        rows = cursor.fetchall()

    return [
        {
            "receipt_no": r[0],
            "date": r[1],
            "product": r[2],
            "quantity": r[3],
            "unit_price": r[4],
            "tax_rate": r[5],
            "tax_amount": r[6],
            "payment": r[7],
            "cashier": r[8],
        }
        for r in rows
    ]



# ============================================================
#  Tax Ledger v2 - Archive endpoints
# ============================================================

from services import tax_archiver


@router.get("/archive/summary")
async def archive_summary(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """List all archived months with totals."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return tax_archiver.get_archive_summary()


@router.get("/archive/full")
async def archive_full(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Combined live + archived + purged totals."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return tax_archiver.get_full_tax_summary()


@router.get("/archive/purgeable")
async def archive_purgeable(retention_years: int = 5, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Months old enough to purge (default 5 years retention)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can view purgeable months")
    return {
        "retention_years": retention_years,
        "months": tax_archiver.list_purgeable(retention_years),
    }


@router.post("/archive/purge/{month}")
async def archive_purge(month: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Purge one archived month. Admin only. Writes permanent manifest."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can purge archives")

    # Validate format
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="Invalid month format (use YYYY-MM)")

    # Check purgeability
    purgeable = tax_archiver.list_purgeable(5)
    purgeable_months = [p["month"] for p in purgeable]
    if month not in purgeable_months:
        raise HTTPException(
            status_code=400,
            detail=f"Month {month} is not old enough to purge (need 5 years retention).",
        )

    result = tax_archiver.purge_month(month, current_user.name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Purge failed"))
    return result


@router.get("/archive/purge-history")
async def archive_purge_history(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanent record of every purge ever done."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return tax_archiver.get_purge_history()


@router.get("/archive/verify")
async def archive_verify(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Verify SHA-256 chain integrity of the archive."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return tax_archiver.verify_chain()



# ============================================================
#  View a single archived month's actual rows
# ============================================================

@router.get("/archive/month/{month}")
async def archive_month_rows(
    month: str,
    limit: int = 200,
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Decompress and return the individual tax rows for one archived month.

    Month format: YYYY-MM (e.g. 2025-03)
    Paginated via ?limit=200&offset=0
    """
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="Invalid month format (use YYYY-MM)")

    import gzip
    import json

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT month, row_count, total_tax, data_blob, sha256, created_at
            FROM tax_ledger_archive
            WHERE month = ?
        """, (month,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Month {month} not found in archive")

    month_name, row_count, total_tax, blob, sha, archived_at = row

    try:
        raw = gzip.decompress(blob)
        rows = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decompress archive: {e}")

    # Paginate
    total_rows = len(rows)
    page = rows[offset:offset + limit]

    return {
        "month": month_name,
        "total_rows": total_rows,
        "total_tax": round(total_tax, 2),
        "archived_at": archived_at,
        "sha256_short": sha[:16] + "...",
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "rows": page,
    }

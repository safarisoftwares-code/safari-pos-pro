from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user
from pydantic import BaseModel
import sqlite3

router = APIRouter()


# ============================================================
#  Settings helpers (same pattern as routers/settings.py)
# ============================================================

def _get_setting(key: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
    return row[0] if row else None


def _set_setting(key: str, value: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


# ============================================================
#  Pydantic models
# ============================================================

class PrinterConfig(BaseModel):
    receipt_printer: str = ""
    report_printer: str = ""
    pdf_fallback_folder: str = ""
    auto_print_receipt: str = "true"
    auto_print_report: str = "false"


# ============================================================
#  Available printers (Windows auto-detect)
# ============================================================

@router.get("/available")
async def available_printers(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Return all printers installed on this Windows machine.

    Uses win32print.EnumPrinters(2) which lists LOCAL + CONNECTION printers.
    Filters out obvious junk (Fax, XPS Document Writer).
    Keeps OneNote and Microsoft Print to PDF since they are useful for
    testing and PDF output.
    """
    try:
        import win32print
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pywin32 is not installed. Run: pip install pywin32",
        )

    try:
        raw = win32print.EnumPrinters(2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enumerate printers: {e}")

    # raw is a list of tuples: (flags, description, name, driver)
    names = sorted(set(p[2] for p in raw))

    # Filter out junk
    junk_markers = ["fax", "xps document writer", "microsoft xps"]
    filtered = [
        name for name in names
        if not any(j in name.lower() for j in junk_markers)
    ]

    # Also identify the Windows default printer
    try:
        default_name = win32print.GetDefaultPrinter()
    except Exception:
        default_name = None

    return {
        "printers": filtered,
        "default": default_name,
        "total_raw": len(names),
        "total_filtered": len(filtered),
    }


# ============================================================
#  Current config
# ============================================================

@router.get("/config")
async def get_printer_config(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "receipt_printer": _get_setting("receipt_printer") or "",
        "report_printer": _get_setting("report_printer") or "",
        "pdf_fallback_folder": _get_setting("pdf_fallback_folder") or "",
        "auto_print_receipt": _get_setting("auto_print_receipt") or "true",
        "auto_print_report": _get_setting("auto_print_report") or "false",
    }


# ============================================================
#  Save config (admin only)
# ============================================================

@router.put("/config")
async def update_printer_config(
    config: PrinterConfig,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can change printer settings")

    _set_setting("receipt_printer", config.receipt_printer or "")
    _set_setting("report_printer", config.report_printer or "")
    _set_setting("pdf_fallback_folder", config.pdf_fallback_folder or "")
    _set_setting("auto_print_receipt", config.auto_print_receipt or "true")
    _set_setting("auto_print_report", config.auto_print_report or "false")

    return {"message": "Printer settings saved"}

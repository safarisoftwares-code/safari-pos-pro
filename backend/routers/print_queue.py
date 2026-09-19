from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user
import services.print_processor as print_processor
from pydantic import BaseModel
import sqlite3
import os
from datetime import datetime

router = APIRouter()


# ============================================================
#  Settings helpers
# ============================================================

def _get_setting(key: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
    return row[0] if row else None


# ============================================================
#  Pydantic models
# ============================================================

class EnqueueRequest(BaseModel):
    job_type: str = "receipt"          # 'receipt' | 'report' | 'test'
    printer_name: str = ""             # optional override; empty = use configured
    payload: str                       # HTML content


class TestPrintRequest(BaseModel):
    printer_name: str = ""             # optional


# ============================================================
#  Endpoints
# ============================================================

@router.post("/enqueue")
async def enqueue_job(
    req: EnqueueRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Queue a print job. Called by checkout when auto_print_receipt is on.
    """
    # Resolve printer
    printer_name = req.printer_name.strip() if req.printer_name else ""
    if not printer_name:
        if req.job_type == "report":
            printer_name = _get_setting("report_printer") or ""
        else:
            printer_name = _get_setting("receipt_printer") or ""

    if not printer_name:
        raise HTTPException(
            status_code=400,
            detail=f"No printer configured for job type '{req.job_type}'. "
                   f"Ask admin to set a printer in Settings.",
        )

    if not req.payload.strip():
        raise HTTPException(status_code=400, detail="Payload is empty")

    job_id = print_processor.enqueue(
        job_type=req.job_type,
        printer_name=printer_name,
        payload=req.payload,
        created_by=current_user.id,
    )

    return {"ok": True, "job_id": job_id, "printer_name": printer_name}


@router.get("/summary")
async def queue_summary(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Counts + recent jobs."""
    return print_processor.get_queue_summary()


@router.post("/clear-printed")
async def clear_printed(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete all printed jobs from the queue."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    removed = print_processor.clear_printed()
    return {"ok": True, "removed": removed}


@router.post("/retry/{job_id}")
async def retry_failed(job_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Reset a failed job back to pending."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    ok = print_processor.retry_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or not in failed state")
    return {"ok": True, "job_id": job_id}


@router.post("/test")
async def test_print(
    req: TestPrintRequest = TestPrintRequest(),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Queue a test print. Uses the configured receipt printer if not specified.
    """
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    printer_name = req.printer_name.strip() if req.printer_name else ""
    if not printer_name:
        printer_name = _get_setting("receipt_printer") or ""

    if not printer_name:
        raise HTTPException(
            status_code=400,
            detail="No printer configured. Set one in Settings > Printer Configuration.",
        )

    payload = f"""
    <html>
    <body style="font-family: Courier New; padding: 20px;">
        <div style="text-align:center;">
            <h2>SAFARI POS PRO</h2>
            <p>From Vision to Version</p>
            <hr>
            <p><strong>TEST PRINT</strong></p>
            <p>Printer: {printer_name}</p>
            <p>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>User: {current_user.name}</p>
            <hr>
            <p>If you can read this, the printer is working.</p>
        </div>
    </body>
    </html>
    """

    job_id = print_processor.enqueue(
        job_type="test",
        printer_name=printer_name,
        payload=payload,
        created_by=current_user.id,
    )

    return {"ok": True, "job_id": job_id, "printer_name": printer_name}



# ============================================================
#  Report print endpoint
# ============================================================

class ReportEnqueueRequest(BaseModel):
    report_type: str          # 'daily-close' | 'profit' | 'sales' | 'analytics' | 'tax' | 'custom'
    title: str = ""           # optional override title
    payload: str              # HTML content


@router.post("/enqueue-report")
async def enqueue_report(
    req: ReportEnqueueRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Queue a report print job. Uses the configured REPORT printer.
    Reports are always archived as PDFs by the print processor.
    """
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only admin or manager can print reports")

    printer_name = _get_setting("report_printer") or ""

    if not printer_name:
        # Fall back to receipt printer if report printer not set
        printer_name = _get_setting("receipt_printer") or ""

    if not printer_name:
        raise HTTPException(
            status_code=400,
            detail="No report printer configured. Set one in Settings > Printer Configuration.",
        )

    if not req.payload.strip():
        raise HTTPException(status_code=400, detail="Payload is empty")

    job_id = print_processor.enqueue(
        job_type="report",
        printer_name=printer_name,
        payload=req.payload,
        created_by=current_user.id,
    )

    return {
        "ok": True,
        "job_id": job_id,
        "printer_name": printer_name,
        "report_type": req.report_type,
    }

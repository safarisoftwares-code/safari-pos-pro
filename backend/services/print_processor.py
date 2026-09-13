"""
Safari POS Pro - Print Queue Processor

Background worker that:
  1. Polls the print_queue table every 3 seconds
  2. Picks the oldest pending job
  3. Sends it to the configured Windows printer
  4. Marks the job as printed (or failed)
  5. Logs every event

Runs as a daemon thread started from main.py on server startup.
"""

import sqlite3
import threading
import time
import os
import re
import json
from datetime import datetime
from database import DB_PATH

# Paths
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
PRINT_LOG = os.path.join(LOG_DIR, "print_processor.log")


# ============================================================
#  PDF Archive
# ============================================================

def _get_pdf_archive_folder():
    """Get the configured PDF archive folder (from settings table)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = 'pdf_fallback_folder'")
            row = cur.fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass

    # Default: Desktop\Safari-POS-Printed
    home = os.path.expanduser("~")
    return os.path.join(home, "Desktop", "Safari-POS-Printed")


def _extract_ref_from_html(html_payload, job_type="unknown"):
    """Pull a useful ref from the HTML: receipt no for receipts, report name for reports."""
    # Receipt number
    m = re.search(r"(INV-\d{8}-\d{4})", html_payload)
    if m:
        return m.group(1)

    # Report title - look for <h2>...</h2> in the header
    if job_type == "report":
        m = re.search(r"<h2[^>]*>([^<]+)</h2>", html_payload)
        if m:
            title = m.group(1).strip()
            safe = re.sub(r"[^A-Za-z0-9 ]+", "", title)
            safe = safe.strip().replace(" ", "-")
            if safe:
                return safe[:40]

    return "unknown"


def save_pdf_archive(job_type, html_payload, timestamp=None):
    """
    Render HTML to PDF and save it under:
      <archive_folder>\YYYYMMDD\HH-MM-SS_<job_type>_<ref>.pdf

    Returns (success, path_or_error).
    """
    if timestamp is None:
        now = datetime.now()
    else:
        now = timestamp

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return False, f"playwright not installed: {e}"

    try:
        base = _get_pdf_archive_folder()
        date_folder = now.strftime("%Y%m%d")
        target_dir = os.path.join(base, date_folder)
        os.makedirs(target_dir, exist_ok=True)

        ref = _extract_ref_from_html(html_payload, job_type)
        filename = f"{now.strftime('%H-%M-%S')}_{job_type}_{ref}.pdf"
        target_path = os.path.join(target_dir, filename)

        # Render via headless Chromium
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html_payload, wait_until="load")
                page.pdf(
                    path=target_path,
                    width="210mm",
                    height="297mm",
                    print_background=True,
                    margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                    prefer_css_page_size=False,
                    tagged=False,
                    outline=False,
                )
            finally:
                browser.close()

        return True, target_path
    except Exception as e:
        return False, f"PDF render failed: {e}"

# Config
POLL_INTERVAL_SECONDS = 3
WORKER_STARTED = False
STOP_FLAG = False


# ============================================================
#  Logging
# ============================================================

def log_event(message: str):
    """Append a line to print_processor.log."""
    try:
        with open(PRINT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"[print-processor] log write failed: {e}")


# ============================================================
#  Table setup
# ============================================================

def ensure_tables():
    """Create the print_queue table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS print_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                printer_name TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                printed_at TEXT,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_print_queue_status
            ON print_queue(status, created_at)
        """)
        conn.commit()


# ============================================================
#  Queue operations (called from routers)
# ============================================================

def enqueue(job_type: str, printer_name: str, payload: str, created_by: int = None) -> int:
    """
    Add a job to the queue. Returns the new job id.
    job_type: 'receipt' | 'report' | 'test'
    payload:  HTML string to print
    """
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO print_queue
            (job_type, status, printer_name, payload, created_by, created_at)
            VALUES (?, 'pending', ?, ?, ?, ?)
        """, (
            job_type, printer_name, payload, created_by,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        conn.commit()
        job_id = cur.lastrowid
    log_event(f"ENQUEUED job #{job_id} type={job_type} printer={printer_name}")
    return job_id


def get_queue_summary() -> dict:
    """Return counts per status + recent jobs."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT status, COUNT(*)
            FROM print_queue
            GROUP BY status
        """)
        counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("""
            SELECT id, job_type, status, printer_name, created_at, printed_at, error_message
            FROM print_queue
            ORDER BY id DESC
            LIMIT 30
        """)
        recent = [
            {
                "id": r[0],
                "job_type": r[1],
                "status": r[2],
                "printer_name": r[3],
                "created_at": r[4],
                "printed_at": r[5],
                "error_message": r[6],
            }
            for r in cur.fetchall()
        ]

    return {
        "counts": {
            "pending": counts.get("pending", 0),
            "printing": counts.get("printing", 0),
            "printed": counts.get("printed", 0),
            "failed": counts.get("failed", 0),
        },
        "recent": recent,
    }


def clear_printed() -> int:
    """Delete all 'printed' jobs. Returns number removed."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM print_queue WHERE status = 'printed'")
        conn.commit()
        removed = cur.rowcount
    log_event(f"CLEARED {removed} printed job(s)")
    return removed


def retry_job(job_id: int) -> bool:
    """Reset a failed job back to pending."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE print_queue
            SET status = 'pending', error_message = NULL
            WHERE id = ? AND status = 'failed'
        """, (job_id,))
        conn.commit()
        ok = cur.rowcount > 0
    if ok:
        log_event(f"RETRY job #{job_id}")
    return ok


# ============================================================
#  Printer send
# ============================================================

def _send_to_printer(printer_name: str, html_payload: str) -> tuple:
    """
    Send raw content to a Windows printer using win32print.
    Returns (success: bool, error_message: str | None)

    Note: win32print sends raw bytes to the spooler. For text-style
    receipts this works. Full HTML rendering happens in Phase 7 via PDF.
    """
    try:
        import win32print
    except ImportError as e:
        return False, f"win32print not installed: {e}"

    # Verify the printer exists
    try:
        installed = [p[2] for p in win32print.EnumPrinters(2)]
        if printer_name not in installed:
            return False, f"Printer '{printer_name}' not found on this machine"
    except Exception as e:
        return False, f"Failed to enumerate printers: {e}"

    # Extract printable text from HTML
    import re
    text = re.sub(r"<br\s*/?>", "\n", html_payload, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</div>|</tr>|</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

    if not text:
        text = "(empty receipt)"

    # Write text to a temp file and print it
    try:
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="safaripos_")
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Use Windows shell to print the file to the specific printer
        # This uses the default print action for .txt files
        import subprocess
        # Command: print /D:"printer name" "file"
        # Windows' built-in `print` command works for text files
        result = subprocess.run(
            ["print", f"/D:{printer_name}", tmp_path],
            capture_output=True, text=True, timeout=30,
        )

        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            return False, f"print command failed: {err}"

        return True, None
    except subprocess.TimeoutExpired:
        return False, "print command timed out"
    except Exception as e:
        return False, f"print error: {e}"


# ============================================================
#  Worker loop
# ============================================================

def _process_one() -> bool:
    """
    Pick one pending job and process it.
    Returns True if a job was processed, False if queue was empty.
    """
    ensure_tables()

    # Grab the oldest pending job
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, job_type, printer_name, payload
            FROM print_queue
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT 1
        """)
        row = cur.fetchone()

    if not row:
        return False

    job_id, job_type, printer_name, payload = row

    # Mark as printing
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE print_queue SET status = 'printing' WHERE id = ?
        """, (job_id,))
        conn.commit()

    log_event(f"PROCESSING job #{job_id} type={job_type} printer={printer_name}")

    # STEP 1: Save PDF archive (always — even if printer fails)
    pdf_ok, pdf_path_or_err = save_pdf_archive(job_type, payload)
    if pdf_ok:
        log_event(f"PDF SAVED job #{job_id}: {pdf_path_or_err}")
    else:
        log_event(f"PDF FAIL job #{job_id}: {pdf_path_or_err}")

    # STEP 2: Send to printer
    success, error = _send_to_printer(printer_name, payload)

    # Update
    with sqlite3.connect(DB_PATH) as conn:
        if success:
            conn.execute("""
                UPDATE print_queue
                SET status = 'printed', printed_at = ?
                WHERE id = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), job_id))
            log_event(f"PRINTED job #{job_id}")
        else:
            conn.execute("""
                UPDATE print_queue
                SET status = 'failed', error_message = ?, retry_count = retry_count + 1
                WHERE id = ?
            """, (error, job_id))
            log_event(f"FAILED job #{job_id}: {error}")
        conn.commit()

    return True


def _worker_loop():
    """Main loop: poll, process, sleep."""
    log_event("=== Print processor started ===")
    while not STOP_FLAG:
        try:
            processed = _process_one()
            if not processed:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                # If we processed one, immediately check for another
                time.sleep(0.3)
        except Exception as e:
            log_event(f"WORKER ERROR: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
    log_event("=== Print processor stopped ===")


def start_worker():
    """Start the background worker thread (idempotent)."""
    global WORKER_STARTED
    if WORKER_STARTED:
        log_event("Worker already running — skipping start")
        return
    ensure_tables()
    t = threading.Thread(target=_worker_loop, daemon=True, name="PrintProcessor")
    t.start()
    WORKER_STARTED = True
    print("[print-processor] Background worker started")


def stop_worker():
    """Signal the worker to stop (used on shutdown)."""
    global STOP_FLAG
    STOP_FLAG = True

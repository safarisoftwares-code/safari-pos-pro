"""
Safari POS Pro - M-Pesa Relay Poller (v4.2)

v4.2 rewrite focuses on SQLite reliability:
  - Every DB operation uses its own short-lived connection.
  - No nested connections - which was causing "database is locked".
  - busy_timeout=30000 set on every connection.
  - _finalize_paid_sale is atomic (all stock + tax writes in one transaction).
  - Idle-skip retained from v4.1: zero relay traffic when nothing pending.
"""

import sqlite3
import threading
import time
import os
from datetime import datetime
from database import DB_PATH

RELAY_BASE_URL = "https://relay.safari-pos.co.ke"
POLL_INTERVAL_SECONDS = 5
IDLE_LOG_INTERVAL_SECONDS = 300

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
)
os.makedirs(LOG_DIR, exist_ok=True)
MPESA_LOG = os.path.join(LOG_DIR, "mpesa_poller.log")

_state_lock = threading.Lock()
_worker_thread = None
_stop_flag = False


# ======================================================================
#  Logging
# ======================================================================

def log_event(message: str):
    try:
        with open(MPESA_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"[mpesa-poller] log write failed: {e}")


# ======================================================================
#  DB helpers - always short-lived connections, always committed or closed
# ======================================================================

def _open_db():
    """Open a fresh SQLite connection with sane pragmas."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # Ensure pragmas even outside SQLAlchemy
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
    except Exception:
        pass
    return conn


def _db_read_one(sql: str, params: tuple = ()):
    """Read one row. Always opens and closes its own connection."""
    conn = _open_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def _db_read_all(sql: str, params: tuple = ()):
    conn = _open_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _db_write(sql: str, params: tuple = ()):
    """Single write. Opens, commits, closes."""
    conn = _open_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _db_write_many(statements):
    """
    Execute a list of (sql, params) inside ONE transaction on ONE connection.
    All succeed or all roll back. Never nests.
    """
    conn = _open_db()
    try:
        cur = conn.cursor()
        for sql, params in statements:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================================================================
#  Settings
# ======================================================================

def get_setting(key):
    row = _db_read_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row[0] if row else None


# ======================================================================
#  Pending-sale lookups
# ======================================================================

def has_pending_sale() -> bool:
    try:
        row = _db_read_one(
            "SELECT 1 FROM sales WHERE payment_status = 'pending' LIMIT 1"
        )
        return row is not None
    except Exception as e:
        log_event(f"has_pending_sale() error: {e}")
        # Be conservative: assume there's a pending sale so we don't miss a callback
        return True


def find_pending_sale_by_checkout(checkout_id: str):
    row = _db_read_one(
        "SELECT id FROM sales WHERE mpesa_checkout_id = ? "
        "AND payment_status = 'pending' LIMIT 1",
        (checkout_id,),
    )
    return row[0] if row else None


# ======================================================================
#  Finalize paid sale
# ======================================================================

def _finalize_paid_sale(sale_id: int):
    """
    After a sale is marked paid:
      - Decrement stock for each item
      - Write tax_ledger rows for each item

    All in ONE transaction. Never opens more than one connection.
    Retried by the caller on lock errors.
    """
    # Gather data first (read-only)
    sale_row = _db_read_one(
        "SELECT receipt_no, cashier_name, payment_method, created_at "
        "FROM sales WHERE id = ?",
        (sale_id,),
    )
    if not sale_row:
        return
    receipt_no, cashier_name, payment_method, created_at = sale_row

    items = _db_read_all(
        "SELECT si.product_id, si.quantity, si.unit_price, si.tax_rate, "
        "si.tax_amount, p.name "
        "FROM sale_items si "
        "LEFT JOIN products p ON p.id = si.product_id "
        "WHERE si.sale_id = ?",
        (sale_id,),
    )
    if not items:
        return

    # Build all statements, then execute atomically
    statements = []
    for product_id, quantity, unit_price, tax_rate, tax_amount, product_name in items:
        statements.append((
            "UPDATE products SET stock = stock - ? WHERE id = ?",
            (quantity, product_id),
        ))
        statements.append((
            "INSERT INTO tax_ledger "
            "(receipt_no, product_name, quantity, unit_price, tax_rate, "
            "tax_amount, payment_method, cashier, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt_no,
                product_name or "Unknown",
                quantity,
                unit_price,
                tax_rate or 0,
                tax_amount or 0,
                payment_method,
                cashier_name or "Unknown",
                created_at,
            ),
        ))

    _db_write_many(statements)


def _finalize_with_retry(sale_id: int, max_attempts: int = 3):
    """Retry on SQLite lock errors."""
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            _finalize_paid_sale(sale_id)
            return
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "locked" in msg or "busy" in msg:
                log_event(f"RETRY finalize #{sale_id} (attempt {attempt}/{max_attempts}): {e}")
                time.sleep(2)
            else:
                raise
    raise last_err if last_err else Exception("finalize failed")


# ======================================================================
#  Callback processing
# ======================================================================

def _process_one_callback(callback_data):
    """
    Handle one callback from the relay.

    IMPORTANT: never opens two DB connections at once.
    Each step uses its own short-lived connection, fully closed before the next.
    """
    try:
        body = callback_data.get("Body", {})
        stk = body.get("stkCallback", {})
        result_code = stk.get("ResultCode")
        checkout_id = stk.get("CheckoutRequestID")

        log_event(f"CALLBACK received: ResultCode={result_code} CheckoutID={checkout_id}")

        if not checkout_id:
            log_event("WARN: No CheckoutRequestID in callback")
            return False

        sale_id = find_pending_sale_by_checkout(checkout_id)
        if not sale_id:
            log_event(f"WARN: No pending sale found for CheckoutID={checkout_id}")
            return False

        mpesa_receipt = ""
        if result_code == 0:
            items = stk.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item.get("Name") == "MpesaReceiptNumber":
                    mpesa_receipt = item.get("Value", "")
                    break

        if result_code == 0:
            # STEP 1: mark sale as paid (its own connection, own commit)
            _db_write(
                "UPDATE sales SET payment_status = 'paid', status = 'completed', "
                "mpesa_receipt = ?, paid_at = ? WHERE id = ?",
                (
                    mpesa_receipt,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    sale_id,
                ),
            )
            log_event(f"PAID sale #{sale_id} (M-Pesa: {mpesa_receipt})")

            # STEP 2: finalize (fresh connection, retry on lock)
            # Connection from step 1 is already closed here.
            try:
                _finalize_with_retry(sale_id)
            except Exception as e:
                log_event(f"ERROR finalizing sale #{sale_id} after retries: {e}")
        else:
            reason = "failed"
            _db_write(
                "UPDATE sales SET payment_status = ?, status = ? WHERE id = ?",
                (reason, reason, sale_id),
            )
            log_event(f"FAILED sale #{sale_id} (ResultCode={result_code})")

        return True
    except Exception as e:
        log_event(f"ERROR processing callback: {e}")
        return False


# ======================================================================
#  Relay poll
# ======================================================================

def _poll_relay_once():
    shop_id = get_setting("mpesa_shop_id")
    if not shop_id:
        return False
    try:
        import requests
        url = f"{RELAY_BASE_URL}/next/{shop_id}"
        r = requests.get(url, timeout=5)

        if r.status_code == 204:
            return False
        if r.status_code != 200:
            log_event(f"WARN: Relay returned {r.status_code}")
            return False

        callback_data = r.json()
        log_event(f"RELAY delivered callback for shop {shop_id}")
        return _process_one_callback(callback_data)
    except Exception as e:
        log_event(f"POLL ERROR: {e}")
        return False


# ======================================================================
#  Worker loop
# ======================================================================

def _worker_loop():
    log_event("=== M-Pesa Poller started (v4.2 single-connection) ===")
    last_idle_log = 0.0
    while not _stop_flag:
        try:
            mpesa_enabled = get_setting("mpesa_enabled") == "true"
            shop_id = get_setting("mpesa_shop_id")

            if not mpesa_enabled or not shop_id:
                _sleep_interruptible(POLL_INTERVAL_SECONDS)
                continue

            if not has_pending_sale():
                now = time.time()
                if now - last_idle_log > IDLE_LOG_INTERVAL_SECONDS:
                    log_event("IDLE: no pending sales, skipping relay calls")
                    last_idle_log = now
                _sleep_interruptible(POLL_INTERVAL_SECONDS)
                continue

            processed = _poll_relay_once()
            if processed:
                _sleep_interruptible(0.5)
                continue

            _sleep_interruptible(POLL_INTERVAL_SECONDS)
        except Exception as e:
            log_event(f"WORKER ERROR: {e}")
            _sleep_interruptible(POLL_INTERVAL_SECONDS)
    log_event("=== M-Pesa Poller stopped ===")


def _sleep_interruptible(seconds: float):
    """Sleep in small chunks so _stop_flag is honored within ~100ms."""
    end = time.time() + seconds
    while time.time() < end:
        if _stop_flag:
            return
        time.sleep(0.1)


# ======================================================================
#  Lifecycle
# ======================================================================

def start_worker():
    global _worker_thread, _stop_flag
    with _state_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _stop_flag = False
        _worker_thread = threading.Thread(
            target=_worker_loop, daemon=True, name="MpesaPoller"
        )
        _worker_thread.start()


def stop_worker():
    global _stop_flag, _worker_thread
    with _state_lock:
        _stop_flag = True
        t = _worker_thread
    if t is not None and t.is_alive():
        try:
            t.join(timeout=3.0)
        except Exception:
            pass

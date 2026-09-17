"""
Safari POS Pro - M-Pesa Relay Poller

Background worker that polls the Cloudflare relay for pending M-Pesa callbacks
and processes them, updating sales from "pending" to "paid" or "failed".
"""

import sqlite3
import threading
import time
import os
import json
from datetime import datetime
from database import DB_PATH

# Configuration
RELAY_BASE_URL = "https://relay.safari-pos.co.ke"
POLL_INTERVAL_SECONDS = 3
WORKER_STARTED = False
STOP_FLAG = False

# Paths
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
MPESA_LOG = os.path.join(LOG_DIR, "mpesa_poller.log")


def log_event(message: str):
    try:
        with open(MPESA_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"[mpesa-poller] log write failed: {e}")


def get_setting(key):
    """Read a setting from the settings table."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
    return row[0] if row else None


def find_pending_sale_by_checkout(checkout_id: str):
    """Return the sale_id that matches this Safaricom CheckoutRequestID."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM sales WHERE mpesa_checkout_id = ? AND payment_status = 'pending' LIMIT 1", (checkout_id,))
        row = cur.fetchone()
    return row[0] if row else None


def _process_one_callback(callback_data):
    """Handle one callback from the relay."""
    try:
        body = callback_data.get("Body", {})
        stk = body.get("stkCallback", {})
        result_code = stk.get("ResultCode")
        checkout_id = stk.get("CheckoutRequestID")
        merchant_id = stk.get("MerchantRequestID")

        log_event(f"CALLBACK received: ResultCode={result_code} CheckoutID={checkout_id}")

        if not checkout_id:
            log_event("WARN: No CheckoutRequestID in callback")
            return False

        sale_id = find_pending_sale_by_checkout(checkout_id)
        if not sale_id:
            log_event(f"WARN: No pending sale found for CheckoutID={checkout_id}")
            return False

        # Extract M-Pesa receipt if success
        mpesa_receipt = ""
        if result_code == 0:
            items = stk.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item.get("Name") == "MpesaReceiptNumber":
                    mpesa_receipt = item.get("Value", "")
                    break

        # Update the sale directly in DB (simpler than calling endpoints)
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            if result_code == 0:
                cur.execute("""
                    UPDATE sales
                    SET payment_status = 'paid',
                        status = 'completed',
                        mpesa_receipt = ?,
                        paid_at = ?
                    WHERE id = ?
                """, (mpesa_receipt, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sale_id))
                log_event(f"PAID sale #{sale_id} (M-Pesa: {mpesa_receipt})")

                # Now decrement stock + write tax ledger
                try:
                    _finalize_paid_sale(sale_id)
                except Exception as e:
                    log_event(f"ERROR finalizing sale #{sale_id}: {e}")

            else:
                reason = "failed"
                cur.execute("""
                    UPDATE sales
                    SET payment_status = ?,
                        status = ?
                    WHERE id = ?
                """, (reason, reason, sale_id))
                log_event(f"FAILED sale #{sale_id} (ResultCode={result_code})")

            conn.commit()

        return True
    except Exception as e:
        log_event(f"ERROR processing callback: {e}")
        return False


def _finalize_paid_sale(sale_id: int):
    """
    After a sale is marked paid:
    - Decrement stock for each item
    - Write rows to tax_ledger
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Get sale info
        cur.execute("SELECT receipt_no, cashier_name, payment_method, created_at FROM sales WHERE id = ?", (sale_id,))
        sale_row = cur.fetchone()
        if not sale_row:
            return
        receipt_no, cashier_name, payment_method, created_at = sale_row

        # Get items
        cur.execute("""
            SELECT si.product_id, si.quantity, si.unit_price, si.tax_rate, si.tax_amount,
                   p.name
            FROM sale_items si
            LEFT JOIN products p ON p.id = si.product_id
            WHERE si.sale_id = ?
        """, (sale_id,))
        items = cur.fetchall()

        # Decrement stock
        for product_id, quantity, _, _, _, _ in items:
            cur.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))

        # Write tax ledger
        for product_id, quantity, unit_price, tax_rate, tax_amount, product_name in items:
            cur.execute("""
                INSERT INTO tax_ledger
                (receipt_no, product_name, quantity, unit_price, tax_rate,
                 tax_amount, payment_method, cashier, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_no,
                product_name or "Unknown",
                quantity,
                unit_price,
                tax_rate,
                tax_amount,
                payment_method,
                cashier_name or "Unknown",
                created_at,
            ))

        conn.commit()


def _poll_relay_once():
    """Call the relay /next/{shop_id} endpoint once."""
    shop_id = get_setting("mpesa_shop_id")
    if not shop_id:
        return False

    # Check if mock mode is on
    mock = get_setting("mpesa_mock_mode") == "true"
    if mock:
        # In mock mode we still poll but the mock handler writes directly
        pass

    try:
        import requests
        url = f"{RELAY_BASE_URL}/next/{shop_id}"
        r = requests.get(url, timeout=5)

        if r.status_code == 204:
            return False  # no callback pending

        if r.status_code != 200:
            log_event(f"WARN: Relay returned {r.status_code}")
            return False

        callback_data = r.json()
        log_event(f"RELAY delivered callback for shop {shop_id}")
        return _process_one_callback(callback_data)
    except Exception as e:
        log_event(f"POLL ERROR: {e}")
        return False


def _worker_loop():
    log_event("=== M-Pesa Poller started ===")
    while not STOP_FLAG:
        try:
            shop_id = get_setting("mpesa_shop_id")
            mpesa_enabled = get_setting("mpesa_enabled") == "true"

            if shop_id and mpesa_enabled:
                processed = _poll_relay_once()
                if processed:
                    time.sleep(0.5)
                    continue

            time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            log_event(f"WORKER ERROR: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
    log_event("=== M-Pesa Poller stopped ===")


def start_worker():
    global WORKER_STARTED
    if WORKER_STARTED:
        log_event("Worker already running")
        return
    t = threading.Thread(target=_worker_loop, daemon=True, name="MpesaPoller")
    t.start()
    WORKER_STARTED = True
    print("[mpesa-poller] Background worker started")


def stop_worker():
    global STOP_FLAG
    STOP_FLAG = True

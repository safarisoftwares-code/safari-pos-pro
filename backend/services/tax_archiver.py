"""
Safari POS Pro - Tax Ledger v2 (3-Tier Archive System)

Live table:      tax_ledger             - last 12 months, fast
Archive table:   tax_ledger_archive     - gzipped monthly blobs, SHA-256 chained
Purge manifest:  tax_ledger_purged      - permanent proof of purged months

Flow:
  1. Sales write rows to tax_ledger (existing code, unchanged)
  2. Once a day, rows older than 12 months get rolled up per-month into
     tax_ledger_archive as gzipped JSON + SHA-256 (chained to previous)
  3. After retention_years (default 5), admin can purge a month
  4. Purging writes a manifest row to tax_ledger_purged (never deleted)

Why this works:
  - KRA requires 5 years retention.
  - Live queries stay fast because live table only holds 12 months.
  - Historical reports sum from the archive.
  - Tamper-evident: SHA-256 chain breaks if any archive is modified.
  - Legal: purge manifest proves what was deleted, when, by whom.
"""

import sqlite3
import json
import gzip
import hashlib
from datetime import datetime
from database import DB_PATH


# ============================================================
#  Table setup
# ============================================================

def ensure_tables():
    """Create the two new tables if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tax_ledger_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                row_count INTEGER NOT NULL,
                total_tax REAL NOT NULL,
                data_blob BLOB NOT NULL,
                sha256 TEXT NOT NULL,
                previous_sha256 TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_archive_month
            ON tax_ledger_archive(month)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tax_ledger_purged (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                total_tax REAL NOT NULL,
                sha256 TEXT NOT NULL,
                purged_by TEXT NOT NULL,
                purged_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_purged_month
            ON tax_ledger_purged(month)
        """)
        conn.commit()


# ============================================================
#  Helpers
# ============================================================

def _hash_blob(data_blob: bytes, previous_sha256: str) -> str:
    """SHA-256 of blob + previous hash (blockchain-lite chain)."""
    h = hashlib.sha256()
    h.update(data_blob)
    h.update((previous_sha256 or "GENESIS").encode())
    return h.hexdigest()


def _month_key(dt_str: str) -> str:
    """'2025-03-15 10:22:01' -> '2025-03'"""
    return dt_str[:7] if dt_str and len(dt_str) >= 7 else "unknown"


def _cutoff_month(retention_months: int = 12) -> str:
    """Return the YYYY-MM that separates live from archive."""
    now = datetime.now()
    # Subtract N months
    y, m = now.year, now.month - retention_months
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


# ============================================================
#  Archive runner (called on startup, once per day)
# ============================================================

def run_daily_maintenance(retention_months: int = 12) -> dict:
    """
    Archive rows in tax_ledger older than retention_months into monthly blobs.

    Returns a summary dict for logging:
      {"archived_months": [...], "rows_moved": N, "rows_deleted": N}
    """
    ensure_tables()

    cutoff = _cutoff_month(retention_months)
    summary = {"archived_months": [], "rows_moved": 0, "rows_deleted": 0, "cutoff": cutoff}

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Find old rows grouped by month
        cur.execute("""
            SELECT substr(created_at, 1, 7) AS month, COUNT(*), SUM(tax_amount)
            FROM tax_ledger
            WHERE substr(created_at, 1, 7) < ?
            GROUP BY month
            ORDER BY month
        """, (cutoff,))
        old_months = cur.fetchall()

        if not old_months:
            return summary

        # Get the last archive's hash for the chain
        cur.execute("SELECT sha256 FROM tax_ledger_archive ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        previous_sha256 = row[0] if row else None

        for month, count, total_tax in old_months:
            # Skip if already archived
            cur.execute("SELECT id FROM tax_ledger_archive WHERE month = ?", (month,))
            if cur.fetchone():
                continue

            # Pull all rows for this month
            cur.execute("""
                SELECT receipt_no, product_name, quantity, unit_price,
                       tax_rate, tax_amount, payment_method, cashier, created_at
                FROM tax_ledger
                WHERE substr(created_at, 1, 7) = ?
                ORDER BY created_at
            """, (month,))
            rows = cur.fetchall()

            payload = [
                {
                    "receipt_no": r[0],
                    "product_name": r[1],
                    "quantity": r[2],
                    "unit_price": r[3],
                    "tax_rate": r[4],
                    "tax_amount": r[5],
                    "payment_method": r[6],
                    "cashier": r[7],
                    "created_at": r[8],
                }
                for r in rows
            ]

            data_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            data_blob = gzip.compress(data_json, compresslevel=9)
            sha = _hash_blob(data_blob, previous_sha256)

            cur.execute("""
                INSERT INTO tax_ledger_archive
                (month, row_count, total_tax, data_blob, sha256, previous_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                month, len(rows), float(total_tax or 0),
                data_blob, sha, previous_sha256,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))

            summary["archived_months"].append(month)
            summary["rows_moved"] += len(rows)
            previous_sha256 = sha

        # Delete archived rows from live table
        cur.execute("DELETE FROM tax_ledger WHERE substr(created_at, 1, 7) < ?", (cutoff,))
        summary["rows_deleted"] = cur.rowcount

        conn.commit()

    return summary


# ============================================================
#  Reporting
# ============================================================

def get_archive_summary() -> dict:
    """Return archived months + totals."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT month, row_count, total_tax, created_at, sha256
            FROM tax_ledger_archive
            ORDER BY month DESC
        """)
        months = [
            {
                "month": r[0],
                "row_count": r[1],
                "total_tax": round(r[2], 2),
                "archived_at": r[3],
                "sha256_short": r[4][:16] + "...",
            }
            for r in cur.fetchall()
        ]
        cur.execute("SELECT COALESCE(SUM(row_count), 0), COALESCE(SUM(total_tax), 0) FROM tax_ledger_archive")
        total_rows, total_tax = cur.fetchone()

    return {
        "months": months,
        "total_rows": total_rows,
        "total_tax": round(total_tax, 2),
    }


def get_full_tax_summary() -> dict:
    """Combine live + archive tax totals for reporting."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Live
        cur.execute("SELECT COALESCE(SUM(tax_amount), 0) FROM tax_ledger")
        live_tax = cur.fetchone()[0]

        # Archived
        cur.execute("SELECT COALESCE(SUM(total_tax), 0) FROM tax_ledger_archive")
        archived_tax = cur.fetchone()[0]

        # Purged
        cur.execute("SELECT COALESCE(SUM(total_tax), 0) FROM tax_ledger_purged")
        purged_tax = cur.fetchone()[0]

    return {
        "live_tax": round(live_tax, 2),
        "archived_tax": round(archived_tax, 2),
        "purged_tax": round(purged_tax, 2),
        "grand_total": round(live_tax + archived_tax + purged_tax, 2),
    }


# ============================================================
#  Purge (admin-triggered, after retention_years)
# ============================================================

def list_purgeable(retention_years: int = 5) -> list:
    """Return archive months old enough to purge."""
    ensure_tables()
    cutoff_year = datetime.now().year - retention_years
    cutoff = f"{cutoff_year:04d}-12"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT month, row_count, total_tax
            FROM tax_ledger_archive
            WHERE month < ?
            ORDER BY month
        """, (cutoff,))
        rows = cur.fetchall()

    return [
        {"month": r[0], "row_count": r[1], "total_tax": round(r[2], 2)}
        for r in rows
    ]


def purge_month(month: str, admin_name: str) -> dict:
    """Purge one archived month. Writes a permanent manifest row first."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT row_count, total_tax, sha256
            FROM tax_ledger_archive
            WHERE month = ?
        """, (month,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": f"Month {month} not found in archive"}

        row_count, total_tax, sha = row

        # Write manifest FIRST (safety: even if delete fails, we have proof)
        cur.execute("""
            INSERT INTO tax_ledger_purged
            (month, row_count, total_tax, sha256, purged_by, purged_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            month, row_count, float(total_tax or 0), sha,
            admin_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

        # Now delete
        cur.execute("DELETE FROM tax_ledger_archive WHERE month = ?", (month,))
        conn.commit()

    return {
        "ok": True,
        "month": month,
        "rows_purged": row_count,
        "total_tax": round(total_tax, 2),
        "sha256": sha[:16] + "...",
        "purged_by": admin_name,
    }


def get_purge_history() -> list:
    """Every purge ever done (permanent record)."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT month, row_count, total_tax, sha256, purged_by, purged_at
            FROM tax_ledger_purged
            ORDER BY purged_at DESC
        """)
        rows = cur.fetchall()

    return [
        {
            "month": r[0],
            "row_count": r[1],
            "total_tax": round(r[2], 2),
            "sha256_short": r[3][:16] + "...",
            "purged_by": r[4],
            "purged_at": r[5],
        }
        for r in rows
    ]


# ============================================================
#  Integrity check
# ============================================================

def verify_chain() -> dict:
    """Verify the SHA-256 chain is intact."""
    ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, month, data_blob, sha256, previous_sha256
            FROM tax_ledger_archive
            ORDER BY id
        """)
        rows = cur.fetchall()

    if not rows:
        return {"ok": True, "message": "No archives to verify"}

    previous_sha = None
    for rid, month, blob, sha, prev in rows:
        expected = _hash_blob(blob, previous_sha)
        if expected != sha:
            return {
                "ok": False,
                "message": f"Chain broken at {month} (id {rid})",
                "expected": expected[:16] + "...",
                "found": sha[:16] + "...",
            }
        previous_sha = sha

    return {"ok": True, "months_verified": len(rows), "message": "Chain intact"}

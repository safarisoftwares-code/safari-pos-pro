import sqlite3, os
db = os.path.join("database", "safaripos.db")
with sqlite3.connect(db) as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM tax_ledger_archive WHERE month = '2024-01'")
    conn.commit()
    print(f"Removed {cur.rowcount} test archive(s)")
    cur.execute("SELECT COUNT(*) FROM tax_ledger_archive")
    print(f"Remaining archives: {cur.fetchone()[0]}")

import sqlite3, os, time
from database import DB_PATH

print("DB path:", DB_PATH)
print("DB size:", os.path.getsize(DB_PATH), "bytes")
print()

# Check for WAL + SHM files
for ext in ["", "-wal", "-shm"]:
    f = DB_PATH + ext
    if os.path.exists(f):
        print(f"{f}: {os.path.getsize(f)} bytes")

print()
# Open a connection and check for lock state
c = sqlite3.connect(DB_PATH, timeout=2)
try:
    c.execute("BEGIN IMMEDIATE")  # try to acquire write lock
    print("[OK] Acquired write lock instantly - no other writer")
    c.execute("ROLLBACK")
except Exception as e:
    print(f"[LOCKED] Cannot acquire write lock: {e}")
finally:
    c.close()

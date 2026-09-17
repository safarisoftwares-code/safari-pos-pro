from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from database import Base, engine, SessionLocal
from models import User
from auth import hash_password
from routers import (
    auth, products, sales, customers, reports, users,
    backup, settings, purchase_orders, analytics, mpesa, tax, printers,
    print_queue,
)
from services import tax_archiver, print_processor, mpesa_poller
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Safari POS Pro", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
#  No-cache middleware (dev + client - prevents stale JS/CSS)
#  The browser will always re-fetch static files on every load.
#  Since files are served locally, this costs nothing.
# ------------------------------------------------------------
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    # Only apply to HTML/CSS/JS — not to API JSON
    path = request.url.path.lower()
    if path.endswith((".html", ".css", ".js")) or path in ("/", "/login"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ------------------------------------------------------------
#  Routers
# ------------------------------------------------------------
app.include_router(auth.router,            prefix="/api/v1/auth",             tags=["auth"])
app.include_router(products.router,        prefix="/api/v1/products",         tags=["products"])
app.include_router(sales.router,           prefix="/api/v1/sales",            tags=["sales"])
app.include_router(customers.router,       prefix="/api/v1/customers",        tags=["customers"])
app.include_router(reports.router,         prefix="/api/v1/reports",          tags=["reports"])
app.include_router(users.router,           prefix="/api/v1/users",            tags=["users"])
app.include_router(backup.router,          prefix="/api/v1/backup",           tags=["backup"])
app.include_router(settings.router,        prefix="/api/v1/settings",         tags=["settings"])
app.include_router(purchase_orders.router, prefix="/api/v1/purchase-orders",  tags=["purchase-orders"])
app.include_router(analytics.router,       prefix="/api/v1/analytics",        tags=["analytics"])
app.include_router(mpesa.router,           prefix="/api/v1/mpesa",            tags=["mpesa"])
app.include_router(tax.router,             prefix="/api/v1/tax",              tags=["tax"])
app.include_router(printers.router,        prefix="/api/v1/printers",         tags=["printers"])
app.include_router(print_queue.router,     prefix="/api/v1/print-queue",      tags=["print-queue"])

# ------------------------------------------------------------
#  Frontend paths (with PyInstaller EXE support)
# ------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Mount static folders
for sub in ("css", "js", "assets"):
    folder = os.path.join(FRONTEND_DIR, sub)
    if os.path.exists(folder):
        app.mount(f"/static/{sub}", StaticFiles(directory=folder), name=sub)


# ------------------------------------------------------------
#  Frontend pages
# ------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Safari POS Pro</h1><p>index.html not found</p>", status_code=404)


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    login_path = os.path.join(FRONTEND_DIR, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    return HTMLResponse("<h1>Login</h1><p>login.html not found</p>", status_code=404)


# ------------------------------------------------------------
#  Health check (used by launcher splash)
# ------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "4.0.0", "app": "Safari POS Pro"}


# ------------------------------------------------------------
#  Startup: create tables + ensure admin exists
# ------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    try:
        from services import print_processor
        print_processor.stop_worker()
        print("[print-queue] Background worker signalled to stop")
    except Exception as e:
        print(f"[print-queue] Shutdown warning: {e}")
    try:
        from services import mpesa_poller
        mpesa_poller.stop_worker()
        print("[mpesa-poller] Background worker signalled to stop")
    except Exception as e:
        print(f"[mpesa-poller] Shutdown warning: {e}")


@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

    # Ensure tax_ledger table exists (raw SQL, same as v3.0 —
    # Phase 2 will replace with proper 3-tier archive)
    import sqlite3
    from database import DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tax_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_no TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                tax_rate REAL NOT NULL,
                tax_amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                cashier TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tax_created_at ON tax_ledger(created_at)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[startup] tax_ledger setup warning: {e}")

    # Ensure settings table exists
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[startup] settings setup warning: {e}")

    # ------------------------------------------------------------------
    #  Tax Ledger v2 - daily auto-archive (once per 24 hours)
    # ------------------------------------------------------------------
    try:
        import time
        from services import tax_archiver, print_processor

        last_run_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs",
            ".last_archive_run",
        )
        os.makedirs(os.path.dirname(last_run_file), exist_ok=True)

        should_run = True
        if os.path.exists(last_run_file):
            try:
                with open(last_run_file, "r") as f:
                    last_ts = float(f.read().strip())
                if time.time() - last_ts < 86400:  # 24 hours
                    should_run = False
            except (ValueError, OSError):
                pass

        if should_run:
            result = tax_archiver.run_daily_maintenance(retention_months=12)
            with open(last_run_file, "w") as f:
                f.write(str(time.time()))

            log_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "logs",
                "tax_archive.log",
            )
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"cutoff={result['cutoff']} "
                    f"months={result['archived_months']} "
                    f"moved={result['rows_moved']} "
                    f"deleted={result['rows_deleted']}\n"
                )

            if result["archived_months"]:
                print(
                    f"[tax-archive] Archived {len(result['archived_months'])} "
                    f"month(s), moved {result['rows_moved']} row(s)"
                )
    except Exception as e:
        print(f"[tax-archive] WARNING: {e}")

    # ------------------------------------------------------------------
    #  Phase 4: Start print queue background worker
    # ------------------------------------------------------------------
    try:
        from services import print_processor
        print_processor.start_worker()
        print("[print-queue] Background worker started")
    except Exception as e:
        print(f"[print-queue] WARNING: Failed to start worker: {e}")

    # ------------------------------------------------------------------
    #  v4.0 M-Pesa: Start relay poller
    # ------------------------------------------------------------------
    try:
        from services import mpesa_poller
        mpesa_poller.start_worker()
        print("[mpesa-poller] Background worker started")
    except Exception as e:
        print(f"[mpesa-poller] WARNING: Failed to start worker: {e}")

    # ------------------------------------------------------------------
    #  Auto-migrate: ensure all new columns exist in sales table
    # ------------------------------------------------------------------
    try:
        import sqlite3 as _sql
        with _sql.connect(DB_PATH) as _conn:
            _cur = _conn.cursor()
            _cur.execute("PRAGMA table_info(sales)")
            _existing = [c[1] for c in _cur.fetchall()]

            _new_cols = [
                ("payment_status", "TEXT DEFAULT 'paid'"),
                ("mpesa_checkout_id", "TEXT"),
                ("mpesa_receipt", "TEXT"),
                ("paid_at", "TEXT"),
            ]
            _added = 0
            for _name, _defn in _new_cols:
                if _name not in _existing:
                    _cur.execute("ALTER TABLE sales ADD COLUMN " + _name + " " + _defn)
                    _added += 1
            if _added:
                _conn.commit()
                print("[migrate] Added " + str(_added) + " new columns to sales table")
    except Exception as _e:
        print("[migrate] Auto-migration warning: " + str(_e))

    # Ensure admin exists
    db = SessionLocal()
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "info@safarisoftwares.co.ke")
        admin_password = os.getenv("ADMIN_PASSWORD", "info123")
        admin_name = os.getenv("ADMIN_NAME", "Admin")

        admin = db.query(User).filter(User.email == admin_email).first()
        if not admin:
            admin = User(
                name=admin_name,
                email=admin_email,
                password_hash=hash_password(admin_password),
                role="admin",
            )
            db.add(admin)
            db.commit()
            print("")
            print("========================================")
            print("  Safari POS Pro v4.0 started")
            print(f"  Admin: {admin_email}")
            print("  URL:   http://localhost:8001")
            print("========================================")
            print("")
    finally:
        db.close()


# ------------------------------------------------------------
#  Entrypoint
# ------------------------------------------------------------


# ------------------------------------------------------------
#  Shutdown endpoint — called by the app when the user closes it
#  Only accepts from localhost
# ------------------------------------------------------------
from fastapi import Request
import signal

@app.post("/__shutdown__")
async def shutdown(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Only localhost")

    import threading, os as _os
    def _delayed_exit():
        import time
        time.sleep(0.5)
        _os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"message": "Shutting down"}

if __name__ == "__main__":
    import uvicorn
    import io

    # Write PID file so the launcher can find us
    pid_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs",
        "server.pid",
    )
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as pf:
        pf.write(str(os.getpid()))

    # Silence if no console attached
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=None, access_log=False)

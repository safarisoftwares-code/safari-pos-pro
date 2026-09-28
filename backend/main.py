"""
Safari POS Pro - Backend entry point

Two modes:
  1. SERVER mode (default):
       python main.py
       or: SafariPOSPro.exe
     Starts the FastAPI + uvicorn server on port 8001.
     Writes a PID file and blocks until shutdown.

  2. LAUNCHER mode (SafariPOSPro.exe --launcher):
     Used by the desktop shortcut in the packaged EXE.
     - If port 8001 already responds to /health, reuse it (don't spawn a second server)
     - Otherwise spawn a child copy of itself (no --launcher) and wait for /health
     - Open Edge in app-mode pointing at http://localhost:8001/splash
     - When Edge closes, kill the child server (only if we started it)
"""
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
    print_queue, quotations,
)
import services.tax_archiver as tax_archiver
import services.print_processor as print_processor
import services.mpesa_poller as mpesa_poller
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
# ------------------------------------------------------------
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
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
app.include_router(quotations.router,      prefix="/api/v1/quotations",       tags=["quotations"])


# ------------------------------------------------------------
#  Frontend paths (with PyInstaller EXE support)
# ------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
LAUNCHER_DIR = os.path.join(BASE_DIR, "launcher")

for sub in ("css", "js", "assets"):
    folder = os.path.join(FRONTEND_DIR, sub)
    if os.path.exists(folder):
        app.mount(f"/static/{sub}", StaticFiles(directory=folder), name=sub)


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
#  Splash screen (served from FastAPI - no external files)
# ------------------------------------------------------------
@app.get("/splash", response_class=HTMLResponse)
async def serve_splash():
    # Try the bundled splash first, fall back to an inline minimal version
    splash_path = os.path.join(LAUNCHER_DIR, "splash_embedded.html")
    if os.path.exists(splash_path):
        return FileResponse(splash_path)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px;"
        "background:#8b4513;color:white'><h1>Safari POS Pro</h1>"
        "<p>Starting server...</p>"
        "<script>setInterval(async()=>{try{const r=await fetch('/health');"
        "const d=await r.json();if(d.status==='healthy')location.replace('/');}catch(e){}},500);</script>"
        "</body></html>"
    )


# ------------------------------------------------------------
#  Health check
# ------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "4.0.0", "app": "Safari POS Pro"}


# ------------------------------------------------------------
#  Shutdown event
# ------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    try:
        import services.print_processor as pp
        pp.stop_worker()
        print("[print-queue] Background worker signalled to stop")
    except Exception as e:
        print(f"[print-queue] Shutdown warning: {e}")
    try:
        import services.mpesa_poller as mp
        mp.stop_worker()
        print("[mpesa-poller] Background worker signalled to stop")
    except Exception as e:
        print(f"[mpesa-poller] Shutdown warning: {e}")


# ------------------------------------------------------------
#  Startup event
# ------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

    import sqlite3
    from database import DB_PATH

    # tax_ledger table
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

    # settings table
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

    # Tax Ledger v2 - daily auto-archive
    try:
        import time
        last_run_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs", ".last_archive_run",
        )
        os.makedirs(os.path.dirname(last_run_file), exist_ok=True)
        should_run = True
        if os.path.exists(last_run_file):
            try:
                with open(last_run_file, "r") as f:
                    last_ts = float(f.read().strip())
                if time.time() - last_ts < 86400:
                    should_run = False
            except (ValueError, OSError):
                pass
        if should_run:
            result = tax_archiver.run_daily_maintenance(retention_months=12)
            with open(last_run_file, "w") as f:
                f.write(str(time.time()))
            log_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "logs", "tax_archive.log",
            )
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"cutoff={result['cutoff']} months={result['archived_months']} "
                    f"moved={result['rows_moved']} deleted={result['rows_deleted']}\n"
                )
            if result["archived_months"]:
                print(f"[tax-archive] Archived {len(result['archived_months'])} month(s), "
                      f"moved {result['rows_moved']} row(s)")
    except Exception as e:
        print(f"[tax-archive] WARNING: {e}")

    # Print queue background worker
    try:
        print_processor.start_worker()
        print("[print-queue] Background worker started")
    except Exception as e:
        print(f"[print-queue] WARNING: Failed to start worker: {e}")

    # M-Pesa relay poller
    try:
        mpesa_poller.start_worker()
        print("[mpesa-poller] Background worker started")
    except Exception as e:
        print(f"[mpesa-poller] WARNING: Failed to start worker: {e}")

    # Auto-migrate sales table columns
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
#  Shutdown endpoint (localhost-only)
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


# ============================================================
#  LAUNCHER MODE
# ============================================================

def _is_server_up(timeout=1.5):
    """Return True if http://localhost:8001/health responds 200 quickly."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:8001/health")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _wait_for_server_up(max_seconds=30):
    """Poll /health until it responds 200 or timeout. Returns True/False."""
    import time
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        if _is_server_up(timeout=1.0):
            return True
        time.sleep(0.5)
    return False


def _find_edge():
    """Find Microsoft Edge executable path on this machine."""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def run_launcher_mode():
    """
    Native launcher mode: called when EXE is run with --launcher.
    Fully self-contained. No VBS, no subprocess of self, no external files.

    1. If port 8001 already responds -> skip server start (reuse)
    2. Else start the FastAPI server in a daemon thread
    3. Wait for /health
    4. Find Edge
    5. Launch Edge in --app mode at /splash
    6. Wait for THAT Edge process to exit (we own the handle)
    7. os._exit(0) -> kills server thread + everything
    """
    import time, threading, subprocess

    CREATE_NO_WINDOW = 0x08000000

    if not _is_server_up():
        try:
            import uvicorn
            def _run():
                try:
                    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=None, access_log=False)
                except Exception as e:
                    print(f"[launcher] server thread: {e}")
            threading.Thread(target=_run, daemon=True, name="ServerThread").start()
        except Exception as e:
            print(f"[launcher] failed to start server: {e}")
            return 1

        if not _wait_for_server_up(max_seconds=30):
            print("[launcher] server never came up")
            return 1

    edge = _find_edge()
    if not edge:
        print("[launcher] Edge not found")
        return 1

    edge_profile = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", ".edge-profile"
    )
    os.makedirs(edge_profile, exist_ok=True)

    args = [
        edge,
        "--app=http://localhost:8001/splash",
        "--disable-http-cache",
        f"--user-data-dir={edge_profile}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        proc = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        print(f"[launcher] Edge launch failed: {e}")
        return 1

    # Wait for the exact Edge process we launched to exit.
    # No WMI, no window scanning, no timing heuristics. Bulletproof.
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass

    time.sleep(0.5)
    os._exit(0)

# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # Launcher mode?
    if "--launcher" in sys.argv:
        sys.exit(run_launcher_mode())

    # SERVER mode (default)
    import uvicorn
    import io

    # Write PID file so any external tooling can find us
    pid_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "server.pid",
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
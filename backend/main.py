from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from database import Base, engine, SessionLocal
from models import User
from auth import hash_password
from routers import (
    auth, products, sales, customers, reports, users,
    backup, settings, purchase_orders, analytics, mpesa, tax,
)
import os
import sys
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

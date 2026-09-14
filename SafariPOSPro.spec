# -*- mode: python ; coding: utf-8 -*-
"""
Safari POS Pro v4.0 - PyInstaller spec file
Optimized: only bundles headless Chromium (saves ~490 MB)
"""
from PyInstaller.utils.hooks import collect_all
import os

# ============================================================
#  Data files
# ============================================================
datas = [
    ("frontend", "frontend"),
    ("launcher", "launcher"),
    ("Safari-POS-Pro.ico", "."),
    (".env", "."),
]

# ============================================================
#  Playwright - bundle ONLY the headless shell (not full Chromium)
# ============================================================
PLAYWRIGHT_PATH = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")
if os.path.exists(PLAYWRIGHT_PATH):
    # Include headless shell + winldd + .links
    for sub in os.listdir(PLAYWRIGHT_PATH):
        # Skip full chromium-XXXX, ffmpeg
        if sub.startswith("chromium-") and not sub.startswith("chromium_headless"):
            continue
        if sub.startswith("ffmpeg-"):
            continue
        src = os.path.join(PLAYWRIGHT_PATH, sub)
        if os.path.isdir(src):
            datas.append((src, f"ms-playwright/{sub}"))
            print(f"[spec] Bundling Playwright subfolder: {sub}")

# ============================================================
#  Hidden imports
# ============================================================
hiddenimports = [
    "routers.auth", "routers.products", "routers.sales", "routers.customers",
    "routers.reports", "routers.users", "routers.backup", "routers.settings",
    "routers.purchase_orders", "routers.analytics", "routers.mpesa",
    "routers.tax", "routers.printers", "routers.print_queue",
    "services.tax_archiver", "services.print_processor",
    "auth", "database", "models", "schemas", "mpesa",
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "fastapi", "starlette", "starlette.routing", "starlette.staticfiles",
    "pydantic", "pydantic_core",
    "sqlalchemy", "sqlalchemy.dialects", "sqlalchemy.dialects.sqlite",
    "jose", "jose.jwt",
    "passlib", "passlib.handlers", "passlib.handlers.bcrypt",
    "bcrypt", "cryptography",
    "win32print", "win32api", "win32con", "win32ui",
    "playwright", "playwright.sync_api",
    "dotenv", "requests", "jinja2", "aiofiles",
]

# Collect playwright package properly
tmp_ret = collect_all("playwright")
datas += tmp_ret[0]
binaries = tmp_ret[1]
hiddenimports += tmp_ret[2]

# Collect passlib, bcrypt
tmp_ret = collect_all("passlib")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_ret = collect_all("bcrypt")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# ============================================================
#  Analysis
# ============================================================
a = Analysis(
    ["backend/main.py"],
    pathex=["backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib",
        "PIL.ImageQt",
        "passlib.tests",       # test modules - big waste
        "passlib.apache",
        "passlib.apps",
        "passlib.ext",
        "numpy", "pandas",      # not used
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SafariPOSPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="Safari-POS-Pro.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SafariPOSPro",
)

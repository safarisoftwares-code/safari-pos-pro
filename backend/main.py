from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from database import Base, engine
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

# PyInstaller EXE support
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Mount static folders if they exist
if os.path.exists(os.path.join(FRONTEND_DIR, "css")):
    app.mount("/static/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
if os.path.exists(os.path.join(FRONTEND_DIR, "js")):
    app.mount("/static/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
if os.path.exists(os.path.join(FRONTEND_DIR, "assets")):
    app.mount("/static/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "4.0.0", "app": "Safari POS Pro"}

@app.get("/", response_class=HTMLResponse)
async def serve_root():
    # Placeholder — replaced in Phase 1 with real index.html
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Safari POS Pro</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #f5e6d3; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .box { background: white; padding: 40px 60px; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.15); text-align: center; }
            h1 { color: #8b4513; margin: 0 0 10px 0; }
            p { color: #d2691e; font-style: italic; margin: 0; }
            .status { margin-top: 20px; padding: 10px 20px; background: #2e7d32; color: white; border-radius: 8px; display: inline-block; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>SAFARI POS PRO</h1>
            <p>From Vision to Version</p>
            <div class="status">Backend is running — Phase 0.5 skeleton</div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    import io
    import os

    # Write PID file for the launcher to find us
    pid_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "server.pid")
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as pf:
        pf.write(str(os.getpid()))

    # Silence output if running without console (PyInstaller future-proofing)
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=None, access_log=False)
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user
import os
import shutil
import sqlite3
import string
from datetime import datetime

router = APIRouter()

BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "backups",
)
os.makedirs(BACKUP_DIR, exist_ok=True)


def get_backup_location(db):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'backup_location'")
        result = cursor.fetchone()
    return result[0] if result and result[0] else None


def _find_backup(filename: str, source_path: str = None):
    """Locate a backup file across known directories."""
    if ".." in filename or "/" in filename or chr(92) in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    dirs_to_check = []
    if source_path:
        dirs_to_check.append(source_path)

    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "Safari-POS Backup")
    dirs_to_check.append(desktop_folder)
    dirs_to_check.append(BACKUP_DIR)

    for letter in string.ascii_uppercase:
        drive_folder = os.path.join(letter + ":\\", "Safari-POS Backup")
        if os.path.exists(drive_folder):
            dirs_to_check.append(drive_folder)

    for dir_path in dirs_to_check:
        if dir_path and os.path.exists(dir_path):
            candidate = os.path.join(dir_path, filename)
            if os.path.exists(candidate):
                return candidate
    return None


@router.post("/create")
async def create_backup(
    location: str = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create backups")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"safaripos_backup_{timestamp}.db"

    if location and location.strip().lower() == "desktop":
        backup_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Safari-POS Backup")
    elif location and location.strip():
        backup_dir = os.path.join(location.strip(), "Safari-POS Backup")
    else:
        backup_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Safari-POS Backup")

    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, backup_filename)
    shutil.copy2(DB_PATH, backup_path)

    return {
        "message": "Backup created successfully",
        "filename": backup_filename,
        "path": backup_path,
        "saved_to": backup_dir,
    }


@router.get("/list")
async def list_backups(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can view backups")

    backups = []
    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "Safari-POS Backup")

    dirs_to_check = [BACKUP_DIR, desktop_folder]
    for letter in string.ascii_uppercase:
        drive_folder = os.path.join(letter + ":\\", "Safari-POS Backup")
        if os.path.exists(drive_folder):
            dirs_to_check.append(drive_folder)

    ext_location = get_backup_location(db)
    if ext_location and os.path.exists(ext_location):
        dirs_to_check.append(ext_location)

    seen = set()
    for dir_path in dirs_to_check:
        if not os.path.exists(dir_path):
            continue
        for filename in os.listdir(dir_path):
            if filename.endswith(".db") and filename not in seen:
                seen.add(filename)
                filepath = os.path.join(dir_path, filename)
                backups.append({
                    "filename": filename,
                    "size": os.path.getsize(filepath),
                    "created": datetime.fromtimestamp(
                        os.path.getctime(filepath)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "location": dir_path,
                })

    backups.sort(key=lambda x: x["created"], reverse=True)
    return backups


@router.post("/restore/{filename}")
async def restore_backup(
    filename: str,
    source_path: str = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can restore backups")

    backup_path = _find_backup(filename, source_path)
    if not backup_path:
        raise HTTPException(status_code=404, detail="Backup file not found")

    safety_backup = DB_PATH + ".pre_restore"
    shutil.copy2(DB_PATH, safety_backup)
    shutil.copy2(backup_path, DB_PATH)

    return {"message": "Database restored successfully. Restart the server."}


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can download")

    backup_path = _find_backup(filename)
    if not backup_path:
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(backup_path, filename=filename)


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    v4.0 FIX: The old v3.0 endpoint returned fake success without
    actually deleting anything, which was misleading. This endpoint
    is now DISABLED on purpose.

    If you want to remove a backup, delete the .db file manually
    from the Safari-POS Backup folder on your Desktop or flash drive.
    This is intentional — it prevents accidental loss of backups.
    """
    raise HTTPException(
        status_code=405,
        detail=(
            "Backup deletion is disabled for safety. "
            "Delete the .db file manually from the Safari-POS Backup folder."
        ),
    )


@router.get("/drives")
async def detect_drives(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin")

    drives = []
    for letter in string.ascii_uppercase:
        drive = letter + ":\\"
        if os.path.exists(drive):
            drives.append(drive)
    return {"drives": drives}


@router.post("/restore-file")
async def restore_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin")

    safety = DB_PATH + ".pre_restore"
    shutil.copy2(DB_PATH, safety)

    with open(DB_PATH, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"message": "Database restored. Restart server to apply."}


@router.post("/restore-data-only/{filename}")
async def restore_data_only(
    filename: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can restore backups")

    backup_path = _find_backup(filename)
    if not backup_path:
        raise HTTPException(status_code=404, detail="Backup file not found")

    shutil.copy2(DB_PATH, DB_PATH + ".pre_data_restore")

    restored = []
    with sqlite3.connect(backup_path) as source, sqlite3.connect(DB_PATH) as target:
        src = source.cursor()
        tgt = target.cursor()

        tables = ["categories", "products", "customers", "sales",
                  "sale_items", "tax_ledger", "purchase_orders"]

        for table in tables:
            try:
                src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                if not src.fetchone():
                    continue

                tgt.execute(f"PRAGMA table_info({table})")
                tgt_cols = [c[1] for c in tgt.fetchall()]
                src.execute(f"PRAGMA table_info({table})")
                src_cols = [c[1] for c in src.fetchall()]
                common = [c for c in tgt_cols if c in src_cols]

                if not common:
                    continue

                tgt.execute(f"DELETE FROM {table}")
                cols_str = ", ".join(common)
                src.execute(f"SELECT {cols_str} FROM {table}")
                rows = src.fetchall()

                if rows:
                    placeholders = ", ".join(["?"] * len(common))
                    tgt.executemany(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                        rows,
                    )
                restored.append(f"{table} ({len(rows)})")
            except Exception as e:
                print(f"[restore-data-only] {table}: {e}")

        target.commit()

    return {
        "message": "Data restored. Users and settings preserved.",
        "restored_tables": restored,
    }


@router.post("/restore-selective/{filename}")
async def restore_selective(
    filename: str,
    tables: str = "",
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can restore backups")

    allowed = {"products", "categories", "tax_ledger", "sales",
               "sale_items", "purchase_orders"}
    selected = [t.strip() for t in tables.split(",") if t.strip() in allowed]
    if not selected:
        raise HTTPException(status_code=400, detail="No valid tables selected")

    backup_path = _find_backup(filename)
    if not backup_path:
        raise HTTPException(status_code=404, detail="Backup not found")

    shutil.copy2(DB_PATH, DB_PATH + ".pre_selective_restore")

    restored = []
    with sqlite3.connect(backup_path) as source, sqlite3.connect(DB_PATH) as target:
        src = source.cursor()
        tgt = target.cursor()

        for table in selected:
            try:
                src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                if not src.fetchone():
                    continue

                tgt.execute(f"PRAGMA table_info({table})")
                tgt_cols = [c[1] for c in tgt.fetchall()]
                src.execute(f"PRAGMA table_info({table})")
                src_cols = [c[1] for c in src.fetchall()]
                common = [c for c in tgt_cols if c in src_cols]

                if not common:
                    continue

                tgt.execute(f"DELETE FROM {table}")
                cols_str = ", ".join(common)
                src.execute(f"SELECT {cols_str} FROM {table}")
                rows = src.fetchall()

                if rows:
                    placeholders = ", ".join(["?"] * len(common))
                    tgt.executemany(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                        rows,
                    )
                restored.append(f"{table} ({len(rows)})")
            except Exception as e:
                print(f"[restore-selective] {table}: {e}")

        target.commit()

    return {"message": "Selective restore complete", "restored_tables": restored}

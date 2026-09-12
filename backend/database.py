from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
import sys

def find_database_path():
    """Find the database path regardless of script or EXE location."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(exe_dir, "database", "safaripos.db"),
            os.path.join(os.path.dirname(exe_dir), "database", "safaripos.db"),
        ]
        for path in candidates:
            if os.path.exists(os.path.dirname(path)):
                return path
        os.makedirs(os.path.dirname(candidates[0]), exist_ok=True)
        return candidates[0]
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "database", "safaripos.db")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

DB_PATH = find_database_path()
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

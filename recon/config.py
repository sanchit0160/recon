from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RECON_DATA_DIR", BASE_DIR / "data"))
DATA_PATH = DATA_DIR / "last_recon.json"
DB_PATH = DATA_DIR / "app.db"
UPLOADS_DIR = DATA_DIR / "uploads"

DEFAULT_ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB

REQUIRED_ITAM_FIELDS = [
    "itam_id",
    "hostname",
    "region",
    "department",
    "environment",
    "ip_address",
]

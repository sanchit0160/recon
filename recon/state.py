import json
from .config import DATA_PATH

LAST_RECON = None


def load_recon():
    global LAST_RECON
    if not DATA_PATH.exists():
        LAST_RECON = None
        return None
    try:
        LAST_RECON = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return LAST_RECON
    except (OSError, json.JSONDecodeError):
        LAST_RECON = None
        return None


def save_recon(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")


def get_recon():
    return LAST_RECON


def set_recon(data: dict) -> None:
    global LAST_RECON
    LAST_RECON = data

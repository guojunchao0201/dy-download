from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
TEMP_DIR = PROJECT_ROOT / ".tmp"
DB_PATH = DATA_DIR / "tasks.db"
COOKIE_PATH = DATA_DIR / "douyin-cookie.bin"


def ensure_directories() -> None:
    for path in (DATA_DIR, LOG_DIR, DOWNLOAD_DIR, TEMP_DIR):
        path.mkdir(parents=True, exist_ok=True)


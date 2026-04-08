from pathlib import Path

STORAGE_DIR = Path(__file__).parent / "storage"
SESSIONS_DIR = STORAGE_DIR / "sessions"
MAX_UPLOAD_BYTES = 2 * 1024 ** 3  # 2 GB
DEFAULT_MAX_POINTS = 500_000
DECIMATION_CHUNK_SIZE = 100_000

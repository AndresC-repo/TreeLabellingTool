import os
import re
from pathlib import Path

STORAGE_DIR = Path(__file__).parent / "storage"
SESSIONS_DIR = STORAGE_DIR / "sessions"
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES") or 2 * 1024 ** 3)  # 2 GB
DEFAULT_MAX_POINTS = int(os.environ.get("DEFAULT_MAX_POINTS") or 500_000)
DECIMATION_CHUNK_SIZE = 100_000
EXTRACTION_CHUNK_SIZE = 1_000_000  # 10x larger — used by patch extractor

# Training-data folder (mounted by docker-compose from DATASET_DIR_HOST in .env).
# Exports go to <DATASET_DIR>/labels; the dataset registry is stored next to it.
# If it isn't mounted, the tool falls back to storage/dataset inside the Docker volume.
DATASET_DIR = Path(os.environ.get("DATASET_DIR", "/dataset"))

# Who is labelling (LABELLER in .env): added to exported file names so files from
# different people never clash, e.g. Gainesville_3-0_p1_AC_t4.las
LABELLER = re.sub(r"[^A-Za-z0-9-]+", "", os.environ.get("LABELLER", ""))[:16]

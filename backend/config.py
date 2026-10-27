import os
from pathlib import Path

STORAGE_DIR = Path(__file__).parent / "storage"
SESSIONS_DIR = STORAGE_DIR / "sessions"
MAX_UPLOAD_BYTES = 2 * 1024 ** 3  # 2 GB
DEFAULT_MAX_POINTS = 500_000
DECIMATION_CHUNK_SIZE = 100_000
EXTRACTION_CHUNK_SIZE = 1_000_000  # 10x larger — used by patch extractor

# Training-data folder (the NN repo's data/ folder, mounted by docker-compose).
# Exports go to <DATASET_DIR>/labels; the dataset registry is stored next to it.
# If it isn't mounted, the tool falls back to storage/dataset inside the Docker volume.
DATASET_DIR = Path(os.environ.get("DATASET_DIR", "/dataset"))

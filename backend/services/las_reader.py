from __future__ import annotations
import uuid
from pathlib import Path
import numpy as np
import laspy
from config import SESSIONS_DIR, DECIMATION_CHUNK_SIZE

CANDIDATE_FIELDS = ["classification", "intensity", "number_of_returns"]

XY_CACHE_FILE   = "xy_cache.npy"
XY_OFFSETS_FILE = "xy_offsets.npy"


def get_session_dir(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def get_xy_cache_paths(session_id: str) -> tuple[Path, Path]:
    d = get_session_dir(session_id)
    return d / XY_CACHE_FILE, d / XY_OFFSETS_FILE


def create_session() -> str:
    session_id = str(uuid.uuid4())
    d = get_session_dir(session_id)
    d.mkdir(parents=True)
    (d / "patches").mkdir()
    (d / "outputs").mkdir()
    return session_id


def get_las_path(session_id: str) -> Path:
    d = get_session_dir(session_id)
    for name in ("original.las", "original.laz"):
        p = d / name
        if p.exists():
            return p
    return d / "original.las"  # fallback (will 404 if missing)


def read_metadata(session_id: str) -> dict:
    las_path = get_las_path(session_id)
    cache_path, offsets_path = get_xy_cache_paths(session_id)

    with laspy.open(las_path) as f:
        count = f.header.point_count
        x_min, x_max = float("inf"), float("-inf")
        y_min, y_max = float("inf"), float("-inf")
        z_min, z_max = float("inf"), float("-inf")
        dim_names = None
        x_chunks: list = []
        y_chunks: list = []

        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
            if dim_names is None:
                dim_names = set(chunk.point_format.dimension_names)
            cx = np.asarray(chunk.x, dtype=np.float64)
            cy = np.asarray(chunk.y, dtype=np.float64)
            x_min = min(x_min, float(cx.min()))
            x_max = max(x_max, float(cx.max()))
            y_min = min(y_min, float(cy.min()))
            y_max = max(y_max, float(cy.max()))
            z_min = min(z_min, float(chunk.z.min()))
            z_max = max(z_max, float(chunk.z.max()))
            x_chunks.append(cx)
            y_chunks.append(cy)

    # Build xy coordinate cache in relative float32 space.
    # Storing (x - x_min, y - y_min) keeps values small (tile extent),
    # giving sub-mm float32 precision even for large UTM coordinates.
    x_all = np.concatenate(x_chunks)
    y_all = np.concatenate(y_chunks)
    offsets = np.array([x_min, y_min], dtype=np.float64)
    xy = np.stack(
        [(x_all - x_min).astype(np.float32),
         (y_all - y_min).astype(np.float32)],
        axis=1,
    )
    np.save(str(cache_path), xy)
    np.save(str(offsets_path), offsets)
    del x_all, y_all, xy  # release memory

    available = [f for f in CANDIDATE_FIELDS if dim_names and f in dim_names]
    # Fallback: if no fields found, include all candidates (some LAS files expose different dim names)
    if not available:
        available = CANDIDATE_FIELDS[:]

    return {
        "point_count": count,
        "bounds": {
            "x": [x_min, x_max],
            "y": [y_min, y_max],
            "z": [z_min, z_max],
        },
        "available_fields": available,
    }

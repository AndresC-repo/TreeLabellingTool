import uuid
from pathlib import Path
import laspy
from config import SESSIONS_DIR, DECIMATION_CHUNK_SIZE

CANDIDATE_FIELDS = ["classification", "intensity", "number_of_returns"]


def get_session_dir(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


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
    with laspy.open(las_path) as f:
        count = f.header.point_count
        x_min, x_max = float("inf"), float("-inf")
        y_min, y_max = float("inf"), float("-inf")
        z_min, z_max = float("inf"), float("-inf")
        dim_names = None
        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
            if dim_names is None:
                dim_names = set(chunk.point_format.dimension_names)
            x_min = min(x_min, float(chunk.x.min()))
            x_max = max(x_max, float(chunk.x.max()))
            y_min = min(y_min, float(chunk.y.min()))
            y_max = max(y_max, float(chunk.y.max()))
            z_min = min(z_min, float(chunk.z.min()))
            z_max = max(z_max, float(chunk.z.max()))

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

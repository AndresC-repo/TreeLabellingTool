"""In-memory cache of decimated point data per session (all scalar fields in one read)."""
from __future__ import annotations
import laspy
from services.decimator import read_decimated
from config import DEFAULT_MAX_POINTS

_BASE_FIELDS = ["x", "y", "z", "classification", "intensity", "number_of_returns"]
_cache: dict[str, dict] = {}


def _has_label_dim(las_path) -> bool:
    """Return True if the file has a full-range int32 'label' extra bytes dimension."""
    try:
        # Read a single-chunk sample to check for the extra dim via chunk attributes
        with laspy.open(las_path) as f:
            for chunk in f.chunk_iterator(1):
                return hasattr(chunk, "label")
        return False
    except Exception:
        return False


def get_session_points(session_id: str, las_path, max_points: int = DEFAULT_MAX_POINTS) -> dict:
    """Return cached dict with keys: data (dict of arrays), total (int). Reads file on first call."""
    if session_id not in _cache:
        if _has_label_dim(las_path):
            # Use the int32 label dim as classification (supports values > 255)
            fields = ["x", "y", "z", "label", "intensity", "number_of_returns"]
            data, total = read_decimated(las_path, max_points, fields)
            data["classification"] = data.pop("label")
        else:
            data, total = read_decimated(las_path, max_points, _BASE_FIELDS)
        _cache[session_id] = {"data": data, "total": total}
    return _cache[session_id]


def evict(session_id: str) -> None:
    _cache.pop(session_id, None)

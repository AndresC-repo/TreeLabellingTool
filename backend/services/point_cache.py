"""In-memory cache of decimated point data per session (all scalar fields in one read)."""
from __future__ import annotations
from services.decimator import read_decimated
from config import DEFAULT_MAX_POINTS

_FIELDS = ["x", "y", "classification", "intensity", "number_of_returns"]
_cache: dict[str, dict] = {}


def get_session_points(session_id: str, las_path, max_points: int = DEFAULT_MAX_POINTS) -> dict:
    """Return cached dict with keys: data (dict of arrays), total (int). Reads file on first call."""
    if session_id not in _cache:
        data, total = read_decimated(las_path, max_points, _FIELDS)
        _cache[session_id] = {"data": data, "total": total}
    return _cache[session_id]


def evict(session_id: str) -> None:
    _cache.pop(session_id, None)

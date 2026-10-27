"""Persisted 2D selections (regions) per session, stored in <session>/regions.json.

The frontend used to keep regions only in memory, so they vanished on reload or
file switch while the patches stayed on disk. This keeps the outline, patch number
and "labelled" flag next to the patches so the 2D view can restore them.
"""
from __future__ import annotations
import json
import shutil
import threading
import time
from pathlib import Path

from services.las_reader import get_session_dir

_lock = threading.Lock()   # sync endpoints run in a threadpool


def _path(session_id: str) -> Path:
    return get_session_dir(session_id) / "regions.json"


def _load(session_id: str) -> dict:
    p = _path(session_id)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(session_id: str, data: dict) -> None:
    p = _path(session_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(p)   # atomic, so a crash never leaves half a file


def max_patch_number(session_id: str) -> int:
    return max((r.get("patch_number", 0) for r in _load(session_id).values()), default=0)


def add_region(session_id: str, patch_id: str, patch_number: int, point_count: int,
               selection_type: str, bounds_2d: dict | None, polygon_2d: list | None) -> None:
    with _lock:
        data = _load(session_id)
        data[patch_id] = {
            "patch_id": patch_id,
            "patch_number": patch_number,
            "point_count": point_count,
            "selection_type": selection_type,
            "bounds_2d": bounds_2d,
            "polygon_2d": polygon_2d,
            "labelled": False,
            "created": time.time(),
        }
        _save(session_id, data)


def mark_labelled(session_id: str, patch_id: str) -> None:
    with _lock:
        data = _load(session_id)
        r = data.get(patch_id)
        if r and not r.get("labelled"):
            r["labelled"] = True
            _save(session_id, data)


def list_regions(session_id: str) -> list[dict]:
    """Regions whose patch file still exists, oldest first."""
    patch_dir = get_session_dir(session_id) / "patches"
    regions = [r for pid, r in _load(session_id).items() if (patch_dir / f"{pid}.las").exists()]
    return sorted(regions, key=lambda r: (r.get("patch_number", 0), r.get("created", 0)))


def remove_region(session_id: str, patch_id: str) -> bool:
    """Delete the patch file, its saved outputs and the region entry. Returns False if unknown."""
    session_dir = get_session_dir(session_id)
    patch_path = session_dir / "patches" / f"{patch_id}.las"
    existed = patch_path.exists()
    patch_path.unlink(missing_ok=True)
    shutil.rmtree(session_dir / "outputs" / patch_id, ignore_errors=True)
    with _lock:
        data = _load(session_id)
        existed = data.pop(patch_id, None) is not None or existed
        if session_dir.exists():
            _save(session_id, data)
    return existed

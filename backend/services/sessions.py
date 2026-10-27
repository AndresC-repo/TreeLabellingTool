"""Session lifecycle helpers: keep-alive, patch counting and full removal."""
from __future__ import annotations
import os
import re
import shutil
import uuid

from services.las_reader import get_session_dir
from services import point_cache
from services import label_manager as lm

# Matches /api/v1/{files|view|patches}/<uuid>/...
_SESSION_URL = re.compile(r"^/api/v1/(?:files|view|patches)/([0-9a-fA-F-]{36})(?:/|$)")


def is_valid_session_id(session_id: str) -> bool:
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False


def session_id_from_path(path: str) -> str | None:
    m = _SESSION_URL.match(path)
    return m.group(1) if m else None


def touch_session(session_id: str) -> None:
    """Mark a session as recently used so the idle cleanup leaves it alone."""
    d = get_session_dir(session_id)
    try:
        if d.is_dir():
            os.utime(d, None)
    except OSError:
        pass


def list_patch_ids(session_id: str) -> list[str]:
    patch_dir = get_session_dir(session_id) / "patches"
    return [p.stem for p in patch_dir.glob("*.las")] if patch_dir.exists() else []


def purge_session(session_id: str) -> int:
    """Delete a session's files and all in-memory state. Returns the number of patches removed.

    Training examples (storage/training) are not touched.
    """
    patch_ids = list_patch_ids(session_id)

    point_cache.evict(session_id)
    try:
        from services.renderer2d import invalidate_session
        invalidate_session(session_id)
    except Exception:
        pass
    lm.forget_session(session_id, patch_ids)
    try:
        from services.predictor import _NN_CACHE
        for pid in patch_ids:
            for k in [k for k in list(_NN_CACHE) if f":{pid}:" in k]:
                _NN_CACHE.pop(k, None)
    except Exception:
        pass

    try:
        from services import dataset_registry as dreg
        dreg.forget_session(session_id)   # unsaved patches of this file are gone
    except Exception:
        pass
    shutil.rmtree(get_session_dir(session_id), ignore_errors=True)
    return len(patch_ids)

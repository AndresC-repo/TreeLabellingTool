"""Full-resolution per-point field arrays on disk, memory-mapped on demand.

The overview image is drawn from a decimated sample (~500k points). When the user
zooms in, the zoomed image is drawn from every point in view instead; these arrays
make that fast without re-reading the LAS file. Each field is built the first time
it is needed, in the same point order as xy_cache.npy (written at upload).
"""
from __future__ import annotations
import threading
import numpy as np
import laspy

from config import DECIMATION_CHUNK_SIZE
from services.las_reader import get_session_dir, get_xy_cache_paths, read_metadata

# field name used by the API -> (file stem, dtype)
_FIELDS = {
    "elevation":         ("full_z",       np.float32),
    "classification":    ("full_cls",     np.int32),
    "intensity":         ("full_int",     np.uint16),
    "number_of_returns": ("full_returns", np.uint8),
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _session_lock(session_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


def _source_dim(chunk, field: str) -> np.ndarray:
    if field == "elevation":
        return np.asarray(chunk.z)
    if field == "classification":
        # Same rule as point_cache: prefer the int32 'label' extra dim (values > 255)
        if "label" in chunk.point_format.extra_dimension_names:
            return np.asarray(chunk.label)
        return np.asarray(chunk.classification)
    return np.asarray(getattr(chunk, field))


def get_xy(session_id: str) -> tuple[np.ndarray, np.ndarray]:
    """(N,2) float32 memmap of x,y relative to offsets, and the float64 offsets."""
    cache_path, offsets_path = get_xy_cache_paths(session_id)
    if not cache_path.exists() or not offsets_path.exists():
        read_metadata(session_id)   # older session without the cache: build it once
    return np.load(str(cache_path), mmap_mode="r"), np.load(str(offsets_path))


def get_field(session_id: str, las_path, field: str) -> np.ndarray:
    stem, dtype = _FIELDS[field]
    path = get_session_dir(session_id) / f"{stem}.npy"
    if not path.exists():
        with _session_lock(session_id):
            if not path.exists():
                tmp = path.with_name(f"{stem}.tmp.npy")
                with laspy.open(las_path) as f:
                    out = np.lib.format.open_memmap(tmp, mode="w+", dtype=dtype, shape=(f.header.point_count,))
                    pos = 0
                    for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
                        vals = _source_dim(chunk, field)
                        out[pos:pos + len(vals)] = vals.astype(dtype, copy=False)
                        pos += len(vals)
                    out.flush()
                    del out
                tmp.replace(path)
    return np.load(str(path), mmap_mode="r")

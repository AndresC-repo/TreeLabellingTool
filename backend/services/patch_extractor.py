from __future__ import annotations
from pathlib import Path
from typing import Optional
import uuid
import numpy as np
import laspy
from config import DECIMATION_CHUNK_SIZE, EXTRACTION_CHUNK_SIZE
from services.las_reader import get_session_dir, get_las_path, get_xy_cache_paths


def polygon_contains(px: np.ndarray, py: np.ndarray, poly: list) -> np.ndarray:
    """Vectorized ray-casting point-in-polygon test. Returns boolean mask."""
    poly = np.array(poly, dtype=np.float64)
    n = len(poly)
    inside = np.zeros(len(px), dtype=bool)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cond = (yi > py) != (yj > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_intersect = (xj - xi) * (py - yi) / (yj - yi) + xi
        inside ^= cond & (px < x_intersect)
        j = i
    return inside


# ── Public entry point ────────────────────────────────────────────────────────

def extract_patch(
    session_id: str,
    selection_type: str,
    bounds_2d: Optional[dict],
    polygon_2d: Optional[list],
) -> dict:
    las_path = get_las_path(session_id)
    cache_path, offsets_path = get_xy_cache_paths(session_id)
    patch_id = str(uuid.uuid4())
    patch_dir = get_session_dir(session_id) / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{patch_id}.las"

    # Fast path: use xy cache if available
    try:
        if cache_path.exists() and offsets_path.exists():
            return _extract_cached(
                las_path, cache_path, offsets_path, patch_path, patch_id,
                selection_type, bounds_2d, polygon_2d,
            )
    except Exception:
        pass  # corrupt/incomplete cache — fall through to legacy

    return _extract_legacy(
        las_path, patch_path, patch_id, selection_type, bounds_2d, polygon_2d,
    )


# ── Fast path (uses xy_cache.npy) ─────────────────────────────────────────────

def _extract_cached(
    las_path, cache_path, offsets_path, patch_path, patch_id,
    selection_type, bounds_2d, polygon_2d,
) -> dict:
    offsets = np.load(str(offsets_path))
    x_off, y_off = float(offsets[0]), float(offsets[1])

    # Load as memmap — no full RAM copy, OS pages in only what's needed
    xy = np.load(str(cache_path), mmap_mode="r")
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise ValueError("Unexpected cache shape")

    # One vectorized mask over all N points (float32, no laspy involved)
    mask = _compute_mask(xy, x_off, y_off, selection_type, bounds_2d, polygon_2d)
    selected = np.where(mask)[0]  # sorted ascending int64

    if len(selected) == 0:
        return _empty(patch_id)

    # One pass through the .las file with 10x larger chunks.
    # np.searchsorted locates which chunk rows to extract in O(log K).
    x_all, y_all, z_all = [], [], []
    class_all, int_all, ret_all, label_all = [], [], [], []
    has_label_dim = None
    src_header = None
    offset = 0

    with laspy.open(las_path) as f:
        src_header = f.header
        for chunk in f.chunk_iterator(EXTRACTION_CHUNK_SIZE):
            clen = len(chunk)
            lo = int(np.searchsorted(selected, offset))
            hi = int(np.searchsorted(selected, offset + clen))
            if lo < hi:
                if has_label_dim is None:
                    has_label_dim = hasattr(chunk, "label")
                idx = selected[lo:hi] - offset   # local row positions in this chunk
                x_all.append(np.asarray(chunk.x)[idx])
                y_all.append(np.asarray(chunk.y)[idx])
                z_all.append(np.asarray(chunk.z)[idx])
                class_all.append(np.asarray(chunk.classification)[idx])
                int_all.append(np.asarray(chunk.intensity)[idx])
                ret_all.append(np.asarray(chunk.number_of_returns)[idx])
                if has_label_dim:
                    label_all.append(np.asarray(chunk.label)[idx])
            offset += clen

    if not x_all:
        return _empty(patch_id)

    return _write_patch(
        patch_id, patch_path, src_header,
        x_all, y_all, z_all, class_all, int_all, ret_all, label_all,
    )


def _compute_mask(xy, x_off, y_off, selection_type, bounds_2d, polygon_2d) -> np.ndarray:
    """Compute boolean mask using cached relative float32 coordinates."""
    xr, yr = xy[:, 0], xy[:, 1]  # float32 views, no copy

    if selection_type == "rectangle" and bounds_2d:
        return (
            (xr >= bounds_2d["x_min"] - x_off) & (xr <= bounds_2d["x_max"] - x_off) &
            (yr >= bounds_2d["y_min"] - y_off) & (yr <= bounds_2d["y_max"] - y_off)
        )

    if selection_type == "polygon" and polygon_2d and len(polygon_2d) >= 3:
        rel = [[v[0] - x_off, v[1] - y_off] for v in polygon_2d]
        pa = np.array(rel)
        bbox = (
            (xr >= pa[:, 0].min()) & (xr <= pa[:, 0].max()) &
            (yr >= pa[:, 1].min()) & (yr <= pa[:, 1].max())
        )
        if not bbox.any():
            return bbox
        full = np.zeros(len(xr), dtype=bool)
        full[bbox] = polygon_contains(
            xr[bbox].astype(np.float64), yr[bbox].astype(np.float64), rel
        )
        return full

    return np.zeros(len(xr), dtype=bool)


# ── Legacy path (original chunk-scan, used as fallback) ──────────────────────

def _extract_legacy(
    las_path, patch_path, patch_id, selection_type, bounds_2d, polygon_2d,
) -> dict:
    x_all, y_all, z_all = [], [], []
    class_all, int_all, ret_all = [], [], []
    label_all = []

    poly_bbox = None
    if selection_type == "polygon" and polygon_2d:
        poly_arr = np.array(polygon_2d)
        poly_bbox = {
            "x_min": float(poly_arr[:, 0].min()),
            "x_max": float(poly_arr[:, 0].max()),
            "y_min": float(poly_arr[:, 1].min()),
            "y_max": float(poly_arr[:, 1].max()),
        }

    with laspy.open(las_path) as f:
        src_header = f.header
        has_label_dim = None
        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
            if has_label_dim is None:
                has_label_dim = hasattr(chunk, "label")
            cx = np.asarray(chunk.x, dtype=np.float64)
            cy = np.asarray(chunk.y, dtype=np.float64)

            if selection_type == "rectangle" and bounds_2d:
                mask = (
                    (cx >= bounds_2d["x_min"]) & (cx <= bounds_2d["x_max"]) &
                    (cy >= bounds_2d["y_min"]) & (cy <= bounds_2d["y_max"])
                )
            elif selection_type == "polygon" and polygon_2d:
                if poly_bbox is None:
                    continue
                bbox_mask = (
                    (cx >= poly_bbox["x_min"]) & (cx <= poly_bbox["x_max"]) &
                    (cy >= poly_bbox["y_min"]) & (cy <= poly_bbox["y_max"])
                )
                if not bbox_mask.any():
                    continue
                mask = np.zeros(len(cx), dtype=bool)
                mask[bbox_mask] = polygon_contains(
                    cx[bbox_mask], cy[bbox_mask], polygon_2d
                )
            else:
                continue

            if not mask.any():
                continue

            x_all.append(np.asarray(chunk.x)[mask])
            y_all.append(np.asarray(chunk.y)[mask])
            z_all.append(np.asarray(chunk.z)[mask])
            class_all.append(np.asarray(chunk.classification)[mask])
            int_all.append(np.asarray(chunk.intensity)[mask])
            ret_all.append(np.asarray(chunk.number_of_returns)[mask])
            if has_label_dim:
                label_all.append(np.asarray(chunk.label)[mask])

    if not x_all:
        return _empty(patch_id)

    return _write_patch(
        patch_id, patch_path, src_header,
        x_all, y_all, z_all, class_all, int_all, ret_all, label_all,
    )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _write_patch(patch_id, patch_path, src_header,
                 x_all, y_all, z_all, class_all, int_all, ret_all, label_all) -> dict:
    x = np.concatenate(x_all)
    y = np.concatenate(y_all)
    z = np.concatenate(z_all)
    classification = np.concatenate(class_all)
    intensity = np.concatenate(int_all)
    returns = np.concatenate(ret_all)
    full_labels = (
        np.concatenate(label_all).astype(np.int32)
        if label_all
        else classification.astype(np.int32)
    )

    new_las = laspy.LasData(
        header=laspy.LasHeader(
            point_format=src_header.point_format,
            version=src_header.version,
        )
    )
    new_las.x = x
    new_las.y = y
    new_las.z = z
    new_las.classification = classification.astype(np.uint8)
    new_las.intensity = intensity.astype(np.uint16)
    new_las.number_of_returns = returns.astype(np.uint8)
    new_las.write(str(patch_path))

    return {
        "patch_id": patch_id,
        "point_count": int(len(x)),
        "bounds_3d": {
            "x": [float(x.min()), float(x.max())],
            "y": [float(y.min()), float(y.max())],
            "z": [float(z.min()), float(z.max())],
        },
        "classification": full_labels,
    }


def _empty(patch_id: str) -> dict:
    return {
        "patch_id": patch_id,
        "point_count": 0,
        "bounds_3d": {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0]},
    }

from pathlib import Path
import uuid
import numpy as np
import laspy
from config import DECIMATION_CHUNK_SIZE
from services.las_reader import get_session_dir, get_las_path


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


def extract_patch(
    session_id: str,
    selection_type: str,
    bounds_2d: dict | None,
    polygon_2d: list | None,
) -> dict:
    las_path = get_las_path(session_id)
    patch_id = str(uuid.uuid4())
    patch_dir = get_session_dir(session_id) / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{patch_id}.las"

    x_all, y_all, z_all = [], [], []
    class_all, int_all, ret_all = [], [], []

    # Pre-compute polygon bbox for polygon selections (avoid recomputing per chunk)
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
        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
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

    if not x_all:
        return {
            "patch_id": patch_id,
            "point_count": 0,
            "bounds_3d": {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0]},
        }

    x = np.concatenate(x_all)
    y = np.concatenate(y_all)
    z = np.concatenate(z_all)
    classification = np.concatenate(class_all)
    intensity = np.concatenate(int_all)
    returns = np.concatenate(ret_all)

    # Write patch .las using same point format as source
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
        "classification": classification,
    }

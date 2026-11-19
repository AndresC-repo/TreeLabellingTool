"""Lat/lon for the 3D view's hover probe (🌐).

The browser has no map-projection library, so the backend fits, once per patch, a quadratic
formula  lon, lat = f(x, y)  from the file's coordinate system to WGS84 over the patch area.
Over a patch (hundreds of metres) the formula is far below a centimetre off; the worst
error on a check grid is returned so the panel can show it.
"""
from __future__ import annotations

import math

import laspy
import numpy as np
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


def _terms(u, v):
    return np.c_[np.ones_like(u), u, v, u * u, u * v, v * v]


@router.get("/{session_id}/{patch_id}/lonlat-fit")
def lonlat_fit(session_id: str, patch_id: str):
    """{available, crs, cx, cy, scale, lon: [6], lat: [6], max_error_m}.
    lon = c . [1, u, v, u², uv, v²] with u = (X - cx) / scale, v = (Y - cy) / scale,
    X/Y in the file's coordinates (the 3D view adds its local origin back first)."""
    from pyproj import CRS, Transformer
    from routers.patches import get_patch_path
    from services.location import crs_label, file_crs

    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    crs = file_crs(patch_path)
    if crs is None:
        try:
            from services.las_reader import get_las_path
            crs = file_crs(get_las_path(session_id))
        except Exception:
            crs = None
    if crs is None:
        return {"available": False, "crs": "", "reason": "The file has no coordinate system."}

    with laspy.open(str(patch_path)) as f:
        h = f.header
        x0, y0, x1, y1 = float(h.mins[0]), float(h.mins[1]), float(h.maxs[0]), float(h.maxs[1])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    scale = max(x1 - x0, y1 - y0, 1.0) / 2

    tr = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    gx, gy = np.meshgrid(np.linspace(x0, x1, 9), np.linspace(y0, y1, 9))
    gx, gy = gx.ravel(), gy.ravel()
    lon, lat = tr.transform(gx, gy)
    lon, lat = np.asarray(lon), np.asarray(lat)
    if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
        return {"available": False, "crs": crs_label(crs), "reason": "Coordinates can't be converted."}
    A = _terms((gx - cx) / scale, (gy - cy) / scale)
    c_lon = np.linalg.lstsq(A, lon, rcond=None)[0]
    c_lat = np.linalg.lstsq(A, lat, rcond=None)[0]

    # check on a finer grid, in metres
    tx, ty = np.meshgrid(np.linspace(x0, x1, 23), np.linspace(y0, y1, 23))
    tx, ty = tx.ravel(), ty.ravel()
    tlon, tlat = tr.transform(tx, ty)
    B = _terms((tx - cx) / scale, (ty - cy) / scale)
    dlat = (B @ c_lat - np.asarray(tlat)) * 111_320
    dlon = (B @ c_lon - np.asarray(tlon)) * 111_320 * math.cos(math.radians(float(np.mean(tlat))))
    err = float(np.max(np.hypot(dlat, dlon)))

    return {"available": True, "crs": crs_label(crs), "cx": cx, "cy": cy, "scale": scale,
            "lon": c_lon.tolist(), "lat": c_lat.tolist(), "max_error_m": round(err, 5)}

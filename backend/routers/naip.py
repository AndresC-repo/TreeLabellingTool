"""NAIP layers for the 2D and 3D views (optional `naip` container, `make naip`).

Five layers, each switched on/off in the views:
  RGB / NDVI      NAIP aerial image (USDA, 0.6 m), resampled onto the file's own coordinates
  Ventura         trees found in the image by the model of Ventura et al. (California-trained)
  True labels     hand-placed tree positions of Ventura et al. (urban-tree-detection-data, CC BY 4.0)
  Labelled area   the image crops those hand labels cover (labels exist only inside them)

POST /api/v1/naip/{sid}/tile          whole loaded file (2D view)
POST /api/v1/naip/{sid}/{pid}/patch   one patch (3D view); points also get the lidar top and ground z
Without the container both answer 503 and the rest of the tool is unaffected.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import laspy
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from scipy.spatial import cKDTree

from services.units import get_session_units

router = APIRouter(prefix="/api/v1/naip", tags=["naip"])

NAIP_URL = os.environ.get("NAIP_SERVICE_URL", "http://naip:8001")


class LayersRequest(BaseModel):
    year: int | None = None     # NAIP year; None = newest


def _call(path: str, payload: dict | None = None, timeout: float = 900):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(NAIP_URL + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", str(e))
        except Exception:
            detail = str(e)
        raise HTTPException(e.code, detail)
    except Exception:
        raise HTTPException(503, "The NAIP service is not running. Start the tool with `make naip` "
                                 "(or `make prod-naip`) to use the NAIP layers.")


def _crs_of(*paths):
    from services.location import file_crs
    for p in paths:
        try:
            crs = file_crs(p)
        except Exception:
            crs = None
        if crs is not None:
            return crs
    raise HTTPException(400, "The file has no coordinate system, so the image can't be placed.")


def _payload(res: dict, ventura: list, truth: list) -> dict:
    return {
        "year": res.get("year"), "years": res.get("years", []), "items": res.get("items", []),
        "bounds": res["bounds"], "rgb_png": res["rgb_png"], "ndvi_png": res["ndvi_png"],
        "model": res.get("model", False), "note": res.get("note", ""),
        "ventura": ventura, "truth": truth, "crops": res.get("hand_crops", []),
    }


@router.get("/status")
def status():
    """{"running": bool, "model": bool} — the panels use this to enable their buttons."""
    try:
        r = _call("/health", timeout=3)
        return {"running": True, "model": bool(r.get("model"))}
    except HTTPException:
        return {"running": False, "model": False}


@router.post("/{session_id}/tile")
def tile_layers(session_id: str, req: LayersRequest):
    """Layers for the whole loaded file (2D view). Points: {x, y} (+ year, crop for true labels)."""
    from services.las_reader import get_las_path
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")
    crs = _crs_of(las_path)
    with laspy.open(str(las_path)) as f:
        h = f.header
        bounds = [float(h.mins[0]), float(h.mins[1]), float(h.maxs[0]), float(h.maxs[1])]
    scale = float(get_session_units(session_id)["scale"])
    res = _call("/hints", {"bounds": bounds, "crs_wkt": crs.to_wkt(), "unit_scale": scale, "year": req.year})
    ventura = [{"x": t[0], "y": t[1]} for t in res.get("trees", [])]
    truth = [{"x": t[0], "y": t[1], "year": t[2], "crop": t[3]} for t in res.get("hand_labels", [])]
    return _payload(res, ventura, truth)


@router.post("/{session_id}/{patch_id}/patch")
def patch_layers(session_id: str, patch_id: str, req: LayersRequest):
    """Layers for one patch (3D view). Points also carry z (highest lidar point within 2.5 m)
    and ground_z, so the 3D view can draw them as dots on top with a line to the ground."""
    from routers.patches import get_patch_path
    from services.las_reader import get_las_path
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    crs = _crs_of(patch_path, get_las_path(session_id))

    las = laspy.read(str(patch_path))
    x = np.asarray(las.x, np.float64)
    y = np.asarray(las.y, np.float64)
    z = np.asarray(las.z, np.float64)
    asprs = np.asarray(las.classification, np.int32)
    scale = float(get_session_units(session_id)["scale"])          # metres per unit
    bounds = [float(x.min()), float(y.min()), float(x.max()), float(y.max())]
    res = _call("/hints", {"bounds": bounds, "crs_wkt": crs.to_wkt(), "unit_scale": scale, "year": req.year})

    ground = asprs == 2
    gtree = cKDTree(np.c_[x[ground], y[ground]]) if ground.sum() >= 5 else None
    z_low = float(np.percentile(z, 2)) if len(z) else 0.0
    xy = cKDTree(np.c_[x, y])
    r = 2.5 / scale

    def heights(px, py):
        if gtree is not None:
            _, gi = gtree.query([px, py], k=min(8, int(ground.sum())))
            gz = float(np.median(z[ground][np.atleast_1d(gi)]))
        else:
            gz = z_low
        near = xy.query_ball_point([px, py], r)
        return (float(z[near].max()) if near else gz), gz

    def inside(px, py):
        return bounds[0] <= px <= bounds[2] and bounds[1] <= py <= bounds[3]

    ventura = []
    for t in res.get("trees", []):
        if inside(t[0], t[1]):
            top, gz = heights(t[0], t[1])
            ventura.append({"x": t[0], "y": t[1], "z": top, "ground_z": gz})
    truth = []
    for t in res.get("hand_labels", []):
        top, gz = heights(t[0], t[1])
        truth.append({"x": t[0], "y": t[1], "year": t[2], "crop": t[3], "z": top, "ground_z": gz})
    out = _payload(res, ventura, truth)
    out["ground_z"] = z_low
    return out

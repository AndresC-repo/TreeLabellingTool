"""Height of every labelled tree in a LAS file, in metres.

Height = highest point of the tree minus the ground under that point (median Z of the
20 nearest ground points: the file's class 2, else labelled 2 in the tool; else the nearest
non-tree points). Used by the Dataset overview to find suspiciously small trees.
"""
from __future__ import annotations
import numpy as np
import laspy
from scipy.spatial import cKDTree

from services.units import UNITS, detect_units

HEIGHTS_VERSION = 4          # 4: + patch centre lat/lon          # bump to make the next rescan re-measure every file
SHORT_TREE_M = 2.5          # trees below this are flagged in the Dataset overview
MAX_PLAUSIBLE_TREE_M = 45.0  # taller usually means feet read as metres


def _labels(las) -> np.ndarray:
    if "label" in las.point_format.extra_dimension_names:
        lab = np.asarray(las.label)
        if (lab >= 100).any():
            return lab
    return np.asarray(las.classification).astype(np.int32)


def tree_heights(las, scale: float) -> list[float]:
    """Height in metres of each tree (label >= 100), sorted ascending."""
    lab = _labels(las)
    trees = np.unique(lab[lab >= 100])
    if trees.size == 0:
        return []
    xyz = np.c_[las.x, las.y, las.z].astype(np.float64)
    # ground: the file's class 2, else points labelled 2 in the tool's labels,
    # else (no ground at all) every non-tree point
    cls = np.asarray(las.classification)
    if (cls == 2).sum() >= 20:
        ground = xyz[cls == 2]
    elif (lab == 2).sum() >= 20:
        ground = xyz[lab == 2]
    else:
        ground = xyz[lab < 100]
    if len(ground) == 0:
        return []
    kd = cKDTree(ground[:, :2])
    k = min(20, len(ground))
    out = []
    for t in trees:
        p = xyz[lab == t]
        top = p[np.argmax(p[:, 2])]
        _, idx = kd.query(top[:2], k=k)
        out.append(float(top[2] - np.median(ground[np.atleast_1d(idx), 2])) * scale)
    return sorted(out)


def file_stats(path, units_hint: str | None = None) -> dict:
    """Tree count, point count and tree heights of a labelled file.

    Units come from the file's coordinate system or the tool's export tag; otherwise
    from `units_hint` (what the registry recorded at save time); otherwise metres,
    switched to US feet if that would make trees implausibly tall."""
    las = laspy.read(str(path))
    lab = _labels(las)
    u = detect_units(str(path))
    code, how = u["code"], "file"
    if u["source"] not in ("crs", "export"):
        code, how = (units_hint, "registry") if units_hint in UNITS else ("m", "guess")
    hs = tree_heights(las, UNITS[code]["scale"])
    if how == "guess" and hs and hs[-1] > MAX_PLAUSIBLE_TREE_M:
        code = "ftUS"
        hs = [h * UNITS["ftUS"]["scale"] for h in hs]
    # Patch centre (bounding-box centre) in WGS84, from the file's own coordinate system
    centre = {"lat": None, "lon": None}
    try:
        from services.location import tile_location
        loc = tile_location(path)
        if loc:
            centre = {"lat": loc["lat"], "lon": loc["lon"]}
    except Exception:
        pass
    return {
        **centre,
        "trees": int(np.unique(lab[lab >= 100]).size),
        "points": int(len(las.points)),
        "tree_heights": [round(h, 2) for h in hs],
        "height_units": code if how != "guess" else f"{code} (guessed)",
        "heights_v": HEIGHTS_VERSION,
    }

"""
Per-tree metrics after instance segmentation.

All lengths in metres, areas in m², volumes in m³, whatever the file's units.

What is measured, and why this way
----------------------------------
position      Crown centre (centroid of the crown outline) and tree top, in the file's own
              coordinates and, when the file has a coordinate system, as WGS84 latitude /
              longitude. Use lat/lon to join trees to neighbourhoods, census blocks etc.
height        Highest point of the tree minus the ground under it. Ground = median Z of the
              20 nearest ground points (class 2) around the tree top: the same rule as the
              Dataset overview (services/tree_heights.py), so the tool has one definition
              of tree height. `height_p95` is the 95th percentile of the tree's points, a
              check against a single stray high point.
crown_area    Area of the convex outline of the tree's points seen from above.
              (The previous version counted occupied grid cells: the result changed by a
              factor of two with the cell-size slider.)
crown_diameter  Diameter of a circle with that area.
crown_volume  Volume of the 3D convex hull of the tree's points.
height_p10 / height_p50
              Height percentiles of the tree's points. p10 was called "crown base height"
              before; it is not a crown base (the laser sees mostly the top of the crown),
              so it is now named for what it is.
point_count, point_density
              Points in the tree and points per m² of crown.
quality       "ok", or the reasons a tree's numbers deserve less trust (see QUALITY_NOTES).

How much to trust the numbers (measured on 418 hand-labelled trees, 2026-11-13, by thinning
each tree to 4 points/m² and comparing with the full-density result):
    height        -0.10 m
    crown_area    x 0.91
    crown_volume  x 0.83
Height is solid at any density. Area and volume shrink as the cloud gets sparser, so only
compare them between clouds of similar density, or thin all clouds to one density first.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

GROUND_NEIGHBOURS = 20      # ground points used for the ground level under a tree
GROUND_FAR_M = 15.0         # ground points further than this from the tree top: flagged
EDGE_MARGIN_M = 1.0         # crown closer than this to the patch edge: flagged
FEW_POINTS = 30
SPARSE_DENSITY = 2.0        # points per m² of crown

QUALITY_NOTES = {
    "edge":        "crown reaches the edge of the patch: area and volume are cut off",
    "few_points":  f"fewer than {FEW_POINTS} points: area and volume are rough",
    "sparse":      f"under {SPARSE_DENSITY:g} points per m²: area and volume are understated",
    "ground_far":  f"nearest ground points are more than {GROUND_FAR_M:g} m away: height is less certain",
    "no_ground":   "no ground points in the patch: height is measured from the coarse ground grid or the lowest point",
    "flat_shape":  "points lie on a line or plane: no area or volume",
}

CSV_COLUMNS = [
    "tree_id", "lat", "lon", "top_lat", "top_lon", "x", "y", "top_x", "top_y",
    "height_m", "height_p95_m", "height_p50_m", "height_p10_m",
    "crown_area_m2", "crown_diameter_m", "crown_volume_m3",
    "ground_elevation_m", "point_count", "point_density_per_m2", "quality",
]


def _polygon_centroid(pts: np.ndarray) -> tuple[float, float]:
    """Centroid of a convex polygon given its vertices in order."""
    x, y = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    a = cross.sum() / 2.0
    if abs(a) < 1e-12:
        return float(x.mean()), float(y.mean())
    return float(((x + x1) * cross).sum() / (6 * a)), float(((y + y1) * cross).sum() / (6 * a))


def _to_lonlat(crs, xs, ys):
    """File coordinates -> WGS84 lon/lat arrays, or (None, None) without a usable CRS."""
    if crs is None or len(xs) == 0:
        return None, None
    try:
        from pyproj import CRS, Transformer
        if crs.is_compound:      # horizontal + vertical: use the horizontal part
            crs = next((c for c in crs.sub_crs_list if c.is_projected or c.is_geographic), crs)
        lon, lat = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True).transform(
            np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64))
        lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
        if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
            return None, None
        return lon, lat
    except Exception:
        return None, None


def compute_tree_metrics(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    labels: np.ndarray,         # int32 (N,) — 0=non-tree, 201+=instances
    original_cls: np.ndarray,   # int32 (N,) — ASPRS class, 2=ground
    cell_size: float = 1.5,     # unused (kept so old callers still work)
    dtm_grid=None,              # coarse ground grid from the point-cloud view: fallback only
    dtm_rows: int = 64,
    dtm_cols: int = 64,
    dtm_x_min: float = 0.0,
    dtm_y_min: float = 0.0,
    dtm_x_range: float = 1.0,
    dtm_y_range: float = 1.0,
    unit_scale: float = 1.0,    # metres per data unit
    crs=None,                   # pyproj CRS of the file, for lat/lon; None = no lat/lon
) -> list[dict]:
    """Return one dict per tree (label >= 201), sorted by tree ID."""
    us = float(unit_scale) if unit_scale and unit_scale > 0 else 1.0
    x = np.asarray(x, dtype=np.float64)   # float32 loses ~0.5 m at state-plane/UTM coordinates
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int32)
    original_cls = np.asarray(original_cls)

    tree_ids = np.unique(labels)
    tree_ids = tree_ids[tree_ids >= 201]
    if tree_ids.size == 0:
        return []

    px_min, px_max = float(x.min()), float(x.max())
    py_min, py_max = float(y.min()), float(y.max())
    edge = EDGE_MARGIN_M / us

    # ── Ground ────────────────────────────────────────────────────────────────
    gnd = original_cls == 2
    kd = None
    if int(gnd.sum()) >= GROUND_NEIGHBOURS:
        gx, gy, gz = x[gnd], y[gnd], z[gnd]
        kd = cKDTree(np.c_[gx, gy])
    grid = None
    if dtm_grid is not None:
        grid = np.asarray(dtm_grid, dtype=np.float64).reshape(dtm_rows, dtm_cols)

    def ground_under(tx: float, ty: float) -> tuple[float, str, bool]:
        """(ground Z, source, far?) under one XY position."""
        if kd is not None:
            d, idx = kd.query([tx, ty], k=GROUND_NEIGHBOURS)
            return float(np.median(gz[np.atleast_1d(idx)])), "ground_points", bool(np.median(d) * us > GROUND_FAR_M)
        if grid is not None:
            cx = int(np.clip((tx - dtm_x_min) / dtm_x_range * dtm_cols, 0, dtm_cols - 1))
            cy = int(np.clip((ty - dtm_y_min) / dtm_y_range * dtm_rows, 0, dtm_rows - 1))
            return float(grid[cy, cx]), "grid", False
        return float(z.min()), "lowest_point", False

    rows = []
    for tid in tree_ids:
        mask = labels == tid
        tx, ty, tz = x[mask], y[mask], z[mask]
        n = int(mask.sum())
        flags = []

        i_top = int(np.argmax(tz))
        top_x, top_y = float(tx[i_top]), float(ty[i_top])
        g, g_src, g_far = ground_under(top_x, top_y)
        if g_src != "ground_points":
            flags.append("no_ground")
        elif g_far:
            flags.append("ground_far")
        h = np.maximum(tz - g, 0.0) * us                      # metres above ground

        # Crown outline (convex hull seen from above), in metres relative to the tree top
        xy_m = np.c_[(tx - top_x) * us, (ty - top_y) * us]
        area = volume = 0.0
        cen_x, cen_y = float(tx.mean()), float(ty.mean())
        try:
            hull2 = ConvexHull(xy_m)
            area = float(hull2.volume)                        # 2D hull: .volume is the area
            cx_m, cy_m = _polygon_centroid(xy_m[hull2.vertices])
            cen_x, cen_y = top_x + cx_m / us, top_y + cy_m / us
        except Exception:
            flags.append("flat_shape")
        if area > 0:
            try:
                volume = float(ConvexHull(np.c_[xy_m, h]).volume)
            except Exception:
                if "flat_shape" not in flags:
                    flags.append("flat_shape")

        density = n / area if area > 0 else 0.0
        if n < FEW_POINTS:
            flags.append("few_points")
        elif area > 0 and density < SPARSE_DENSITY:
            flags.append("sparse")
        if (tx.min() - px_min < edge or px_max - tx.max() < edge or
                ty.min() - py_min < edge or py_max - ty.max() < edge):
            flags.append("edge")

        rows.append({
            "id": int(tid),
            "x": cen_x, "y": cen_y, "top_x": top_x, "top_y": top_y,
            "height": round(float(h.max()), 2),
            "height_p95": round(float(np.percentile(h, 95)), 2),
            "height_p50": round(float(np.percentile(h, 50)), 2),
            "height_p10": round(float(np.percentile(h, 10)), 2),
            "crown_area": round(area, 1),
            "crown_diameter": round(2.0 * math.sqrt(area / math.pi), 2) if area > 0 else 0.0,
            "crown_volume": round(volume, 1),
            "ground_elevation": round(g * us, 2),
            "ground_source": g_src,
            "point_count": n,
            "point_density": round(density, 1),
            "quality": ";".join(flags) if flags else "ok",
        })

    # ── Latitude / longitude ──────────────────────────────────────────────────
    lon, lat = _to_lonlat(crs, [r["x"] for r in rows], [r["y"] for r in rows])
    tlon, tlat = _to_lonlat(crs, [r["top_x"] for r in rows], [r["top_y"] for r in rows])
    for i, r in enumerate(rows):
        r["lat"] = round(float(lat[i]), 7) if lat is not None else None
        r["lon"] = round(float(lon[i]), 7) if lon is not None else None
        r["top_lat"] = round(float(tlat[i]), 7) if tlat is not None else None
        r["top_lon"] = round(float(tlon[i]), 7) if tlon is not None else None
        for k in ("x", "y", "top_x", "top_y"):
            r[k] = round(r[k], 3)

    return sorted(rows, key=lambda m: m["id"])


def metrics_to_csv(trees: list[dict], extra: dict | None = None) -> str:
    """CSV text for a list of metric dicts. `extra` adds constant columns in front
    (e.g. {"patch": ..., "crs": ...}) so files from many patches can be stacked."""
    import csv
    import io
    extra = extra or {}
    key = {"tree_id": "id", "height_m": "height", "height_p95_m": "height_p95",
           "height_p50_m": "height_p50", "height_p10_m": "height_p10",
           "crown_area_m2": "crown_area", "crown_diameter_m": "crown_diameter",
           "crown_volume_m3": "crown_volume", "ground_elevation_m": "ground_elevation",
           "point_density_per_m2": "point_density"}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(extra) + CSV_COLUMNS)
    for t in trees:
        w.writerow(list(extra.values()) +
                   ["" if t.get(key.get(c, c)) is None else t.get(key.get(c, c)) for c in CSV_COLUMNS])
    return buf.getvalue()

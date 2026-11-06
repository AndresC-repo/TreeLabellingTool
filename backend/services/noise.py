"""Removing obvious noise points when a patch is cut.

A point is noise if
  * it is classified as noise in the file (ASPRS 7 = low noise, 18 = high noise), or
  * it lies far outside the tile's normal height range AND is isolated.

"Far outside" = more than max(10 m, half the normal height range) above the 99.5th
percentile or below the 0.5th percentile of the tile's heights (noise classes excluded).
"Isolated" = fewer than 5 other such points within 5 m. Tall trees and building roofs
above the normal range are dense clusters, so they are kept; single spikes (birds,
sensor noise, multipath) are not.
"""
from __future__ import annotations
import numpy as np

NOISE_CLASSES = (7, 18)
MIN_MARGIN_M = 10.0
NEIGHBOUR_RADIUS_M = 5.0
MIN_NEIGHBOURS = 5


def noise_mask(x, y, z, classification, z_lo: float, z_hi: float, metres_per_unit: float = 1.0):
    """Return (mask of points to remove, {"classified": n, "outliers": n})."""
    upm = 1.0 / max(metres_per_unit, 1e-9)          # data units per metre
    cls = np.asarray(classification)
    by_class = np.isin(cls, NOISE_CLASSES)

    z = np.asarray(z, dtype=np.float64)
    margin = max(MIN_MARGIN_M * upm, 0.5 * (z_hi - z_lo))
    cand = ~by_class & ((z > z_hi + margin) | (z < z_lo - margin))
    outliers = np.zeros(len(z), dtype=bool)
    idx = np.flatnonzero(cand)
    if len(idx):
        from scipy.spatial import cKDTree
        pts = np.column_stack([np.asarray(x, np.float64)[idx], np.asarray(y, np.float64)[idx], z[idx]])
        n_near = cKDTree(pts).query_ball_point(pts, r=NEIGHBOUR_RADIUS_M * upm, return_length=True) - 1
        outliers[idx[n_near < MIN_NEIGHBOURS]] = True
    return by_class | outliers, {"classified": int(by_class.sum()), "outliers": int(outliers.sum())}

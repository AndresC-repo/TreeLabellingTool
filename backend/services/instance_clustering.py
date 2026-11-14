# ─────────────────────────────────────────────────────────────────────────────
# VERBATIM COPY of urban-tree-detection/src/instances/clustering.py (commit 23f4c58).
# Do not edit here — change it in the training repo and copy it again, so the tool
# groups trees exactly like the evaluation did.
# ─────────────────────────────────────────────────────────────────────────────
"""
Turn per-point offsets (and optionally embeddings) into tree instances.

Method (numpy + scipy only, so the labelling tool can import this file as it is):

  1. Every tree point votes for its tree centre: position + predicted XY offset.
  2. Votes are accumulated on a 2D grid. Each point's vote is weighted by the ground area it
     represents (1 / points in its 0.5 m cell), so the vote mass of a tree is its crown area in
     m², whatever the point density (2 pts/m² or 40 pts/m² give the same picture).
  3. The grid is smoothed and its local maxima are the tree centres
     (at least `min_peak_distance` apart).
  4. Each point goes to the nearest centre, measured from where its vote landed.
  5. Optional: embeddings refine the assignment between neighbouring centres.
  6. Centres whose crown is smaller than `min_crown_area` m² or `min_points` points are dropped,
     smallest first, and their points handed to the nearest remaining centre if one is close.

Compared with DBSCAN / mean-shift on the shifted points: no bandwidth that depends on point
density, deterministic, linear in the number of points, and the thresholds are in metres and m².
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

DEFAULT_PARAMS = dict(
    cell=0.25,               # vote grid resolution (m)
    sigma=0.75,              # Gaussian smoothing of the vote grid (m)
    min_peak_distance=3.0,   # two tree centres are never closer than this (m)
    min_crown_area=2.0,      # drop trees whose crown covers less than this (m²)
    min_points=10,           # ... or with fewer points than this
    embed_weight=0.0,        # 0 = offsets only; > 0 adds the embedding distance (see below)
    embed_scale=1.5,         # embedding distance that counts like `spatial_scale` metres
    spatial_scale=1.5,       # (m)
    refine_iters=1,          # times the centres are moved to the mean of their votes
    reassign_dist=6.0,       # points of a dropped tree join another centre only within this (m)
    area_cell=0.5,           # cell size used for the crown-area weights (m)
)


def _area_weights(xy: np.ndarray, area_cell: float) -> np.ndarray:
    """Ground area represented by each point (m²): cell area / points in the cell."""
    ij = np.floor((xy - xy.min(axis=0)) / area_cell).astype(np.int64)
    key = ij[:, 0] * (int(ij[:, 1].max()) + 1) + ij[:, 1]
    _, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    return (area_cell * area_cell) / counts[inv]


def _find_peaks(votes: np.ndarray, w: np.ndarray, cell: float, sigma: float,
                min_peak_distance: float, min_crown_area: float) -> np.ndarray:
    """Local maxima of the smoothed vote grid. Returns (K, 2) centres in metres."""
    lo = votes.min(axis=0) - 3 * sigma
    hi = votes.max(axis=0) + 3 * sigma
    shape = np.maximum(np.ceil((hi - lo) / cell).astype(np.int64) + 1, 1)
    ij = np.minimum(np.floor((votes - lo) / cell).astype(np.int64), shape - 1)
    grid = np.bincount(ij[:, 0] * shape[1] + ij[:, 1], weights=w,
                       minlength=int(shape[0] * shape[1])).reshape(shape).astype(np.float32)

    s = sigma / cell
    smooth = ndimage.gaussian_filter(grid, s, mode='constant')

    r = max(int(round(min_peak_distance / cell)), 1)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    footprint = (yy * yy + xx * xx) <= r * r
    local_max = ndimage.maximum_filter(smooth, footprint=footprint, mode='constant')
    # A tree of the minimum area, perfectly concentrated, peaks at area / (2*pi*s^2).
    # Accept much weaker peaks here; the crown-area test afterwards is the real filter.
    floor = 0.1 * min_crown_area / (2 * np.pi * s * s)
    peak_mask = (smooth == local_max) & (smooth > floor)
    if not peak_mask.any():
        return np.empty((0, 2), dtype=np.float64)
    lbl, n = ndimage.label(peak_mask)            # merge plateau pixels into one peak
    com = np.array(ndimage.center_of_mass(smooth, lbl, np.arange(1, n + 1))).reshape(-1, 2)
    return lo + (com + 0.5) * cell


def cluster_trees(xy: np.ndarray, offsets_xy: np.ndarray, embeddings: np.ndarray | None = None,
                  return_info: bool = False, **params):
    """Group tree points into individual trees.

    Args:
        xy:          (N, 2) positions of the tree points (metres)
        offsets_xy:  (N, 2) predicted offsets towards the tree centre (metres)
        embeddings:  (N, E) optional; used only if embed_weight > 0
        params:      overrides for DEFAULT_PARAMS
    Returns:
        labels (N,) int32: 1..K per tree, 0 = not assigned to any tree
        info dict (if return_info): 'centers' (K, 2), 'area' (K,), 'n_points' (K,)
    """
    p = dict(DEFAULT_PARAMS)
    unknown = set(params) - set(p)
    if unknown:
        raise TypeError(f"unknown clustering parameter(s): {sorted(unknown)}")
    p.update(params)

    n = len(xy)
    labels = np.zeros(n, dtype=np.int32)
    empty_info = {'centers': np.empty((0, 2)), 'area': np.empty(0), 'n_points': np.empty(0, dtype=int)}
    if n == 0:
        return (labels, empty_info) if return_info else labels

    xy = np.asarray(xy, dtype=np.float64)[:, :2]
    votes = xy + np.asarray(offsets_xy, dtype=np.float64)[:, :2]
    w = _area_weights(xy, p['area_cell'])

    centers = _find_peaks(votes, w, p['cell'], p['sigma'], p['min_peak_distance'], p['min_crown_area'])
    if len(centers) == 0:
        return (labels, empty_info) if return_info else labels

    assign = cKDTree(centers).query(votes)[1]

    # Move each centre to the weighted mean of its votes, then reassign
    for _ in range(int(p['refine_iters'])):
        mass = np.bincount(assign, weights=w, minlength=len(centers))
        keep = mass > 0
        cx = np.bincount(assign, weights=w * votes[:, 0], minlength=len(centers))
        cy = np.bincount(assign, weights=w * votes[:, 1], minlength=len(centers))
        centers = np.stack([cx[keep] / mass[keep], cy[keep] / mass[keep]], axis=1)
        assign = cKDTree(centers).query(votes)[1]

    # Embedding refinement between the nearest few centres
    if embeddings is not None and p['embed_weight'] > 0 and len(centers) > 1:
        emb = np.asarray(embeddings, dtype=np.float64)
        k = min(3, len(centers))
        d, cand = cKDTree(centers).query(votes, k=k)                    # (N, k)
        for _ in range(2):
            K = len(centers)
            mass = np.maximum(np.bincount(assign, weights=w, minlength=K), 1e-9)
            mean_emb = np.stack([np.bincount(assign, weights=w * emb[:, j], minlength=K) / mass
                                 for j in range(emb.shape[1])], axis=1)   # (K, E)
            occupied = np.bincount(assign, minlength=K) > 0
            d_emb = np.linalg.norm(emb[:, None, :] - mean_emb[cand], axis=2)   # (N, k)
            cost = (d / p['spatial_scale']) ** 2 + p['embed_weight'] * (d_emb / p['embed_scale']) ** 2
            cost[~occupied[cand]] = np.inf
            assign = cand[np.arange(n), cost.argmin(axis=1)]

    # Drop trees that are too small, smallest first
    alive = np.ones(len(centers), dtype=bool)
    assign = assign.astype(np.int64)
    while True:
        area = np.bincount(assign[assign >= 0], weights=w[assign >= 0], minlength=len(centers))
        count = np.bincount(assign[assign >= 0], minlength=len(centers))
        bad = alive & ((area < p['min_crown_area']) | (count < p['min_points']))
        if not bad.any():
            break
        worst = np.flatnonzero(bad)[np.argmin(area[bad])]
        alive[worst] = False
        pts = np.flatnonzero(assign == worst)
        if len(pts) and alive.any():
            alive_idx = np.flatnonzero(alive)
            d, j = cKDTree(centers[alive_idx]).query(votes[pts])
            assign[pts] = np.where(d <= p['reassign_dist'], alive_idx[j], -1)
        else:
            assign[pts] = -1

    alive_idx = np.flatnonzero(alive)
    remap = np.full(len(centers), 0, dtype=np.int32)
    remap[alive_idx] = np.arange(1, len(alive_idx) + 1, dtype=np.int32)
    ok = assign >= 0
    labels[ok] = remap[assign[ok]]

    if return_info:
        K = len(alive_idx)
        info = {'centers': centers[alive_idx],
                'area': np.bincount(labels[labels > 0] - 1, weights=w[labels > 0], minlength=K),
                'n_points': np.bincount(labels[labels > 0] - 1, minlength=K)}
        return labels, info
    return labels

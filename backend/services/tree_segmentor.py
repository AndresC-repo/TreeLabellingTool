"""
CHM-based tree instance segmentation.

Algorithm:
  1. Build DTM (min Z per cell) from ground points (ASPRS class 2).
  2. Build DSM (max Z per cell) from tree points (label == 101).
  3. CHM = max(0, DSM - DTM), Gaussian smoothed.
  4. Local maxima in CHM → tree-top seeds.
  5. Each tree point assigned to its nearest seed via cKDTree.
  6. Instance IDs start at 201 (201, 202, ...).
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.spatial import cKDTree


def segment_tree_instances(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    labels: np.ndarray,          # int32 (N,)  0=non-tree, 101=tree
    original_cls: np.ndarray,    # int32 (N,)  ASPRS classification, 2=ground
    cell_size: float = 0.5,      # CHM grid resolution in metres
    smooth_sigma: float = 3.0,   # Gaussian sigma (cells); 3 cells × 0.5 m = 1.5 m
    min_height: float = 3.0,     # minimum CHM height to count as a tree top (m)
    min_distance: int = 10,      # neighbourhood size for maximum_filter (cells); 10 × 0.5 m = 5 m
    max_radius: float = 15.0,    # max XY distance from seed to assign a point (m)
) -> tuple[np.ndarray, int]:
    """
    Returns
    -------
    new_labels : int32 (N,)  — 0 = non-tree, 201+ = individual tree instances
    tree_count : int          — number of distinct instances found
    """
    new_labels  = labels.copy().astype(np.int32)
    tree_mask   = labels == 101
    ground_mask = original_cls == 2

    if not np.any(tree_mask):
        return new_labels, 0

    # ── Grid setup ────────────────────────────────────────────────────────────
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    cols = max(int(np.ceil((x_max - x_min) / cell_size)) + 1, 1)
    rows = max(int(np.ceil((y_max - y_min) / cell_size)) + 1, 1)

    def _rc(px: np.ndarray, py: np.ndarray):
        """Convert world XY → (row, col) grid indices, clipped to grid bounds."""
        c = np.clip(((px - x_min) / cell_size).astype(np.int32), 0, cols - 1)
        r = np.clip(((py - y_min) / cell_size).astype(np.int32), 0, rows - 1)
        return r, c

    # ── DTM — min Z per cell from ground points ───────────────────────────────
    flat = rows * cols
    dtm = np.full(flat, np.inf, dtype=np.float32)
    if np.any(ground_mask):
        gr, gc = _rc(x[ground_mask], y[ground_mask])
        np.minimum.at(dtm, gr * cols + gc, z[ground_mask].astype(np.float32))
        fallback = float(z[ground_mask].min())
    else:
        fallback = float(z.min())   # flat-ground fallback when no ASPRS class 2
    dtm[dtm == np.inf] = fallback
    dtm = dtm.reshape(rows, cols)

    # ── DSM — max Z per cell from tree points ─────────────────────────────────
    dsm = np.full(flat, -np.inf, dtype=np.float32)
    tr, tc = _rc(x[tree_mask], y[tree_mask])
    np.maximum.at(dsm, tr * cols + tc, z[tree_mask].astype(np.float32))
    dsm[dsm == -np.inf] = 0.0    # empty cells → height 0
    dsm = dsm.reshape(rows, cols)

    # ── CHM — smooth ──────────────────────────────────────────────────────────
    chm = np.maximum(0.0, dsm - dtm).astype(np.float32)
    chm_smooth = gaussian_filter(chm, sigma=smooth_sigma)

    # ── Local maxima ──────────────────────────────────────────────────────────
    chm_max   = maximum_filter(chm_smooth, size=max(1, min_distance))
    peak_r, peak_c = np.where(
        (chm_smooth == chm_max) & (chm_smooth >= min_height)
    )

    # Convert peak grid coords → world XY (cell centre)
    peak_x = x_min + peak_c * cell_size + cell_size / 2
    peak_y = y_min + peak_r * cell_size + cell_size / 2

    print(f"[tree_segmentor] CHM grid {rows}×{cols}, "
          f"{np.any(ground_mask).sum() if np.any(ground_mask) else 0} ground pts, "
          f"{int(tree_mask.sum()):,} tree pts, "
          f"{len(peak_x)} peaks found (min_height={min_height}m)")

    # ── Edge case: no peaks ───────────────────────────────────────────────────
    if len(peak_x) == 0:
        new_labels[tree_mask] = 201
        return new_labels, 1

    # ── Nearest-peak assignment ───────────────────────────────────────────────
    kd     = cKDTree(np.column_stack([peak_x, peak_y]))
    dists, nearest = kd.query(
        np.column_stack([x[tree_mask], y[tree_mask]]), k=1
    )
    # Points within max_radius get a unique instance ID; beyond → ungrouped (201)
    instance_ids = np.where(
        dists <= max_radius, 201 + nearest.astype(np.int32), 201
    ).astype(np.int32)
    new_labels[tree_mask] = instance_ids

    tree_count = int(np.unique(instance_ids).size)
    print(f"[tree_segmentor] {tree_count} tree instances assigned.")
    return new_labels, tree_count

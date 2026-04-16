"""
CHM-based tree instance segmentation.

Algorithm:
  1. Build DTM (min Z per cell) from ground points (ASPRS class 2).
  2. Build DSM (max Z per cell) from tree points (label == 101).
  3. CHM = max(0, DSM - DTM), Gaussian smoothed.
  4. Local maxima in CHM → tree-top seeds.
  5. Each tree point assigned to its nearest seed via cKDTree.
  6. Post-process: merge instances with fewer than min_tree_points into
     the nearest valid (large enough) peak.
  7. Instance IDs start at 201 (201, 202, ...).
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
    smooth_sigma: float = 3.0,   # Gaussian sigma (cells); 3 × 0.5 m = 1.5 m
    min_height: float = 3.0,     # minimum CHM height to count as a tree top (m)
    min_distance: int = 10,      # neighbourhood size for maximum_filter (cells); 10 × 0.5 m = 5 m
    max_radius: float = 15.0,    # max XY distance from seed to assign a point (m)
    min_tree_points: int = 500,  # merge instances smaller than this into nearest valid peak
) -> tuple[np.ndarray, int]:
    """
    Returns
    -------
    new_labels : int32 (N,)  — 0 = non-tree, 201+ = individual tree instances
    tree_count : int          — number of distinct instances found
    peaks      : float32 (K, 3)  — [x, y, z] of each valid tree-top (world coords)
    """
    new_labels  = labels.copy().astype(np.int32)
    tree_mask   = labels == 101
    ground_mask = original_cls == 2

    if not np.any(tree_mask):
        return new_labels, 0, np.empty((0, 3), dtype=np.float32)

    # ── Grid setup ────────────────────────────────────────────────────────────
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    cols = max(int(np.ceil((x_max - x_min) / cell_size)) + 1, 1)
    rows = max(int(np.ceil((y_max - y_min) / cell_size)) + 1, 1)

    def _rc(px: np.ndarray, py: np.ndarray):
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
        fallback = float(z.min())
    dtm[dtm == np.inf] = fallback
    dtm = dtm.reshape(rows, cols)

    # ── DSM — max Z per cell from tree points ─────────────────────────────────
    dsm = np.full(flat, -np.inf, dtype=np.float32)
    tr, tc = _rc(x[tree_mask], y[tree_mask])
    np.maximum.at(dsm, tr * cols + tc, z[tree_mask].astype(np.float32))
    dsm[dsm == -np.inf] = 0.0
    dsm = dsm.reshape(rows, cols)

    # ── CHM — smooth ──────────────────────────────────────────────────────────
    chm = np.maximum(0.0, dsm - dtm).astype(np.float32)
    chm_smooth = gaussian_filter(chm, sigma=smooth_sigma)

    # ── Local maxima ──────────────────────────────────────────────────────────
    chm_max = maximum_filter(chm_smooth, size=max(1, min_distance))
    peak_r, peak_c = np.where(
        (chm_smooth == chm_max) & (chm_smooth >= min_height)
    )

    peak_x = x_min + peak_c * cell_size + cell_size / 2
    peak_y = y_min + peak_r * cell_size + cell_size / 2

    n_tree = int(tree_mask.sum())
    print(f"[tree_segmentor] grid {rows}×{cols}, {n_tree:,} tree pts, "
          f"{len(peak_x)} initial peaks (min_height={min_height}m, "
          f"min_distance={min_distance} cells, smooth={smooth_sigma})")

    # DSM Z at each peak cell = absolute tree-top height
    peak_z = dsm[peak_r, peak_c]

    # ── Edge case: no peaks ───────────────────────────────────────────────────
    if len(peak_x) == 0:
        new_labels[tree_mask] = 201
        return new_labels, 1, np.empty((0, 3), dtype=np.float32)

    # ── Initial nearest-peak assignment ──────────────────────────────────────
    peak_xy = np.column_stack([peak_x, peak_y])
    tree_xy = np.column_stack([x[tree_mask], y[tree_mask]])

    kd = cKDTree(peak_xy)
    dists, nearest = kd.query(tree_xy, k=1)
    instance_ids = np.where(
        dists <= max_radius, 201 + nearest.astype(np.int32), 201
    ).astype(np.int32)

    # ── Post-process: merge small instances into nearest valid peak ───────────
    valid_peak_idx = np.arange(len(peak_x))   # all peaks initially valid

    if min_tree_points > 0 and len(peak_x) > 1:
        unique_inst, inst_counts = np.unique(instance_ids, return_counts=True)
        valid_instances = unique_inst[inst_counts >= min_tree_points]

        if len(valid_instances) == 0:
            # Nothing meets the threshold — collapse to single instance
            new_labels[tree_mask] = 201
            best_z = float(dsm[peak_r, peak_c].max())
            best_r, best_c = peak_r[0], peak_c[0]
            peaks_out = np.array([[
                x_min + best_c * cell_size + cell_size / 2,
                y_min + best_r * cell_size + cell_size / 2,
                best_z,
            ]], dtype=np.float32)
            return new_labels, 1, peaks_out

        if len(valid_instances) < len(unique_inst):
            valid_peak_idx = valid_instances - 201   # 0-based indices into peak arrays
            valid_peak_xy  = peak_xy[valid_peak_idx]

            kd2 = cKDTree(valid_peak_xy)
            _, nearest2 = kd2.query(tree_xy, k=1)
            instance_ids = (201 + valid_peak_idx[nearest2]).astype(np.int32)

    new_labels[tree_mask] = instance_ids

    # Build final peaks array (only valid peaks, with absolute Z)
    peaks_out = np.column_stack([
        peak_x[valid_peak_idx],
        peak_y[valid_peak_idx],
        peak_z[valid_peak_idx],
    ]).astype(np.float32)

    tree_count = int(np.unique(instance_ids).size)
    print(f"[tree_segmentor] {tree_count} tree instances after merging "
          f"(min_tree_points={min_tree_points}).")
    return new_labels, tree_count, peaks_out

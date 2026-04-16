"""
CHM-based tree crown delineation — Duncanson et al. (2014) algorithm.

Reference
---------
Duncanson, L.I., Cook, B.D., Hurtt, G.C., Dubayah, R.O. (2014).
An efficient, multi-layered crown delineation algorithm for mapping individual
tree structure across multiple ecosystems.
Remote Sensing of Environment, 154, 378–386.

Algorithm
---------
1.  Build per-point terrain height from an external DTM grid (preferred,
    derived from class-2 ground points in the point-cloud view) or from
    ASPRS class-2 points in the LAS file.
2.  For every tree point (label == 101) compute
      height_above_terrain = max(0, z − terrain_at(x, y))
3.  Rasterise to a CHM at `cell_size` resolution (max height per cell).
4.  Apply the Duncanson custom smoothing:
      a.  Classify each cell as canopy (CHM ≥ min_height) or ground.
      b.  Ground cells surrounded by ≥ 4 canopy neighbours are treated as
          within-crown gaps and replaced by the mean of their canopy
          neighbours.  (Fills LiDAR occlusion holes without blurring edges.)
      c.  Apply an N×N uniform (moving-average) filter over the gap-filled CHM.
      d.  Optional additional Gaussian smoothing (smooth_sigma > 0).
5.  Detect local maxima in the smoothed CHM using peak_local_max with a
    minimum inter-peak distance of `min_distance` cells and a height threshold
    of `min_height` metres.  These are the watershed seed markers.
6.  Run marker-based watershed on −CHM (inverted so peaks become basins)
    within the canopy mask (CHM ≥ min_height AND tree-point cells).
7.  For visualisation: report the actual CHM-peak position within each basin
    as the seed point (always on top of the tree, not at the smoothed peak).
8.  Post-process: merge basins with fewer than `min_tree_points` by re-running
    watershed with only the valid seeds as markers.
9.  Instance IDs start at 201 (201, 202, …).
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import uniform_filter, gaussian_filter, label as nd_label
from skimage.feature import peak_local_max
from skimage.segmentation import watershed


# ─────────────────────────────────────────────────────────────────────────────
def _duncanson_smooth(
    chm: np.ndarray,
    height_threshold: float = 2.0,
    window: int = 5,
    sigma: float = 0.0,
) -> np.ndarray:
    """
    Custom moving-window smoothing from Duncanson et al. (2014).

    Ground cells (CHM < height_threshold) that have ≥ 4 canopy neighbours in
    a 3×3 window are "within-crown gaps" and are replaced by the mean of
    their canopy neighbours before the N×N uniform smoothing is applied.
    This fills holes caused by LiDAR occlusion without blurring crown edges.
    """
    chm = chm.astype(np.float32)
    is_canopy = (chm >= height_threshold).astype(np.float32)

    # 3×3 neighbour statistics (exclude centre cell)
    nbr_canopy_sum = uniform_filter(is_canopy, size=3) * 9.0 - is_canopy
    nbr_val_sum    = uniform_filter(chm * is_canopy, size=3) * 9.0 - chm * is_canopy

    # Mean canopy value from neighbours (safe divide)
    canopy_mean = np.where(nbr_canopy_sum > 0, nbr_val_sum / nbr_canopy_sum, 0.0)

    # Within-crown gap: ground cell with ≥ 4 canopy neighbours
    within_crown_gap = (is_canopy < 0.5) & (nbr_canopy_sum >= 4.0)
    chm_filled = np.where(within_crown_gap, canopy_mean, chm)

    # N×N uniform (moving-average) smoothing
    smoothed = uniform_filter(chm_filled, size=window).astype(np.float32)

    # Optional additional Gaussian pass
    if sigma > 0:
        smoothed = gaussian_filter(smoothed, sigma=sigma).astype(np.float32)

    return smoothed


# ─────────────────────────────────────────────────────────────────────────────
def segment_tree_instances(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    labels: np.ndarray,            # int32 (N,)  0=non-tree, 101=tree
    original_cls: np.ndarray,      # int32 (N,)  ASPRS classification, 2=ground
    cell_size: float = 1.5,        # CHM grid resolution (m)
    smooth_window: int = 1,        # Duncanson uniform-filter window (cells)
    smooth_sigma: float = 0.0,     # additional Gaussian σ after window filter
    min_height: float = 2.5,       # min CHM (m) to be canopy
    min_distance: int = 10,        # min peak separation (cells) for seed detection
    min_tree_points: int = 500,    # merge basins smaller than this
    min_crown_cells: int = 70,     # remove isolated canopy blobs smaller than this (cells)
    # Unused legacy params (kept for API compatibility):
    max_radius: float = 15.0,
    # External DTM from the point-cloud view
    dtm_grid: np.ndarray | None = None,
    dtm_rows: int = 64,
    dtm_cols: int = 64,
    dtm_x_min: float = 0.0,
    dtm_y_min: float = 0.0,
    dtm_x_range: float = 1.0,
    dtm_y_range: float = 1.0,
) -> tuple[np.ndarray, int, np.ndarray, np.ndarray]:
    """
    Returns
    -------
    new_labels  : int32 (N,)     0 = non-tree, 201+ = individual instances
    tree_count  : int            number of valid instances
    peaks       : float32 (K,3) [x,y,z] of valid tree tops (after merge)
    seed_peaks  : float32 (M,3) [x,y,z] of ALL CHM local maxima (watershed seeds)
    """
    EMPTY = np.empty((0, 3), dtype=np.float32)
    new_labels = labels.copy().astype(np.int32)
    tree_mask  = labels == 101

    if not np.any(tree_mask):
        return new_labels, 0, EMPTY, EMPTY

    # ── CHM grid ──────────────────────────────────────────────────────────────
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    cols = max(int(np.ceil((x_max - x_min) / cell_size)) + 1, 1)
    rows = max(int(np.ceil((y_max - y_min) / cell_size)) + 1, 1)
    flat = rows * cols

    def _rc(px, py):
        c = np.clip(((px - x_min) / cell_size).astype(np.int32), 0, cols - 1)
        r = np.clip(((py - y_min) / cell_size).astype(np.int32), 0, rows - 1)
        return r, c

    # ── Per-point terrain height ──────────────────────────────────────────────
    if dtm_grid is not None:
        dtm_arr = np.array(dtm_grid, dtype=np.float32).reshape(dtm_rows, dtm_cols)
        cx = np.clip(((x - dtm_x_min) / dtm_x_range * dtm_cols).astype(np.int32),
                     0, dtm_cols - 1)
        cy = np.clip(((y - dtm_y_min) / dtm_y_range * dtm_rows).astype(np.int32),
                     0, dtm_rows - 1)
        terrain_z = dtm_arr[cy, cx]
        print(f"[tree_segmentor] external DTM ({dtm_rows}×{dtm_cols})")
    else:
        gnd = original_cls == 2
        dtm_flat = np.full(flat, np.inf, dtype=np.float32)
        if gnd.any():
            gr, gc = _rc(x[gnd], y[gnd])
            np.minimum.at(dtm_flat, gr * cols + gc, z[gnd].astype(np.float32))
            fallback = float(z[gnd].mean())
        else:
            fallback = float(z.min())
        dtm_flat[dtm_flat == np.inf] = fallback
        dtm_2d = dtm_flat.reshape(rows, cols)
        pr_all, pc_all = _rc(x, y)
        terrain_z = dtm_2d[pr_all, pc_all]
        print(f"[tree_segmentor] internal DTM (fallback={fallback:.1f}m)")

    # ── Rasterise CHM from tree points ────────────────────────────────────────
    hat = np.maximum(0.0, z - terrain_z).astype(np.float32)   # height above terrain
    tr, tc = _rc(x[tree_mask], y[tree_mask])

    chm_flat = np.full(flat, -np.inf, dtype=np.float32)
    np.maximum.at(chm_flat, tr * cols + tc, hat[tree_mask])
    chm_flat[chm_flat == -np.inf] = 0.0
    chm = chm_flat.reshape(rows, cols)

    # ── Duncanson smoothing (paper §2.4) ─────────────────────────────────────
    chm_smooth = _duncanson_smooth(
        chm,
        height_threshold=min_height,
        window=max(1, smooth_window),
        sigma=smooth_sigma,
    )

    # ── Canopy mask: tree-point cells AND CHM ≥ min_height ───────────────────
    tree_grid = np.zeros(flat, dtype=bool)
    np.put(tree_grid, tr * cols + tc, True)
    tree_grid   = tree_grid.reshape(rows, cols)
    canopy_mask = tree_grid & (chm_smooth >= min_height)

    # ── Drop isolated canopy blobs (noise scatter from cut/partial trees) ───────
    # Connected components in the canopy mask: blobs with fewer cells than
    # min_crown_cells are spatially isolated and treated as noise — their points
    # get label 0 (non-tree) so they don't seed spurious watershed basins.
    if min_crown_cells > 0 and canopy_mask.any():
        comp_lbl, n_comp = nd_label(canopy_mask)
        comp_sizes = np.bincount(comp_lbl.ravel())   # index 0 = background
        remove_ids = np.where((comp_sizes < min_crown_cells) & (np.arange(len(comp_sizes)) > 0))[0]
        if remove_ids.size:
            noise_cells = np.isin(comp_lbl, remove_ids)
            canopy_mask[noise_cells] = False
            # Also clear tree_grid so those points fall outside canopy mask
            tree_grid[noise_cells] = False
            removed_pts = noise_cells[tr, tc]          # which tree points are in removed blobs
            new_labels[np.where(tree_mask)[0][removed_pts]] = 0   # label as non-tree
            tree_mask_arr = np.where(tree_mask)[0]
            keep = ~removed_pts
            tr, tc = tr[keep], tc[keep]
            tree_mask = np.zeros(len(labels), dtype=bool)
            tree_mask[tree_mask_arr[keep]] = True
            print(f"[tree_segmentor] removed {remove_ids.size} isolated blob(s) "
                  f"({removed_pts.sum():,} pts → label 0)")

    n_tree = int(tree_mask.sum())
    print(f"[tree_segmentor] grid {rows}×{cols}, {n_tree:,} tree pts, "
          f"smooth_window={smooth_window}, min_height={min_height}m, "
          f"min_distance={min_distance}")

    if not canopy_mask.any():
        print("[tree_segmentor] no canopy cells above min_height — returning single instance")
        new_labels[tree_mask] = 201
        return new_labels, 1, EMPTY, EMPTY

    # ── Local maxima detection (peak_local_max, paper §2.4 step 3) ───────────
    # peak_local_max returns an (N,2) coordinate array in skimage >= 0.19.
    # Convert to a boolean mask so nd_label / watershed can use it.
    peak_coords = peak_local_max(
        chm_smooth,
        min_distance=max(1, min_distance),
        threshold_abs=min_height,
        labels=canopy_mask,    # only search within canopy mask
        exclude_border=False,
    )
    peaks_mask = np.zeros(chm_smooth.shape, dtype=bool)
    if len(peak_coords):
        peaks_mask[peak_coords[:, 0], peak_coords[:, 1]] = True

    # Label each peak as a separate marker (some may be adjacent → nd_label)
    peak_markers, n_peaks = nd_label(peaks_mask)

    print(f"[tree_segmentor] {n_peaks} seed peaks detected")

    if n_peaks == 0:
        new_labels[tree_mask] = 201
        return new_labels, 1, EMPTY, EMPTY

    # ── Seeded watershed on inverted CHM ─────────────────────────────────────
    ws = watershed(-chm_smooth, markers=peak_markers, mask=canopy_mask)

    # ── Seed peaks for visualisation: actual CHM max WITHIN each basin ───────
    # (Not the smoothed-peak position — the real tree top in the point cloud.)
    basin_ids = np.unique(ws)
    basin_ids = basin_ids[basin_ids > 0]

    # Vectorised argmax per basin
    flat_ws  = ws.ravel()
    flat_chm = chm_smooth.ravel()
    flat_raw = chm.ravel()          # unsmoothed CHM for actual tree-top height

    peak_flat_idx = np.zeros(n_peaks + 1, dtype=np.int64)
    peak_val_buf  = np.full(n_peaks + 1, -np.inf, dtype=np.float32)
    valid_cells   = flat_ws > 0
    for i in np.where(valid_cells)[0]:
        bid = int(flat_ws[i])
        v   = float(flat_chm[i])
        if v > peak_val_buf[bid]:
            peak_val_buf[bid] = v
            peak_flat_idx[bid] = i

    seed_r = (peak_flat_idx[basin_ids] // cols).astype(np.int32)
    seed_c = (peak_flat_idx[basin_ids] % cols).astype(np.int32)
    seed_px = (x_min + seed_c * cell_size + cell_size / 2).astype(np.float32)
    seed_py = (y_min + seed_r * cell_size + cell_size / 2).astype(np.float32)

    # Absolute Z: terrain at seed + raw (unsmoothed) CHM at seed cell
    if dtm_grid is not None:
        scx = np.clip(((seed_px - dtm_x_min) / dtm_x_range * dtm_cols).astype(np.int32),
                      0, dtm_cols - 1)
        scy = np.clip(((seed_py - dtm_y_min) / dtm_y_range * dtm_rows).astype(np.int32),
                      0, dtm_rows - 1)
        seed_terrain = dtm_arr[scy, scx]
    else:
        srr, scc = _rc(seed_px, seed_py)
        seed_terrain = dtm_2d[srr, scc]

    seed_pz = (seed_terrain + flat_raw[peak_flat_idx[basin_ids]]).astype(np.float32)
    seed_peaks_out = np.column_stack([seed_px, seed_py, seed_pz]).astype(np.float32)

    # ── Map tree points to watershed basins ───────────────────────────────────
    point_basin  = ws[tr, tc]                              # 0 = unassigned
    instance_ids = np.where(
        point_basin > 0, 200 + point_basin, 201
    ).astype(np.int32)

    # ── Post-process: merge small basins ─────────────────────────────────────
    valid_peak_basin_ids = basin_ids      # 1-indexed, same order as seed_peaks_out

    if min_tree_points > 0 and n_peaks > 1:
        unique_inst, inst_counts = np.unique(instance_ids, return_counts=True)
        valid_inst = unique_inst[inst_counts >= min_tree_points]

        if len(valid_inst) == 0:
            # Nothing survives — keep all as one instance
            new_labels[tree_mask] = 201
            best = int(np.argmax(flat_chm[peak_flat_idx[basin_ids]]))
            return new_labels, 1, seed_peaks_out[best:best+1], seed_peaks_out

        if len(valid_inst) < len(unique_inst):
            # Re-run watershed with only valid seeds as markers
            valid_basin_ids_orig = (valid_inst - 200).astype(int)  # 1-based

            new_markers = np.zeros((rows, cols), dtype=np.int32)
            for new_i, orig_bid in enumerate(valid_basin_ids_orig):
                r_s = int(peak_flat_idx[orig_bid] // cols)
                c_s = int(peak_flat_idx[orig_bid] % cols)
                new_markers[r_s, c_s] = new_i + 1

            ws2 = watershed(-chm_smooth, markers=new_markers, mask=canopy_mask)
            point_basin2 = ws2[tr, tc]
            instance_ids = np.where(
                point_basin2 > 0, 200 + point_basin2, 201
            ).astype(np.int32)

            valid_peak_basin_ids = valid_basin_ids_orig
            print(f"[tree_segmentor] merged to {len(valid_basin_ids_orig)} valid instances")

    new_labels[tree_mask] = instance_ids
    tree_count = int(np.unique(instance_ids).size)

    # Final valid peaks (subset of seed_peaks_out)
    # basin_ids and seed_peaks_out are in the same order
    basin_id_to_idx = {int(bid): i for i, bid in enumerate(basin_ids)}
    valid_idx = [basin_id_to_idx[bid] for bid in valid_peak_basin_ids
                 if bid in basin_id_to_idx]
    peaks_out = seed_peaks_out[valid_idx] if valid_idx else seed_peaks_out[:1]

    print(f"[tree_segmentor] {tree_count} tree instances (Duncanson watershed)")
    return new_labels, tree_count, peaks_out, seed_peaks_out

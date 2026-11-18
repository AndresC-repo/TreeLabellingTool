"""
The city pipeline's filters, applied to a split-trees result so their effect can be seen.

Same rules and default values as urban-tree-detection (branch city-pipeline):
  - Rooftop test: src/city/process.py (structure_cells, trees_on_structure). A tree is removed
    when most of its 1 m cells have no ground-class point within 2 m and their lowest return is
    at least 2.5 m above the ground: clutter on a roof, not a tree standing on the ground.
  - Tree definition: src/city/combine.py. Top at least 2.5 m and at most 70 m above the
    ground, crown at least 3 m².
Both are off unless the request switches them on. Removed trees become non-tree (0); their tops
are returned so the 3D view can mark them.

Keep the two copies in step: if a value changes in the pipeline, change it here too.
"""
from __future__ import annotations

import numpy as np

NOISE_CLASSES = (7, 18)
STRUCTURE_SEARCH_M = 2.0
STRUCTURE_MIN_BASE_M = 2.5
TREE_MIN_HEIGHT_M = 2.5
TREE_MAX_HEIGHT_M = 70.0
TREE_MIN_CROWN_M2 = 3.0


def structure_cells(xyz: np.ndarray, cls: np.ndarray, x0: float, y0: float, shape: tuple,
                    search_m: float = STRUCTURE_SEARCH_M, min_base_m: float = STRUCTURE_MIN_BASE_M,
                    ground_cell: float = 2.0):
    """Copy of src/city/process.py::structure_cells (metres). (on_structure, lowest above ground) per 1 m cell."""
    from scipy import ndimage
    g = cls == 2
    if g.sum() < 50:
        return None
    lo = xyz[:, :2].min(axis=0)
    gij = np.floor((xyz[:, :2] - lo) / ground_cell).astype(np.int64)
    grid = np.full(gij.max(axis=0) + 1, np.inf)
    np.minimum.at(grid, (gij[g, 0], gij[g, 1]), xyz[g, 2])
    empty = ~np.isfinite(grid)
    if empty.any():
        near = ndimage.distance_transform_edt(empty, return_distances=False, return_indices=True)
        grid = grid[near[0], near[1]]
    above = xyz[:, 2] - grid[gij[:, 0], gij[:, 1]]

    pad = int(np.ceil(search_m))
    nx, ny = shape[0] + 2 * pad, shape[1] + 2 * pad
    c = np.floor(xyz[:, :2] - [x0 - pad, y0 - pad]).astype(np.int64)
    inside = (c[:, 0] >= 0) & (c[:, 0] < nx) & (c[:, 1] >= 0) & (c[:, 1] < ny)
    ground = np.zeros((nx, ny), dtype=bool)
    gi = inside & g
    ground[c[gi, 0], c[gi, 1]] = True
    yy, xx = np.ogrid[-pad:pad + 1, -pad:pad + 1]
    near_ground = ndimage.binary_dilation(ground, structure=(xx * xx + yy * yy) <= search_m * search_m)
    lowest = np.full((nx, ny), np.inf)
    np.minimum.at(lowest, (c[inside, 0], c[inside, 1]), above[inside])
    sl = (slice(pad, pad + shape[0]), slice(pad, pad + shape[1]))
    lowest, near_ground = lowest[sl], near_ground[sl]
    on_structure = ~near_ground & np.isfinite(lowest) & (lowest >= min_base_m)
    return on_structure, np.where(np.isfinite(lowest), lowest, np.nan)


def trees_on_structure(xy: np.ndarray, inst: np.ndarray, on_structure: np.ndarray, lowest: np.ndarray,
                       x0: float, y0: float) -> dict:
    """Copy of src/city/process.py::trees_on_structure. {instance id: (on a structure?, base height m)}."""
    out = {}
    c = np.floor(xy - [x0, y0]).astype(np.int64)
    ok = (inst > 0) & (c[:, 0] >= 0) & (c[:, 0] < on_structure.shape[0]) & (c[:, 1] >= 0) & (c[:, 1] < on_structure.shape[1])
    if not ok.any():
        return out
    cell = c[ok, 0] * on_structure.shape[1] + c[ok, 1]
    pairs = np.unique(np.stack([inst[ok], cell], axis=1), axis=0)
    flat_s, flat_l = on_structure.ravel(), lowest.ravel()
    pairs = pairs[np.argsort(pairs[:, 0], kind="stable")]
    starts = np.flatnonzero(np.r_[True, pairs[1:, 0] != pairs[:-1, 0]])
    for a, b in zip(starts, np.r_[starts[1:], len(pairs)]):
        cells = pairs[a:b, 1]
        base = flat_l[cells]
        out[int(pairs[a, 0])] = (float(flat_s[cells].mean()) > 0.5,
                                 float(np.nanmedian(base)) if np.isfinite(base).any() else None)
    return out


def apply_filters(x, y, z, classification, labels, metres_per_unit: float,
                  rooftop: bool = False, definition: bool = False,
                  min_height: float = TREE_MIN_HEIGHT_M, max_height: float = TREE_MAX_HEIGHT_M,
                  min_crown_area: float = TREE_MIN_CROWN_M2) -> dict:
    """Remove trees as the city pipeline would. labels: 0 / 201+ (instances).

    Returns dict(labels, removed_tops [[x, y, z] file units], stats). Removed trees become 0.
    """
    labels = np.asarray(labels, dtype=np.int32).copy()
    stats = dict(filters_rooftop=bool(rooftop), filters_definition=bool(definition),
                 removed_on_structure=0, removed_too_low=0, removed_too_tall=0, removed_small_crown=0,
                 rooftop_unavailable=False)
    removed_tops: list[list[float]] = []
    if not (rooftop or definition):
        return dict(labels=labels, removed_tops=removed_tops, stats=stats)

    mpu = float(metres_per_unit or 1.0)
    xf, yf, zf = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    cls = np.asarray(classification, dtype=np.int32)
    ids = np.unique(labels[labels >= 201])
    if ids.size == 0:
        return dict(labels=labels, removed_tops=removed_tops, stats=stats)
    stats["trees_before_filters"] = int(ids.size)
    reason: dict[int, str] = {}

    if rooftop:
        xyz = np.c_[xf, yf, zf] * mpu
        valid = ~np.isin(cls, NOISE_CLASSES)
        x0, y0 = np.floor(xyz[valid, :2].min(axis=0))
        shape = tuple((np.ceil(xyz[valid, :2].max(axis=0) - [x0, y0]) + 1).astype(int))
        st = structure_cells(xyz[valid], cls[valid], x0, y0, shape)
        if st is None:
            stats["rooftop_unavailable"] = True      # too few ground-class points to tell
        else:
            inst = np.where(labels >= 201, labels - 200, 0).astype(np.int64)
            for tid, (flag, _base) in trees_on_structure(xyz[:, :2], inst, st[0], st[1], x0, y0).items():
                if flag:
                    reason[tid + 200] = "on_structure"
            stats["structure_area_m2"] = int(st[0].sum())

    if definition:
        from services.tree_metrics import compute_tree_metrics
        for m in compute_tree_metrics(xf, yf, zf, labels, cls, unit_scale=mpu):
            tid = int(m["id"])
            if tid in reason:
                continue
            if m["height"] < min_height:
                reason[tid] = "too_low"
            elif m["height"] > max_height:
                reason[tid] = "too_tall"
            elif m["crown_area"] < min_crown_area:
                reason[tid] = "small_crown"

    key = dict(on_structure="removed_on_structure", too_low="removed_too_low",
               too_tall="removed_too_tall", small_crown="removed_small_crown")
    for tid, why in reason.items():
        sel = labels == tid
        if not sel.any():
            continue
        top = np.flatnonzero(sel)[np.argmax(zf[sel])]
        removed_tops.append([float(xf[top]), float(yf[top]), float(zf[top])])
        labels[sel] = 0
        stats[key[why]] += 1

    # renumber the remaining trees 201, 202, ... so colours and counts stay tidy
    keep = np.unique(labels[labels >= 201])
    remap = {int(old): 201 + i for i, old in enumerate(keep)}
    if remap:
        lut = np.zeros(int(labels.max()) + 1, dtype=np.int32)
        for old, new in remap.items():
            lut[old] = new
        labels = np.where(labels >= 201, lut[np.clip(labels, 0, len(lut) - 1)], labels)
    stats["trees_after_filters"] = len(remap)
    return dict(labels=labels, removed_tops=removed_tops, stats=stats)

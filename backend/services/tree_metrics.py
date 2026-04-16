"""
Per-tree crown metrics after instance segmentation.

Metrics follow Duncanson et al. (2014):
  Ht  — tree height        : max height-above-terrain in the instance
  Hb  — crown base height  : 10th-percentile height-above-terrain
                             (proxy for the lowest live branch)
  Lc  — live crown length  : Ht − Hb
  CW  — crown width        : mean of E-W and N-S extents of the footprint
  CA  — crown area         : occupied CHM-cell count × cell_size² (m²)
"""
from __future__ import annotations
import math
import numpy as np


def compute_tree_metrics(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    labels: np.ndarray,         # int32 (N,) — 0=non-tree, 201+=instances
    original_cls: np.ndarray,   # int32 (N,) — ASPRS class, 2=ground
    cell_size: float = 1.5,
    dtm_grid=None,
    dtm_rows: int = 64,
    dtm_cols: int = 64,
    dtm_x_min: float = 0.0,
    dtm_y_min: float = 0.0,
    dtm_x_range: float = 1.0,
    dtm_y_range: float = 1.0,
) -> list[dict]:
    """Return a list of metric dicts sorted by tree ID."""
    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    z = np.asarray(z, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int32)

    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    cols = max(int(np.ceil((x_max - x_min) / cell_size)) + 1, 1)
    rows = max(int(np.ceil((y_max - y_min) / cell_size)) + 1, 1)

    def _rc(px, py):
        c = np.clip(((px - x_min) / cell_size).astype(np.int32), 0, cols - 1)
        r = np.clip(((py - y_min) / cell_size).astype(np.int32), 0, rows - 1)
        return r, c

    # ── DTM ──────────────────────────────────────────────────────────────────
    if dtm_grid is not None:
        dtm_arr = np.array(dtm_grid, dtype=np.float32).reshape(dtm_rows, dtm_cols)
        cx = np.clip(((x - dtm_x_min) / dtm_x_range * dtm_cols).astype(np.int32),
                     0, dtm_cols - 1)
        cy = np.clip(((y - dtm_y_min) / dtm_y_range * dtm_rows).astype(np.int32),
                     0, dtm_rows - 1)
        terrain_z = dtm_arr[cy, cx]
    else:
        flat = rows * cols
        gnd = original_cls == 2
        dtm_flat = np.full(flat, np.inf, dtype=np.float32)
        if gnd.any():
            gr, gc = _rc(x[gnd], y[gnd])
            np.minimum.at(dtm_flat, gr * cols + gc, z[gnd])
            fallback = float(z[gnd].mean())
        else:
            fallback = float(z.min())
        dtm_flat[dtm_flat == np.inf] = fallback
        dtm_2d = dtm_flat.reshape(rows, cols)
        pr, pc = _rc(x, y)
        terrain_z = dtm_2d[pr, pc]

    hat = np.maximum(0.0, z - terrain_z)   # height above terrain

    # ── Per-instance metrics ──────────────────────────────────────────────────
    tree_ids = np.unique(labels)
    tree_ids = tree_ids[tree_ids >= 201]

    metrics = []
    for tid in tree_ids:
        mask = labels == tid
        tx, ty = x[mask], y[mask]
        th = hat[mask]

        Ht = float(th.max())
        Hb = float(np.percentile(th, 10))
        Lc = max(0.0, Ht - Hb)

        # Crown area: unique CHM cells occupied by the instance
        cr, cc = _rc(tx, ty)
        n_cells = int(np.unique(cr * cols + cc).size)
        ca = n_cells * cell_size * cell_size

        # Crown width — area-derived circular equivalent diameter.
        # Using max-min extent is unreliable: a few outlier points far from
        # the main crown inflate it dramatically (e.g. 90 m for a 27 m crown).
        # 2*sqrt(CA/π) gives the diameter of a circle with the same footprint area.
        cw = 2.0 * math.sqrt(ca / math.pi) if ca > 0 else 0.0

        # Raw extents kept as supplementary info
        width_ew = float(tx.max() - tx.min())
        width_ns = float(ty.max() - ty.min())

        metrics.append({
            'id':           int(tid),
            'height':       round(Ht, 2),
            'base_height':  round(Hb, 2),
            'crown_length': round(Lc, 2),
            'crown_width':  round(cw, 2),
            'width_ew':     round(width_ew, 2),
            'width_ns':     round(width_ns, 2),
            'crown_area':   round(ca, 1),
            'point_count':  int(mask.sum()),
        })

    return sorted(metrics, key=lambda m: m['id'])

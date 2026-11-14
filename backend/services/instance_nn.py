"""
Split tree points into single trees with the instance network (Instance_model.pth, run I02).

How it is used (from the 3D view):
  1. The tree mask comes from the tool (the points shown as tree after Run Inference with
     best_model_m.pth = E12, after the threshold slider and any hand edits).
  2. Instance_model.pth runs on the same pre-processing as E12 (XY relative to the tile
     centre, Z = height above ground from the 64x64 ground grid, 0.08 m voxels, XYZ only).
  3. Only offsets[:, :2] (metres, towards the tree centre) are used. The third offset channel,
     the embeddings and the model's own Semantic head are not.
  4. Tree points are grouped with cluster_trees (verbatim copy of the training repo's
     src/instances/clustering.py) using the clustering settings uploaded next to the model.

Reference implementation: urban-tree-detection/src/instances/predict.py (run_tile, TileIndex,
predict_cloud). The functions below follow it line by line; the differences are that the tree
mask is given instead of computed, and the network outputs are cached per patch so changing a
clustering setting does not run the network again.
The old mean-shift route (predictor.predict_instances / "predict-instances") is NOT used.
"""
from __future__ import annotations

import json
import os

import numpy as np
import torch
import spconv.pytorch as spconv
from huggingface_hub import hf_hub_download

from services import predictor
from services.instance_clustering import cluster_trees, DEFAULT_PARAMS

MODEL_VERSION = 'instance'                 # key in predictor._MODEL_CONFIGS
VOXEL = 0.08                               # m, data.voxel_size of the I02 run
NOISE_CLASSES = (7, 18)
MIN_TILE_POINTS = 500
TILE, BUFFER = 60.0, 15.0                  # m, predict.py defaults

# I02's clustering.json (tuned on val). Used when the file on Hugging Face can't be read.
I02_CLUSTERING = dict(cell=0.25, sigma=0.75, min_peak_distance=4.0, min_crown_area=2.0,
                      min_points=10, embed_weight=0.0)
_CLUSTER_FILES = ('clustering_Instance_model.json', 'clustering.json')

_cache: dict[str, dict] = {}               # "session:patch" -> network outputs per tile


# ----------------------------------------------------------------------------- settings
def clustering_settings() -> tuple[dict, str]:
    """(params, source). Settings from the JSON uploaded next to the model, else I02's."""
    for name in _CLUSTER_FILES:
        try:
            path = hf_hub_download(repo_id=predictor._MODEL_REPO, filename=name)
            raw = json.loads(open(path).read())
            params = {k: v for k, v in raw.items() if k in DEFAULT_PARAMS}
            params['embed_weight'] = 0.0       # embeddings are untrained
            return params, f"Hugging Face: {name}"
        except Exception:
            continue
    return dict(I02_CLUSTERING), "built-in I02 settings (clustering file not found on Hugging Face)"


# ----------------------------------------------------------------------------- ground
def ground_grid_terrain(coords: np.ndarray, lidar_class, grid: int = 64):
    """Copy of src/data/dataset.py::ground_grid_terrain (the training ground model)."""
    if lidar_class is None:
        return None
    g = lidar_class == 2
    if not g.any():
        return None
    x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]
    x_min, y_min = x.min(), y.min()
    xr, yr = max(float(x.max() - x_min), 1e-6), max(float(y.max() - y_min), 1e-6)
    cx = np.minimum(((x - x_min) / xr * grid).astype(np.int64), grid - 1)
    cy = np.minimum(((y - y_min) / yr * grid).astype(np.int64), grid - 1)
    cell = cy * grid + cx
    terrain = np.full(grid * grid, np.inf, dtype=np.float64)
    np.minimum.at(terrain, cell[g], z[g])
    covered = np.isfinite(terrain)
    queue = list(np.flatnonzero(covered))
    head = 0
    while head < len(queue):
        i = queue[head]; head += 1
        r, c = divmod(int(i), grid)
        for j in (i - grid if r > 0 else -1, i + grid if r < grid - 1 else -1,
                  i - 1 if c > 0 else -1, i + 1 if c < grid - 1 else -1):
            if j >= 0 and not covered[j]:
                covered[j] = True
                terrain[j] = terrain[i]
                queue.append(j)
    return terrain[cell].astype(np.float32)


# ----------------------------------------------------------------------------- network
@torch.no_grad()
def _offsets_tile(model, xyz_m: np.ndarray, ground_class: np.ndarray) -> np.ndarray:
    """predict.py::run_tile for one tile; returns per-point offsets[:, :2] in metres."""
    coords = xyz_m.astype(np.float32).copy()
    centre_xy = coords[:, :2].mean(axis=0)
    z_ground = ground_grid_terrain(coords, ground_class)          # ground_model: dtm
    if z_ground is None:
        z_ground = np.percentile(coords[:, 2], 5)
    coords[:, :2] -= centre_xy
    coords[:, 2] -= z_ground

    vox = np.round(coords / VOXEL).astype(np.int32)
    vox -= vox.min(axis=0)
    _, first, inverse = np.unique(vox, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    indices = np.hstack([np.zeros((len(first), 1), dtype=np.int32), vox[first]])
    st = spconv.SparseConvTensor(
        features=torch.from_numpy(np.ascontiguousarray(coords[first], dtype=np.float32)),
        indices=torch.from_numpy(indices).int(),
        spatial_shape=(vox.max(axis=0) + 1).tolist(), batch_size=1)
    out = model(st)
    return out['offsets'][:, :2].float().cpu().numpy()[inverse]


class TileIndex:
    """predict.py::TileIndex — points binned into square tiles (3x3 neighbourhood each)."""

    def __init__(self, xy: np.ndarray, tile: float, buffer: float):
        self.xy, self.tile, self.buffer = xy, float(tile), float(buffer)
        self.lo = xy.min(axis=0)
        ext = xy.max(axis=0) - self.lo
        self.single = bool((ext <= tile + 2 * buffer).all())
        if self.single:
            self.shape = (1, 1)
            return
        ij = np.floor((xy - self.lo) / tile).astype(np.int64)
        self.shape = tuple(int(v) for v in ij.max(axis=0) + 1)
        key = ij[:, 0] * self.shape[1] + ij[:, 1]
        self.order = np.argsort(key, kind='stable')
        self.starts = np.searchsorted(key[self.order], np.arange(self.shape[0] * self.shape[1] + 1))

    def tiles(self):
        if self.single:
            hi = self.xy.max(axis=0) + 1e-6
            yield np.arange(len(self.xy)), np.ones(len(self.xy), dtype=bool), (*self.lo, *hi)
            return
        nx, ny = self.shape
        for i in range(nx):
            for j in range(ny):
                if self.starts[i * ny + j] == self.starts[i * ny + j + 1]:
                    continue
                parts = [self.order[self.starts[a * ny + b]:self.starts[a * ny + b + 1]]
                         for a in range(max(i - 1, 0), min(i + 2, nx))
                         for b in range(max(j - 1, 0), min(j + 2, ny))]
                idx = np.sort(np.concatenate(parts))
                x0, y0 = self.lo + np.array([i, j]) * self.tile
                x1, y1 = x0 + self.tile, y0 + self.tile
                p = self.xy[idx]
                b = self.buffer
                near = (p[:, 0] >= x0 - b) & (p[:, 0] < x1 + b) & (p[:, 1] >= y0 - b) & (p[:, 1] < y1 + b)
                idx, p = idx[near], p[near]
                core = (p[:, 0] >= x0) & (p[:, 0] < x1) & (p[:, 1] >= y0) & (p[:, 1] < y1)
                yield idx, core, (x0, y0, x1, y1)


def _network_outputs(key: str, xyz_m: np.ndarray, ground_class: np.ndarray) -> dict:
    """Offsets for every tile of the cloud; cached per patch and model file."""
    model = predictor._get_model(MODEL_VERSION)
    model_path = predictor._loaded_path.get(MODEL_VERSION, '')
    hit = _cache.get(key)
    if hit and hit['model'] == model_path and hit['n'] == len(xyz_m):
        return hit
    tiles = []
    index = TileIndex(xyz_m[:, :2], TILE, BUFFER)
    for idx, core, box in index.tiles():
        if len(idx) < MIN_TILE_POINTS:
            continue
        tiles.append((idx, core, box, _offsets_tile(model, xyz_m[idx], ground_class[idx])))
    out = dict(model=model_path, n=len(xyz_m), tiles=tiles)
    _cache[key] = out
    while len(_cache) > 8:
        _cache.pop(next(iter(_cache)))
    return out


def forget(key_prefix: str) -> None:
    for k in [k for k in _cache if k.startswith(key_prefix)]:
        _cache.pop(k, None)


# ----------------------------------------------------------------------------- public
def split_trees(cache_key: str, x, y, z, classification, tree_mask: np.ndarray,
                metres_per_unit: float, ground_labels: np.ndarray | None = None,
                params: dict | None = None) -> dict:
    """Instance IDs for the tree points of a patch.

    Args:
        x, y, z         : (N,) file coordinates (file units)
        classification  : (N,) the file's ASPRS classes (ground = 2, noise = 7/18)
        tree_mask       : (N,) bool, which points are trees (from the tool)
        metres_per_unit : file units -> metres
        ground_labels   : (N,) the tool's labels; used for the ground only when the file
                          has no class-2 points (same rule as the 3D view)
        params          : clustering overrides (metres)
    Returns dict: labels (N,) int32 0 / 201.. ; tree_count; tops [[x, y, z]] in file units;
                  settings; unassigned (tree points without a tree)
    """
    x, y, z = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    n = len(x)
    settings, source = clustering_settings()
    settings.update({k: v for k, v in (params or {}).items() if k in DEFAULT_PARAMS and v is not None})
    settings['embed_weight'] = 0.0

    mpu = float(metres_per_unit or 1.0)
    xyz = np.stack([np.asarray(x, np.float64), np.asarray(y, np.float64), np.asarray(z, np.float64)], 1) * mpu
    shift = np.floor(xyz.min(axis=0))
    xyz = xyz - shift                                   # small numbers before the float32 cast
    cls = np.asarray(classification, dtype=np.int32)
    ground = cls
    if (cls == 2).sum() < 20 and ground_labels is not None and (np.asarray(ground_labels) == 2).sum() >= 20:
        ground = np.where(np.asarray(ground_labels) == 2, 2, cls)
    valid = ~np.isin(cls, NOISE_CLASSES)
    mask = np.asarray(tree_mask, dtype=bool) & valid

    labels = np.zeros(n, dtype=np.int32)
    empty = dict(labels=labels, tree_count=0, tops=[], settings=settings, settings_source=source,
                 unassigned=int(mask.sum()))
    if not mask.any():
        return empty

    vidx = np.flatnonzero(valid)
    out = _network_outputs(cache_key, xyz[vidx], ground[vidx])
    tree_v = mask[vidx]

    # predict.py::predict_cloud, with the given mask instead of prob >= threshold
    m = len(vidx)
    best_dist = np.full(m, np.inf, dtype=np.float32)
    best_id = np.zeros(m, dtype=np.int64)
    next_id = 1
    cloud_lo = xyz[vidx, :2].min(axis=0)
    cloud_hi = xyz[vidx, :2].max(axis=0) - 1e-3
    for idx, core, (x0, y0, x1, y1), offs in out['tiles']:
        tree = tree_v[idx]
        if not tree.any():
            continue
        pts = xyz[vidx[idx]]
        t_idx = idx[tree]
        lab, info = cluster_trees(pts[tree, :2], offs[tree], None, return_info=True, **settings)
        if len(info['centers']) == 0:
            continue
        c = info['centers']
        cc = np.clip(c, cloud_lo, cloud_hi)
        owned = (cc[:, 0] >= x0) & (cc[:, 0] < x1) & (cc[:, 1] >= y0) & (cc[:, 1] < y1)
        votes = pts[tree, :2] + offs[tree]
        for k in np.flatnonzero(owned):
            sel = lab == k + 1
            dist = np.linalg.norm(votes[sel] - c[k], axis=1).astype(np.float32)
            g = t_idx[sel]
            better = dist < best_dist[g]
            best_dist[g[better]] = dist[better]
            best_id[g[better]] = next_id
            next_id += 1

    best_id[~tree_v] = 0
    min_points = int(settings.get('min_points', DEFAULT_PARAMS['min_points']))
    ids, inv, counts = np.unique(best_id, return_inverse=True, return_counts=True)
    keep = (ids > 0) & (counts >= min_points)
    remap = np.zeros(len(ids), dtype=np.int32)
    remap[keep] = np.arange(1, int(keep.sum()) + 1)
    inst = remap[inv.reshape(-1)]

    labels[vidx] = np.where(inst > 0, 200 + inst, 0)
    K = int(inst.max()) if len(inst) else 0
    tops = []
    zf = np.asarray(z, np.float64)
    for k in range(1, K + 1):
        g = vidx[inst == k]
        t = g[np.argmax(zf[g])]
        tops.append([float(x[t]), float(y[t]), float(zf[t])])
    return dict(labels=labels, tree_count=K, tops=tops, settings=settings, settings_source=source,
                unassigned=int((mask & (labels == 0)).sum()))

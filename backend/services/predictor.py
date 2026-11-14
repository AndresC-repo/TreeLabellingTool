"""
Inference service for SegmentAnyTree models (Hugging Face: AndCarr/UrbanTreeDetector).

metric      -- XYZ, METRES  in_channels=3  best_model_m.pth      (latest)  tree/non-tree only, threshold 0.55
metric_old  -- XYZ, METRES  in_channels=3  best_model_m_old.pth  (previous)       threshold 0.75
"""
from __future__ import annotations
import os
import time
import numpy as np
import torch
import spconv.pytorch as spconv
from spconv.pytorch import SparseConvTensor
from huggingface_hub import hf_hub_download
from services.segment_any_tree import SegmentAnyTree

_MODEL_REPO = "AndCarr/UrbanTreeDetector"
_VOXEL_SIZE = 0.08  # model-frame units -- must match training (finetune_config.yaml: voxel_size: 0.08)

# ── Units ─────────────────────────────────────────────────────────────────────
# Each model config has 'input_units':
#   'raw' -- the model was trained on coordinates in the files' own units (the older
#            models: mostly US survey feet read as if metres). Input is fed as-is.
#   'm'   -- the model was trained in metres. x, y, z (and the DTM) are multiplied by
#            the file's metres-per-unit before voxelising, so 0.08 = 8 cm.
# Everything downstream (voxels, tiling, offsets, clustering) runs in this "model frame".
# Clustering parameters coming from the UI (bandwidth, max_spread) are in METRES and are
# converted into the model frame. Outputs are per-point labels, so nothing has to be
# converted back.

# Sliding-window inference constants (model-frame units: metres for 'm' models)
# The model was trained on small patches (~20-30 m diameter).
# When the input exceeds _MAX_DIRECT_M in X or Y we tile it into overlapping
# windows, run the model on each tile, and merge by averaging softmax scores.
_MAX_DIRECT_M = 150.0   # metres -- below this, run in one shot
_TILE_SIZE_M  = 120.0   # side length of each inference tile
_TILE_STEP_M  =  60.0   # step between tiles (50 % overlap)
_MIN_TILE_PTS =  20     # skip tiles with fewer points than this

# Hugging Face convention (AndCarr/UrbanTreeDetector):
#   best_model_m.pth      latest metric model
#   best_model_m_old.pth  the previous one (moved there when a new latest is uploaded)
_MODEL_CONFIGS: dict[str, dict] = {
    'metric': {
        'filename':           'best_model_m.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'input_units':        'm',
        'label':              'XYZ (m)',
        'tag':                'latest',
        'threshold':          0.55,    # tree if P(tree) >= threshold
        'instance_heads':     False,   # tree / non-tree only: no offset / embedding heads
    },
    'metric_old': {
        'filename':           'best_model_m_old.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'input_units':        'm',
        'label':              'XYZ (m)',
        'tag':                'old',
        'threshold':          0.75,
        'instance_heads':     True,    # checked again when the file is loaded
    },
    # Splits trees only (offsets). Never used for tree / non-tree: the mask comes from
    # best_model_m.pth (E12). See services/instance_nn.py.
    'instance': {
        'filename':           'Instance_model.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'input_units':        'm',
        'label':              'Instance NN',
        'tag':                'splits trees',
        'role':               'instance',
        'threshold':          0.5,
        'instance_heads':     True,
    },
}

_loaded: dict[str, SegmentAnyTree] = {}
_loaded_path: dict[str, str] = {}   # version -> real path of the loaded file (changes on a new upload)
_has_heads: dict[str, bool] = {}    # version -> checkpoint contains trained Offset/Embed heads

# NN output cache: key = "session_id:patch_id:version"
# Stores (pt_probs, pt_offs, pt_embs) so Run Instance Segmentation
# can re-use the forward pass from Run Inference without hitting the NN again.
_NN_CACHE: dict[str, tuple] = {}
VALID_VERSIONS = tuple(_MODEL_CONFIGS.keys())


# ---------------------------------------------------------------------------
# Model list for the UI: when was each file last updated on Hugging Face
# ---------------------------------------------------------------------------

_CATALOG_TTL = 600   # seconds
_catalog_cache: dict = {"at": 0.0, "data": None}


def model_catalog(refresh: bool = False) -> list[dict]:
    """[{id, label, tag, filename, available, updated, commit_title, size, source}]

    source "hub":   date of the last commit that changed the file on Hugging Face
    source "cache": Hub unreachable; available = the file is in the local download cache
    """
    if not refresh and _catalog_cache["data"] and time.time() - _catalog_cache["at"] < _CATALOG_TTL:
        return _catalog_cache["data"]
    from huggingface_hub import HfApi, try_to_load_from_cache
    files = [c['filename'] for c in _MODEL_CONFIGS.values()]
    info, source = {}, "hub"
    try:
        for f in HfApi().get_paths_info(_MODEL_REPO, files, expand=True):
            lc = getattr(f, "last_commit", None)
            info[f.path] = {
                "available": True,
                "updated": lc.date.isoformat() if lc and lc.date else None,
                "commit_title": lc.title if lc else None,
                "size": getattr(f, "size", None),
            }
    except Exception as e:
        print(f"[predictor] Hugging Face not reachable for the model list: {e}")
        source = "cache"
        for name in files:
            cached = try_to_load_from_cache(_MODEL_REPO, name)
            if isinstance(cached, str):
                info[name] = {"available": True, "updated": None, "commit_title": None,
                              "size": os.path.getsize(cached),
                              "downloaded": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                          time.gmtime(os.path.getmtime(cached))) + "+00:00"}
    out = []
    for vid, c in _MODEL_CONFIGS.items():
        i = info.get(c['filename'], {"available": False, "updated": None, "commit_title": None, "size": None})
        out.append({"id": vid, "label": c['label'], "tag": c.get('tag', ''), "filename": c['filename'],
                    "role": c.get('role', 'semantic'),
                    "input_units": c['input_units'], "threshold": c.get('threshold', 0.5),
                    "instance_heads": bool(c.get('instance_heads', True) and _has_heads.get(vid, True)),
                    "source": source, **i})
    # offline answers are only kept for a minute, so the dates show up soon after reconnecting
    _catalog_cache.update(at=time.time() - (_CATALOG_TTL - 60 if source == "cache" else 0), data=out)
    return out


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _get_model(version: str) -> SegmentAnyTree:
    cfg = _MODEL_CONFIGS[version]
    # hf_hub_download checks the Hub each time (a quick HEAD request) and only downloads
    # when the file changed; offline it returns the cached copy. A new upload therefore
    # gives a new path, and the model is reloaded.
    path = os.path.realpath(hf_hub_download(repo_id=_MODEL_REPO, filename=cfg['filename']))
    if version in _loaded and _loaded_path.get(version) == path:
        return _loaded[version]
    if version in _loaded:
        print(f"[predictor] {cfg['filename']} changed on Hugging Face -- reloading.")
        for k in [k for k in _NN_CACHE if f":{version}:" in k]:
            _NN_CACHE.pop(k, None)   # cached outputs of the previous model
    _loaded_path[version] = path
    print(f"[predictor] Loading state dict from {path} ...")

    obj = torch.load(path, map_location='cpu', weights_only=False)

    if isinstance(obj, dict):
        state_dict = obj.get('model_state_dict') or obj.get('state_dict') or obj
    else:
        _loaded[version] = obj
        obj.eval()
        print(f"[predictor] {version.upper()} ready (full-model save).")
        return obj

    _has_heads[version] = any(k.startswith(('Offset.', 'Embed.')) for k in state_dict)

    # Auto-detect embedding_dim from checkpoint (Embed.1.weight shape[0])
    embed_weight = state_dict.get('Embed.1.weight')
    embedding_dim = int(embed_weight.shape[0]) if embed_weight is not None else 5

    model = SegmentAnyTree(in_channels=cfg['in_channels'], num_classes=2,
                           embedding_dim=embedding_dim)

    model_dict = model.state_dict()
    loaded = skipped_shape = skipped_missing = 0
    for key, value in state_dict.items():
        if key not in model_dict:
            skipped_missing += 1
            continue
        if model_dict[key].shape == value.shape:
            model_dict[key] = value
            loaded += 1
        elif len(model_dict[key].shape) == 3 and len(value.shape) == 2:
            model_dict[key] = value.unsqueeze(0)
            loaded += 1
        else:
            skipped_shape += 1
            print(f"[predictor] WARNING shape mismatch -- skipping {key}: "
                  f"ckpt {tuple(value.shape)} vs model {tuple(model_dict[key].shape)}")

    model.load_state_dict(model_dict, strict=False)
    print(f"[predictor] {version.upper()} loaded: {loaded} layers "
          f"(skipped shape={skipped_shape}, missing={skipped_missing}).")

    _force_spconv_native(model)
    model.eval()
    _loaded[version] = model
    print(f"[predictor] {version.upper()} ({cfg['label']}) ready.")
    return model


def _force_spconv_native(model: SegmentAnyTree) -> None:
    """Set ConvAlgo.Native on every spconv layer for CPU inference."""
    try:
        from spconv.core import ConvAlgo
    except ImportError:
        try:
            from spconv.algo import ConvAlgo
        except ImportError:
            print("[predictor] WARNING: cannot import ConvAlgo -- "
                  "spconv algo not overridden; inference may fail on CPU.")
            return
    native = ConvAlgo.Native
    count = 0
    for m in model.modules():
        if hasattr(m, 'algo'):
            m.algo = native
            count += 1
    print(f"[predictor] Forced ConvAlgo.Native on {count} spconv layer(s).")


# ---------------------------------------------------------------------------
# Voxelisation
# ---------------------------------------------------------------------------

def _voxelize_metric(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    terrain_z: np.ndarray | float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Voxelize in metric units with HAG coordinate frame.

    Coordinate frame -- MUST match dataset.py __getitem__:
      XY : centroid-subtracted (per tile)
      Z  : height above ground (HAG) = z - terrain_z
           terrain_z can be:
             np.ndarray (N,)  -- per-point ground elevation from DTM (best)
             float            -- global scalar fallback
             None             -- compute from percentile(z, 5) of this tile

    Returns
    -------
    coords  : int32  (V, 4)  [batch=0, ix, iy, iz]
    feats   : float32 (V, C)
    inv_map : int64  (N,)
    """
    pts = np.stack([x, y, z], axis=1).astype(np.float32)

    xy_centroid = pts[:, :2].mean(axis=0)
    if terrain_z is None:
        z_ground = np.float32(np.percentile(pts[:, 2], 5))
    else:
        z_ground = np.asarray(terrain_z, dtype=np.float32)  # scalar or (N,)

    pts_c = pts.copy()
    pts_c[:, :2] -= xy_centroid  # XY centroid-relative
    pts_c[:, 2]  -= z_ground     # Z: HAG (per-point if DTM supplied, else global scalar)

    vox = np.round(pts_c / _VOXEL_SIZE).astype(np.int32)
    unique_vox, inv_map = np.unique(vox, axis=0, return_inverse=True)
    V = len(unique_vox)

    cols = [pts_c]
    if intensity is not None:
        cols.append((intensity / 65535.0).reshape(-1, 1).astype(np.float32))
    if classification is not None:
        cls = classification.astype(np.int32)
        cols.append((cls == 2).astype(np.float32).reshape(-1, 1))  # is_ground
        cols.append((cls == 6).astype(np.float32).reshape(-1, 1))  # is_building

    all_feats = np.concatenate(cols, axis=1).astype(np.float32)
    C = all_feats.shape[1]

    feats  = np.zeros((V, C), dtype=np.float32)
    counts = np.zeros(V,      dtype=np.float32)
    np.add.at(feats,  inv_map, all_feats)
    np.add.at(counts, inv_map, 1.0)
    feats /= counts[:, None]

    coords = np.concatenate(
        [np.zeros((V, 1), dtype=np.int32), unique_vox.astype(np.int32)],
        axis=1,
    )
    return coords, feats, inv_map


# ---------------------------------------------------------------------------
# Forward pass helpers
# ---------------------------------------------------------------------------

def _forward_chunk(
    model: SegmentAnyTree,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    terrain_z: np.ndarray | float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Voxelise one chunk and run a single model forward pass.

    Returns per-original-point arrays:
      probs      : float32 (N, 2)
      offsets    : float32 (N, 3)
      embeddings : float32 (N, E)
    """
    coords, feats, inv_map = _voxelize_metric(x, y, z, intensity, classification,
                                               terrain_z=terrain_z)

    vox_xyz = coords[:, 1:]
    min_vox = vox_xyz.min(axis=0)
    shifted = (vox_xyz - min_vox).astype(np.int32)
    sp_shape = (shifted.max(axis=0) + 1).tolist()
    indices = np.concatenate(
        [np.zeros((len(shifted), 1), dtype=np.int32), shifted], axis=1
    )

    sparse_in = SparseConvTensor(
        features=torch.from_numpy(feats).float(),
        indices=torch.from_numpy(indices).int(),
        spatial_shape=sp_shape,
        batch_size=1,
    )
    with torch.no_grad():
        out = model(sparse_in)

    vox_probs = torch.softmax(out['semantic_logits'], dim=1).cpu().numpy()
    vox_offs  = out['offsets'].cpu().numpy()
    vox_embs  = out['embeddings'].cpu().numpy()

    return vox_probs[inv_map], vox_offs[inv_map], vox_embs[inv_map]


def _compute_terrain_z(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    dtm_grid: list | None,
    dtm_rows: int,
    dtm_cols: int,
    dtm_x_min: float,
    dtm_y_min: float,
    dtm_x_range: float,
    dtm_y_range: float,
) -> np.ndarray | None:
    """Compute per-point ground elevation from DTM grid, or None if no DTM."""
    if dtm_grid is None:
        return None
    dtm_arr = np.array(dtm_grid, dtype=np.float32).reshape(dtm_rows, dtm_cols)
    cx = np.clip(((x - dtm_x_min) / dtm_x_range * dtm_cols).astype(np.int32), 0, dtm_cols - 1)
    cy = np.clip(((y - dtm_y_min) / dtm_y_range * dtm_rows).astype(np.int32), 0, dtm_rows - 1)
    return dtm_arr[cy, cx]


def _predict_with_tiling(
    model: SegmentAnyTree,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    version: str,
    terrain_z: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sliding-window inference over large point clouds.

    Tiles XY into overlapping _TILE_SIZE_M windows with _TILE_STEP_M step.
    Returns (probs, offsets, embeddings) averaged over all covering tiles.
    terrain_z: per-point ground elevation from DTM (N,), or None for fallback.
    """
    n = len(x)
    accum_probs = np.zeros((n, 2), dtype=np.float64)
    accum_offs  = np.zeros((n, 3), dtype=np.float64)
    accum_embs  = None
    count       = np.zeros(n, dtype=np.float64)

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())

    x_starts = np.arange(xmin, xmax, _TILE_STEP_M)
    y_starts = np.arange(ymin, ymax, _TILE_STEP_M)
    total    = len(x_starts) * len(y_starts)

    # Z reference: use DTM per-point terrain if available, else global percentile.
    # Per-tile percentile(z,5) is unreliable for corner tiles dominated by buildings.
    if terrain_z is not None:
        print(f"[predictor:{version}] {xmax-xmin:.0f}m x {ymax-ymin:.0f}m -- "
              f"sliding window ({total} tiles), DTM per-point HAG ...")
    else:
        z_ground_global = float(np.percentile(z, 5))
        print(f"[predictor:{version}] {xmax-xmin:.0f}m x {ymax-ymin:.0f}m -- "
              f"sliding window ({total} tiles), global z_ground={z_ground_global:.2f}m ...")

    done = 0
    for xs in x_starts:
        for ys in y_starts:
            done += 1
            mask = (
                (x >= xs) & (x < xs + _TILE_SIZE_M) &
                (y >= ys) & (y < ys + _TILE_SIZE_M)
            )
            idx = np.where(mask)[0]
            if len(idx) < _MIN_TILE_PTS:
                continue

            tile_int = intensity[idx]      if intensity      is not None else None
            tile_cls = classification[idx] if classification is not None else None

            tile_tz = terrain_z[idx] if terrain_z is not None else z_ground_global
            probs, offs, embs = _forward_chunk(
                model, x[idx], y[idx], z[idx], tile_int, tile_cls,
                terrain_z=tile_tz,
            )

            if accum_embs is None:
                accum_embs = np.zeros((n, embs.shape[1]), dtype=np.float64)

            accum_probs[idx] += probs
            accum_offs[idx]  += offs
            accum_embs[idx]  += embs
            count[idx]       += 1

            if done % 10 == 0 or done == total:
                print(f"[predictor:{version}]   tile {done}/{total}")

    uncovered = count == 0
    if uncovered.any():
        print(f"[predictor:{version}] WARNING: {uncovered.sum():,} points uncovered -- non-tree.")
        accum_probs[uncovered, 0] = 1.0
        count[uncovered]          = 1.0

    c = count[:, None]
    avg_probs = (accum_probs / c).astype(np.float32)
    avg_offs  = (accum_offs  / c).astype(np.float32)
    avg_embs  = (accum_embs  / c).astype(np.float32) if accum_embs is not None \
                else np.zeros((n, 1), dtype=np.float32)

    return avg_probs, avg_offs, avg_embs


# ---------------------------------------------------------------------------
# Model frame (units + local origin)
# ---------------------------------------------------------------------------

def _model_frame(cfg: dict, x, y, z, metres_per_unit: float, dtm: dict) -> tuple:
    """Return float32 x, y, z in the model's frame, the converted DTM kwargs and the
    model-frame units per metre.

    x/y are first shifted to a local origin in float64: casting absolute coordinates
    to float32 (e.g. eastings ~2.65e6 ft) quantises them to ~0.25 units — coarser than
    the 0.08 voxels. The model centres every tile anyway, so the shift changes nothing
    else.
    """
    f = float(metres_per_unit) if cfg.get('input_units') == 'm' else 1.0
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    ox = float(np.floor(x.min())) if len(x) else 0.0
    oy = float(np.floor(y.min())) if len(y) else 0.0
    xf = ((x - ox) * f).astype(np.float32)
    yf = ((y - oy) * f).astype(np.float32)
    zf = (np.asarray(z, dtype=np.float64) * f).astype(np.float32)

    dtm_out = dict(dtm)
    if dtm.get('dtm_grid') is not None:
        dtm_out['dtm_grid']    = (np.asarray(dtm['dtm_grid'], dtype=np.float64) * f).tolist()
        dtm_out['dtm_x_min']   = (dtm['dtm_x_min'] - ox) * f
        dtm_out['dtm_y_min']   = (dtm['dtm_y_min'] - oy) * f
        dtm_out['dtm_x_range'] = dtm['dtm_x_range'] * f
        dtm_out['dtm_y_range'] = dtm['dtm_y_range'] * f

    # model-frame units per metre: 1 for metric models, 1/metres_per_unit for raw ones
    units_per_m = 1.0 if cfg.get('input_units') == 'm' else 1.0 / float(metres_per_unit or 1.0)
    return xf, yf, zf, dtm_out, units_per_m


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None = None,
    classification: np.ndarray | None = None,
    version: str = 'metric',
    cache_key: str | None = None,
    dtm_grid: list | None = None,
    dtm_rows: int = 64,
    dtm_cols: int = 64,
    dtm_x_min: float = 0.0,
    dtm_y_min: float = 0.0,
    dtm_x_range: float = 1.0,
    dtm_y_range: float = 1.0,
    metres_per_unit: float = 1.0,
    return_probs: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Per-point semantic prediction.

    Args:
        x, y, z        : (N,) world coordinates in the file's units (float64 preferred)
        metres_per_unit: file units -> metres (0.3048006 for US survey feet)
        intensity      : float32 (N,) raw intensity  (required for v3, v4)
        classification : float32 (N,) ASPRS class    (required for v2, v4)
        version        : model id, see _MODEL_CONFIGS

    Returns:
        labels : int32 (N,) -- 0=non-tree, 101=tree
    """
    if version not in _MODEL_CONFIGS:
        raise ValueError(f"Unknown version '{version}'. Choose from {VALID_VERSIONS}.")

    cfg = _MODEL_CONFIGS[version]
    if cfg.get('role') == 'instance':   # see services/instance_nn.py
        raise ValueError(f"{cfg['filename']} only splits trees (Split trees: Instance NN); "
                         "run inference with a tree / non-tree model")
    if cfg['use_intensity'] and intensity is None:
        raise ValueError(f"version='{version}' requires intensity values")
    if cfg['use_classification'] and classification is None:
        raise ValueError(f"version='{version}' requires classification values")

    model = _get_model(version)

    dtm = dict(dtm_grid=dtm_grid, dtm_rows=dtm_rows, dtm_cols=dtm_cols, dtm_x_min=dtm_x_min,
               dtm_y_min=dtm_y_min, dtm_x_range=dtm_x_range, dtm_y_range=dtm_y_range)
    x32, y32, z32, dtm, _ = _model_frame(cfg, x, y, z, metres_per_unit, dtm)
    int_ = intensity.astype(np.float32)      if (intensity      is not None and cfg['use_intensity'])      else None
    cls_ = classification.astype(np.float32) if (classification is not None and cfg['use_classification']) else None

    extent_x = float(x32.max() - x32.min())
    extent_y = float(y32.max() - y32.min())
    print(f"[predictor:{version}] {len(x32):,} pts, {extent_x:.1f} x {extent_y:.1f} "
          f"({'m' if cfg.get('input_units') == 'm' else 'file units'})")

    terrain_z = _compute_terrain_z(x32, y32, z32, dtm['dtm_grid'], dtm['dtm_rows'], dtm['dtm_cols'],
                                   dtm['dtm_x_min'], dtm['dtm_y_min'], dtm['dtm_x_range'], dtm['dtm_y_range'])

    if cache_key and cache_key in _NN_CACHE:
        print(f"[predictor:{version}] Using cached NN outputs for semantic ...")
        probs, _, _ = _NN_CACHE[cache_key]
    else:
        if extent_x <= _MAX_DIRECT_M and extent_y <= _MAX_DIRECT_M:
            probs, _offs, _embs = _forward_chunk(model, x32, y32, z32, int_, cls_,
                                                  terrain_z=terrain_z)
        else:
            probs, _offs, _embs = _predict_with_tiling(model, x32, y32, z32, int_, cls_, version,
                                                        terrain_z=terrain_z)
        if cache_key:
            _NN_CACHE[cache_key] = (probs, _offs, _embs)
            print(f"[predictor:{version}] NN outputs cached (key={cache_key})")

    threshold = float(cfg.get('threshold', 0.5))   # per model, see _MODEL_CONFIGS
    point_labels = (probs[:, 1] >= threshold).astype(np.int32)
    point_labels[point_labels == 1] = 101  # 1=tree -> 101

    print(f"[predictor:{version}] Done. "
          f"Counts: {dict(zip(*np.unique(point_labels, return_counts=True)))}")
    if return_probs:   # P(tree) per point, for the threshold slider in the UI
        return point_labels, np.asarray(probs[:, 1], dtype=np.float32)
    return point_labels


def _cluster_instances(
    coords: np.ndarray,
    offsets: np.ndarray,
    embeddings: np.ndarray,
    bandwidth: float = 2.0,
    min_points: int = 100,
    embed_weight: float = 0.3,
    max_spread: float = 5.0,
) -> np.ndarray:
    """Mean-shift clustering on offset-shifted XY + scaled embeddings.

    Returns labels (1,2,... for trees; 0 = noise).
    """
    from sklearn.cluster import MeanShift, DBSCAN

    shifted  = coords[:, :2] + offsets[:, :2]
    features = np.hstack([shifted, embeddings * embed_weight])

    ms = MeanShift(bandwidth=bandwidth, bin_seeding=True, n_jobs=-1)
    ms.fit(features)
    raw_labels = ms.labels_

    labels      = np.zeros(len(coords), dtype=np.int32)
    instance_id = 0

    for cluster_id in np.unique(raw_labels):
        mask     = raw_labels == cluster_id
        mask_idx = np.where(mask)[0]

        db = DBSCAN(eps=max_spread, min_samples=1, algorithm='ball_tree').fit(
            coords[mask, :2]
        )
        comp_labels = db.labels_
        unique_comps, comp_counts = np.unique(
            comp_labels[comp_labels >= 0], return_counts=True
        )
        if len(unique_comps) == 0:
            continue

        keep = comp_labels == unique_comps[comp_counts.argmax()]
        if keep.sum() < min_points:
            continue

        instance_id += 1
        labels[mask_idx[keep]] = instance_id

    return labels


def predict_instances(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None = None,
    classification: np.ndarray | None = None,
    version: str = 'metric_old',
    bandwidth: float = 2.0,
    min_points: int = 100,
    embed_weight: float = 0.3,
    max_spread: float = 5.0,
    cache_key: str | None = None,
    dtm_grid: list | None = None,
    dtm_rows: int = 64,
    dtm_cols: int = 64,
    dtm_x_min: float = 0.0,
    dtm_y_min: float = 0.0,
    dtm_x_range: float = 1.0,
    dtm_y_range: float = 1.0,
    metres_per_unit: float = 1.0,
    threshold: float | None = None,
) -> np.ndarray:
    """Per-point instance segmentation using all three model heads.

    Args:
        x, y, z        : (N,) world coordinates in the file's units (float64 preferred)
        metres_per_unit: file units -> metres (0.3048006 for US survey feet)
        intensity      : float32 (N,) raw intensity (required for v3, v4)
        classification : float32 (N,) ASPRS class  (required for v2, v4)
        version        : a model with instance heads (see _MODEL_CONFIGS['instance_heads'])
        bandwidth      : mean-shift bandwidth in metres (converted to the model frame)
        min_points     : minimum cluster size to be kept as a tree
        embed_weight   : embedding vs XY weighting for clustering
        max_spread     : DBSCAN eps for spatial coherence in metres (converted)

    Returns:
        labels : int32 (N,) -- 0=non-tree, 201,202,...=tree instances
    """
    if version not in _MODEL_CONFIGS:
        raise ValueError(f"Unknown version '{version}'. Choose from {VALID_VERSIONS}.")

    cfg = _MODEL_CONFIGS[version]
    if cfg.get('role') == 'instance':   # see services/instance_nn.py
        raise ValueError(f"{cfg['filename']} only splits trees (Split trees: Instance NN); "
                         "run inference with a tree / non-tree model")
    if cfg['use_intensity'] and intensity is None:
        raise ValueError(f"version='{version}' requires intensity values")
    if cfg['use_classification'] and classification is None:
        raise ValueError(f"version='{version}' requires classification values")

    no_heads = (f"{cfg['label']} {cfg.get('tag', '')} ({cfg['filename']}) has no instance heads -- "
                "it only separates tree / non-tree. Use 'Segment Trees (CHM)' to split trees.")
    if not cfg.get('instance_heads', True):
        raise ValueError(no_heads)
    model = _get_model(version)
    if not _has_heads.get(version, True):
        raise ValueError(no_heads)

    dtm = dict(dtm_grid=dtm_grid, dtm_rows=dtm_rows, dtm_cols=dtm_cols, dtm_x_min=dtm_x_min,
               dtm_y_min=dtm_y_min, dtm_x_range=dtm_x_range, dtm_y_range=dtm_y_range)
    x32, y32, z32, dtm, units_per_m = _model_frame(cfg, x, y, z, metres_per_unit, dtm)
    int_ = intensity.astype(np.float32)      if (intensity      is not None and cfg['use_intensity'])      else None
    cls_ = classification.astype(np.float32) if (classification is not None and cfg['use_classification']) else None

    # bandwidth / max_spread arrive in metres -> model frame
    bandwidth  = bandwidth  * units_per_m
    max_spread = max_spread * units_per_m

    extent_x = float(x32.max() - x32.min())
    extent_y = float(y32.max() - y32.min())
    print(f"[predictor:{version}] {len(x32):,} pts, {extent_x:.1f} x {extent_y:.1f} "
          f"({'m' if cfg.get('input_units') == 'm' else 'file units'}) -- 3-head ...")

    terrain_z = _compute_terrain_z(x32, y32, z32, dtm['dtm_grid'], dtm['dtm_rows'], dtm['dtm_cols'],
                                   dtm['dtm_x_min'], dtm['dtm_y_min'], dtm['dtm_x_range'], dtm['dtm_y_range'])

    if cache_key and cache_key in _NN_CACHE:
        print(f"[predictor:{version}] Cache hit — skipping NN forward pass ...")
        pt_probs, pt_offs, pt_embs = _NN_CACHE[cache_key]
    else:
        if extent_x <= _MAX_DIRECT_M and extent_y <= _MAX_DIRECT_M:
            pt_probs, pt_offs, pt_embs = _forward_chunk(model, x32, y32, z32, int_, cls_,
                                                         terrain_z=terrain_z)
        else:
            pt_probs, pt_offs, pt_embs = _predict_with_tiling(
                model, x32, y32, z32, int_, cls_, version, terrain_z=terrain_z)
        if cache_key:
            _NN_CACHE[cache_key] = (pt_probs, pt_offs, pt_embs)
            print(f"[predictor:{version}] NN outputs cached (key={cache_key})")

    tree_mask = pt_probs[:, 1] >= float(threshold if threshold is not None else cfg.get('threshold', 0.5))
    n_tree    = int(tree_mask.sum())
    print(f"[predictor:{version}] {n_tree:,}/{len(x):,} tree pts -- clustering ...")

    output = np.zeros(len(x), dtype=np.int32)

    if n_tree > 0:
        # Cluster in the model frame: offsets are predicted in model-frame units
        xyz_tree = np.stack([x32, y32, z32], axis=1)[tree_mask]
        inst_labels = _cluster_instances(
            xyz_tree, pt_offs[tree_mask], pt_embs[tree_mask],
            bandwidth=bandwidth, min_points=min_points,
            embed_weight=embed_weight, max_spread=max_spread,
        )
        n_inst     = int(inst_labels.max()) if len(inst_labels) else 0
        n_assigned = int((inst_labels > 0).sum())
        print(f"[predictor:{version}] {n_inst} instances, {n_assigned:,} assigned")
        output[tree_mask] = np.where(inst_labels > 0, 200 + inst_labels, 0)

    return output

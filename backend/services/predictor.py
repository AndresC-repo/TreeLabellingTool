"""
Inference service for SegmentAnyTree models.

finetune     -- XYZ             in_channels=3  best_model.pth           (finetuned)
finetune_int -- XYZ + Intensity in_channels=4  best_model_int.pth       (finetuned)
scratch      -- XYZ             in_channels=3  best_model_scratch.pth   (trained from scratch)
scratch_int  -- XYZ + Intensity in_channels=4  best_model_scratch_int.pth (trained from scratch)
"""
from __future__ import annotations
import numpy as np
import torch
import spconv.pytorch as spconv
from spconv.pytorch import SparseConvTensor
from huggingface_hub import hf_hub_download
from services.segment_any_tree import SegmentAnyTree

_MODEL_REPO = "AndCarr/UrbanTreeDetector"
_VOXEL_SIZE = 0.08  # metres -- must match training (finetune_config.yaml: voxel_size: 0.08)

# Sliding-window inference constants
# The model was trained on small patches (~20-30 m diameter).
# When the input exceeds _MAX_DIRECT_M in X or Y we tile it into overlapping
# windows, run the model on each tile, and merge by averaging softmax scores.
_MAX_DIRECT_M = 150.0   # metres -- below this, run in one shot
_TILE_SIZE_M  = 120.0   # side length of each inference tile
_TILE_STEP_M  =  60.0   # step between tiles (50 % overlap)
_MIN_TILE_PTS =  20     # skip tiles with fewer points than this

_MODEL_CONFIGS: dict[str, dict] = {
    'finetune': {
        'filename':           'best_model.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'label':              'Finetune — XYZ',
    },
    'finetune_int': {
        'filename':           'best_model_int.pth',
        'in_channels':        4,
        'use_intensity':      True,
        'use_classification': False,
        'label':              'Finetune — XYZ + Intensity',
    },
    'scratch': {
        'filename':           'best_model_scratch.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'label':              'Scratch — XYZ',
    },
    'scratch_int': {
        'filename':           'best_model_scratch_int.pth',
        'in_channels':        4,
        'use_intensity':      True,
        'use_classification': False,
        'label':              'Scratch — XYZ + Intensity',
    },
}

_loaded: dict[str, SegmentAnyTree] = {}

# NN output cache: key = "session_id:patch_id:version"
# Stores (pt_probs, pt_offs, pt_embs) so Run Instance Segmentation
# can re-use the forward pass from Run Inference without hitting the NN again.
_NN_CACHE: dict[str, tuple] = {}
VALID_VERSIONS = tuple(_MODEL_CONFIGS.keys())


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _get_model(version: str) -> SegmentAnyTree:
    if version in _loaded:
        return _loaded[version]

    cfg = _MODEL_CONFIGS[version]
    print(f"[predictor] Downloading {cfg['filename']} ({cfg['label']}) ...")
    path = hf_hub_download(repo_id=_MODEL_REPO, filename=cfg['filename'])
    print(f"[predictor] Loading state dict from {path} ...")

    obj = torch.load(path, map_location='cpu', weights_only=False)

    if isinstance(obj, dict):
        state_dict = obj.get('model_state_dict') or obj.get('state_dict') or obj
    else:
        _loaded[version] = obj
        obj.eval()
        print(f"[predictor] {version.upper()} ready (full-model save).")
        return obj

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
    z_ground_ref: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Voxelize in metric units with HAG coordinate frame.

    Coordinate frame -- MUST match dataset.py __getitem__:
      XY : centroid-subtracted (per tile)
      Z  : height above ground (HAG) = z - z_ground_ref
           z_ground_ref defaults to percentile(z, 5) of this tile, but should
           be computed globally across the whole patch when tiling so all tiles
           share the same Z reference frame.

    Returns
    -------
    coords  : int32  (V, 4)  [batch=0, ix, iy, iz]
    feats   : float32 (V, C)
    inv_map : int64  (N,)
    """
    pts = np.stack([x, y, z], axis=1).astype(np.float32)

    xy_centroid = pts[:, :2].mean(axis=0)
    z_ground    = np.float32(z_ground_ref if z_ground_ref is not None
                             else np.percentile(pts[:, 2], 5))

    pts_c = pts.copy()
    pts_c[:, :2] -= xy_centroid  # XY centroid-relative
    pts_c[:, 2]  -= z_ground     # Z: HAG

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
    z_ground_ref: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Voxelise one chunk and run a single model forward pass.

    Returns per-original-point arrays:
      probs      : float32 (N, 2)
      offsets    : float32 (N, 3)
      embeddings : float32 (N, E)
    """
    coords, feats, inv_map = _voxelize_metric(x, y, z, intensity, classification,
                                               z_ground_ref=z_ground_ref)

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


def _predict_with_tiling(
    model: SegmentAnyTree,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    version: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sliding-window inference over large point clouds.

    Tiles XY into overlapping _TILE_SIZE_M windows with _TILE_STEP_M step.
    Returns (probs, offsets, embeddings) averaged over all covering tiles.
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

    # Compute z_ground globally so all tiles share the same HAG reference.
    # Per-tile estimation fails for corner tiles with few ground points
    # (e.g. large building footprint), shifting HAG and causing misclassification.
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

            probs, offs, embs = _forward_chunk(
                model, x[idx], y[idx], z[idx], tile_int, tile_cls,
                z_ground_ref=z_ground_global,
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
# Public API
# ---------------------------------------------------------------------------

def predict(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None = None,
    classification: np.ndarray | None = None,
    version: str = 'finetune',
    cache_key: str | None = None,
) -> np.ndarray:
    """Per-point semantic prediction.

    Args:
        x, y, z        : float32 (N,) world coordinates
        intensity      : float32 (N,) raw intensity  (required for v3, v4)
        classification : float32 (N,) ASPRS class    (required for v2, v4)
        version        : 'finetune' | 'finetune_int' | 'scratch' | 'scratch_int'

    Returns:
        labels : int32 (N,) -- 0=non-tree, 101=tree
    """
    if version not in _MODEL_CONFIGS:
        raise ValueError(f"Unknown version '{version}'. Choose from {VALID_VERSIONS}.")

    cfg = _MODEL_CONFIGS[version]
    if cfg['use_intensity'] and intensity is None:
        raise ValueError(f"version='{version}' requires intensity values")
    if cfg['use_classification'] and classification is None:
        raise ValueError(f"version='{version}' requires classification values")

    model = _get_model(version)

    x32  = x.astype(np.float32)
    y32  = y.astype(np.float32)
    z32  = z.astype(np.float32)
    int_ = intensity.astype(np.float32)      if (intensity      is not None and cfg['use_intensity'])      else None
    cls_ = classification.astype(np.float32) if (classification is not None and cfg['use_classification']) else None

    extent_x = float(x32.max() - x32.min())
    extent_y = float(y32.max() - y32.min())
    print(f"[predictor:{version}] {len(x32):,} pts, {extent_x:.1f}m x {extent_y:.1f}m")

    if cache_key and cache_key in _NN_CACHE:
        print(f"[predictor:{version}] Using cached NN outputs for semantic ...")
        probs, _, _ = _NN_CACHE[cache_key]
    else:
        if extent_x <= _MAX_DIRECT_M and extent_y <= _MAX_DIRECT_M:
            probs, _offs, _embs = _forward_chunk(model, x32, y32, z32, int_, cls_)
        else:
            probs, _offs, _embs = _predict_with_tiling(model, x32, y32, z32, int_, cls_, version)
        if cache_key:
            _NN_CACHE[cache_key] = (probs, _offs, _embs)
            print(f"[predictor:{version}] NN outputs cached (key={cache_key})")

    _TREE_THRESHOLD = 0.4   # lower = more recall; default argmax was effectively 0.5
    point_labels = (probs[:, 1] >= _TREE_THRESHOLD).astype(np.int32)
    point_labels[point_labels == 1] = 101  # 1=tree -> 101

    print(f"[predictor:{version}] Done. "
          f"Counts: {dict(zip(*np.unique(point_labels, return_counts=True)))}")
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
    version: str = 'finetune',
    bandwidth: float = 2.0,
    min_points: int = 100,
    embed_weight: float = 0.3,
    max_spread: float = 5.0,
    cache_key: str | None = None,
) -> np.ndarray:
    """Per-point instance segmentation using all three model heads.

    Args:
        x, y, z        : float32 (N,) world coordinates
        intensity      : float32 (N,) raw intensity (required for v3, v4)
        classification : float32 (N,) ASPRS class  (required for v2, v4)
        version        : 'finetune' | 'finetune_int' | 'scratch' | 'scratch_int'
        bandwidth      : mean-shift bandwidth in metres
        min_points     : minimum cluster size to be kept as a tree
        embed_weight   : embedding vs XY weighting for clustering
        max_spread     : DBSCAN eps for spatial coherence (metres)

    Returns:
        labels : int32 (N,) -- 0=non-tree, 201,202,...=tree instances
    """
    if version not in _MODEL_CONFIGS:
        raise ValueError(f"Unknown version '{version}'. Choose from {VALID_VERSIONS}.")

    cfg = _MODEL_CONFIGS[version]
    if cfg['use_intensity'] and intensity is None:
        raise ValueError(f"version='{version}' requires intensity values")
    if cfg['use_classification'] and classification is None:
        raise ValueError(f"version='{version}' requires classification values")

    model = _get_model(version)

    x32  = x.astype(np.float32)
    y32  = y.astype(np.float32)
    z32  = z.astype(np.float32)
    int_ = intensity.astype(np.float32)      if (intensity      is not None and cfg['use_intensity'])      else None
    cls_ = classification.astype(np.float32) if (classification is not None and cfg['use_classification']) else None

    extent_x = float(x32.max() - x32.min())
    extent_y = float(y32.max() - y32.min())
    print(f"[predictor:{version}] {len(x32):,} pts, {extent_x:.1f}m x {extent_y:.1f}m -- 3-head ...")

    if cache_key and cache_key in _NN_CACHE:
        print(f"[predictor:{version}] Cache hit — skipping NN forward pass ...")
        pt_probs, pt_offs, pt_embs = _NN_CACHE[cache_key]
    else:
        if extent_x <= _MAX_DIRECT_M and extent_y <= _MAX_DIRECT_M:
            pt_probs, pt_offs, pt_embs = _forward_chunk(model, x32, y32, z32, int_, cls_)
        else:
            pt_probs, pt_offs, pt_embs = _predict_with_tiling(
                model, x32, y32, z32, int_, cls_, version)
        if cache_key:
            _NN_CACHE[cache_key] = (pt_probs, pt_offs, pt_embs)
            print(f"[predictor:{version}] NN outputs cached (key={cache_key})")

    _TREE_THRESHOLD = 0.4
    tree_mask = pt_probs[:, 1] >= _TREE_THRESHOLD
    n_tree    = int(tree_mask.sum())
    print(f"[predictor:{version}] {n_tree:,}/{len(x):,} tree pts -- clustering ...")

    output = np.zeros(len(x), dtype=np.int32)

    if n_tree > 0:
        xyz_tree = np.stack([x, y, z], axis=1)[tree_mask]
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

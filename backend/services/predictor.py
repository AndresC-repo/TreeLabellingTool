"""
Inference service for SegmentAnyTree models.

v1 — XYZ                       in_channels=3  best_model.pth
v2 — XYZ + classification      in_channels=4  best_model_cls.pth
v3 — XYZ + intensity           in_channels=4  best_model_int.pth
v4 — XYZ + intensity + class   in_channels=5  best_model_int_cls.pth
"""
from __future__ import annotations
import numpy as np
import torch
import MinkowskiEngine as ME
from huggingface_hub import hf_hub_download
from services.segment_any_tree import SegmentAnyTree

_MODEL_REPO = "AndCarr/UrbanTreeDetector"
_VOXEL_SIZE = 0.1   # metres

_MODEL_CONFIGS: dict[str, dict] = {
    'v1': {
        'filename':           'best_model.pth',
        'in_channels':        3,
        'use_intensity':      False,
        'use_classification': False,
        'label':              'XYZ',
    },
    'v2': {
        'filename':           'best_model_cls.pth',
        'in_channels':        5,   # 3 (XYZ) + 2 (classification, 2-channel encoding)
        'use_intensity':      False,
        'use_classification': True,
        'label':              'XYZ + Classification',
    },
    'v3': {
        'filename':           'best_model_int.pth',
        'in_channels':        4,   # 3 (XYZ) + 1 (intensity)
        'use_intensity':      True,
        'use_classification': False,
        'label':              'XYZ + Intensity',
    },
    'v4': {
        'filename':           'best_model_int_cls.pth',
        'in_channels':        6,   # 3 (XYZ) + 1 (intensity) + 2 (classification)
        'use_intensity':      True,
        'use_classification': True,
        'label':              'XYZ + Intensity + Classification',
    },
}

_loaded: dict[str, SegmentAnyTree] = {}   # version → model singleton

VALID_VERSIONS = tuple(_MODEL_CONFIGS.keys())


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

    model = SegmentAnyTree(in_channels=cfg['in_channels'], num_classes=2, embedding_dim=5)

    # Flexible loading — mirrors the training script approach:
    # skip layers whose shapes don't match (e.g. first conv when in_channels differs).
    model_dict = model.state_dict()
    loaded = skipped_shape = skipped_missing = 0
    for key, value in state_dict.items():
        if key not in model_dict:
            skipped_missing += 1
            continue
        if model_dict[key].shape == value.shape:
            model_dict[key] = value
            loaded += 1
        elif (len(model_dict[key].shape) == 3 and len(value.shape) == 2):
            # 1×1 conv kernel stored as [in, out] → [1, in, out]
            model_dict[key] = value.unsqueeze(0)
            loaded += 1
        else:
            skipped_shape += 1
            print(f"[predictor] WARNING shape mismatch — skipping {key}: "
                  f"checkpoint {tuple(value.shape)} vs model {tuple(model_dict[key].shape)}")

    model.load_state_dict(model_dict, strict=False)

    if skipped_shape > 0:
        print(f"[predictor] WARNING: {skipped_shape} layer(s) skipped due to shape mismatch.")
        print(f"[predictor] This usually means the checkpoint was saved with different "
              f"in_channels than {cfg['in_channels']}.")
        print(f"[predictor] Upload the fine-tuned '{cfg['filename']}' weights to HuggingFace "
              f"to fix this.")
    print(f"[predictor] {version.upper()} loaded: {loaded} layers "
          f"(skipped shape={skipped_shape}, missing={skipped_missing}).")

    model.eval()
    _loaded[version] = model
    print(f"[predictor] {version.upper()} ({cfg['label']}) ready.")
    return model


def _voxelize(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Voxelise a point cloud and build normalised per-voxel features.

    Feature columns (always in this order if present):
      XYZ normalised                    (3 channels, always)
      intensity / 65535                 (1 channel, optional)
      is_ground   (class == 2)  float   (1 channel, optional)  ⎤ classification
      is_building (class == 6)  float   (1 channel, optional)  ⎦ = 2 channels total

    Returns
    -------
    coords   : int32   (V, 4)  [batch=0, ix, iy, iz]
    feats    : float32 (V, C)
    inv_map  : int64   (N,)
    """
    pts = np.stack([x, y, z], axis=1).astype(np.float64)

    centroid = pts.mean(axis=0)
    pts_norm = pts - centroid
    scale = np.linalg.norm(pts_norm, axis=1).max()
    if scale > 1e-6:
        pts_norm /= scale

    voxel_size_norm = _VOXEL_SIZE / (scale if scale > 1e-6 else 1.0)
    quantised = np.floor(pts_norm / voxel_size_norm).astype(np.int64)

    unique_coords, inv_map = np.unique(quantised, axis=0, return_inverse=True)
    V = len(unique_coords)

    # Build per-point feature matrix
    cols = [pts_norm.astype(np.float32)]
    if intensity is not None:
        # Intensity stored as uint16 in LAS (0–65535) → normalise to [0, 1]
        cols.append((intensity / 65535.0).reshape(-1, 1).astype(np.float32))
    if classification is not None:
        # 2 binary channels matching training (dataset.py collate_fn):
        #   ch0: is_ground   (ASPRS class == 2)
        #   ch1: is_building (ASPRS class == 6)
        cls = classification.astype(np.int32)
        is_ground    = (cls == 2).astype(np.float32).reshape(-1, 1)
        is_building  = (cls == 6).astype(np.float32).reshape(-1, 1)
        cols.append(is_ground)
        cols.append(is_building)

    all_feats = np.concatenate(cols, axis=1)   # (N, C)
    C = all_feats.shape[1]

    # Average per voxel using vectorised scatter-add
    feats  = np.zeros((V, C), dtype=np.float32)
    counts = np.zeros(V,      dtype=np.float32)
    np.add.at(feats,  inv_map, all_feats)
    np.add.at(counts, inv_map, 1.0)
    feats /= counts[:, None]

    coords = np.concatenate(
        [np.zeros((V, 1), dtype=np.int32), unique_coords.astype(np.int32)],
        axis=1,
    )
    return coords, feats, inv_map


def predict(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    intensity: np.ndarray | None = None,
    classification: np.ndarray | None = None,
    version: str = 'v1',
) -> np.ndarray:
    """
    Run per-point semantic prediction.

    Args:
        x, y, z        : float32 (N,) world coordinates
        intensity      : float32 (N,) raw intensity  (required for v3, v4)
        classification : float32 (N,) ASPRS class    (required for v2, v4)
        version        : 'v1' | 'v2' | 'v3' | 'v4'

    Returns:
        labels : int32 (N,) — 0=non-tree, 101=tree
    """
    if version not in _MODEL_CONFIGS:
        raise ValueError(f"Unknown version '{version}'. Choose from {VALID_VERSIONS}.")

    cfg = _MODEL_CONFIGS[version]
    if cfg['use_intensity'] and intensity is None:
        raise ValueError(f"version='{version}' requires intensity values")
    if cfg['use_classification'] and classification is None:
        raise ValueError(f"version='{version}' requires classification values")

    model = _get_model(version)

    print(f"[predictor:{version}] Voxelising {len(x):,} points ...")
    coords, feats, inv_map = _voxelize(
        x.astype(np.float64),
        y.astype(np.float64),
        z.astype(np.float64),
        intensity      if cfg['use_intensity']      else None,
        classification if cfg['use_classification'] else None,
    )
    print(f"[predictor:{version}] {len(coords):,} voxels → running inference ...")

    sparse_input = ME.SparseTensor(
        features    = torch.from_numpy(feats).float(),
        coordinates = torch.from_numpy(coords).int(),
    )

    with torch.no_grad():
        out = model(sparse_input)

    voxel_labels = out['semantic_logits'].argmax(dim=1).cpu().numpy()
    point_labels = voxel_labels[inv_map].astype(np.int32)

    # Remap: 1=tree → 101 (tool label convention), 0=non-tree stays 0
    point_labels[point_labels == 1] = 101

    print(f"[predictor:{version}] Done. "
          f"Counts: {dict(zip(*np.unique(point_labels, return_counts=True)))}")
    return point_labels

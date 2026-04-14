"""Download best_model.pth from HuggingFace and run per-point inference.

Uses the SegmentAnyTree MinkowskiEngine sparse-UNet architecture.
Input: XYZ point cloud → Output: per-point binary label (0=non-tree, 1=tree).
"""
from __future__ import annotations
import numpy as np
import torch
import MinkowskiEngine as ME
from huggingface_hub import hf_hub_download
from services.segment_any_tree import SegmentAnyTree

_MODEL_REPO = "AndCarr/UrbanTreeDetector"
_MODEL_FILE = "best_model.pth"
_VOXEL_SIZE = 0.1   # metres — matches training voxel resolution

_model = None   # singleton — loaded once, reused across requests


def _get_model() -> SegmentAnyTree:
    global _model
    if _model is not None:
        return _model

    print(f"[predictor] Downloading {_MODEL_FILE} from {_MODEL_REPO} ...")
    path = hf_hub_download(repo_id=_MODEL_REPO, filename=_MODEL_FILE)
    print(f"[predictor] Loading state dict from {path} ...")

    obj = torch.load(path, map_location="cpu", weights_only=False)

    # Unwrap checkpoint wrappers if present
    if isinstance(obj, dict):
        state_dict = (
            obj.get("model_state_dict")
            or obj.get("state_dict")
            or obj   # assume the dict IS the state dict
        )
    else:
        # Already a model object (unlikely but handle gracefully)
        _model = obj
        _model.eval()
        print("[predictor] Model ready (full-model save).")
        return _model

    model = SegmentAnyTree(in_channels=3, num_classes=2, embedding_dim=5)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    _model = model
    print("[predictor] SegmentAnyTree model ready.")
    return _model


def _voxelize(
    x: np.ndarray, y: np.ndarray, z: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Voxelise a point cloud and normalise features.

    Returns
    -------
    coords   : int32 (V, 4) — [batch=0, ix, iy, iz]
    feats    : float32 (V, 3) — normalised XYZ features per voxel
    inv_map  : int64 (N,) — maps each original point → its voxel index
    """
    pts = np.stack([x, y, z], axis=1).astype(np.float64)  # (N, 3)

    # Normalise: centre then scale to unit sphere
    centroid = pts.mean(axis=0)
    pts_norm = pts - centroid
    scale = np.linalg.norm(pts_norm, axis=1).max()
    if scale > 1e-6:
        pts_norm /= scale

    # Quantise to voxel grid (use normalised coords so voxel_size is scale-invariant)
    voxel_size_norm = _VOXEL_SIZE / (scale if scale > 1e-6 else 1.0)
    quantised = np.floor(pts_norm / voxel_size_norm).astype(np.int64)  # (N, 3)

    # Unique voxels and inverse mapping
    unique_coords, inv_map = np.unique(quantised, axis=0, return_inverse=True)

    # Average normalised XYZ features per voxel
    V = len(unique_coords)
    feats = np.zeros((V, 3), dtype=np.float32)
    counts = np.zeros(V, dtype=np.int32)
    for i, vi in enumerate(inv_map):
        feats[vi] += pts_norm[i].astype(np.float32)
        counts[vi] += 1
    feats /= counts[:, None].astype(np.float32)

    # Build ME-compatible coords: prepend batch index = 0
    coords = np.concatenate(
        [np.zeros((V, 1), dtype=np.int32), unique_coords.astype(np.int32)],
        axis=1,
    )  # (V, 4)

    return coords, feats, inv_map


def predict(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """
    Run per-point semantic prediction on a patch.

    Args:
        x, y, z: float32 (N,) world XYZ coordinates

    Returns:
        labels: int32 (N,) predicted class per point (0=non-tree, 1=tree)
    """
    model = _get_model()

    print(f"[predictor] Voxelising {len(x):,} points (voxel_size={_VOXEL_SIZE} m)...")
    coords, feats, inv_map = _voxelize(
        x.astype(np.float64),
        y.astype(np.float64),
        z.astype(np.float64),
    )
    print(f"[predictor] {len(coords):,} voxels → running inference...")

    coords_t = torch.from_numpy(coords).int()
    feats_t  = torch.from_numpy(feats).float()

    sparse_input = ME.SparseTensor(features=feats_t, coordinates=coords_t)

    with torch.no_grad():
        out = model(sparse_input)

    # out['semantic_logits'] shape: (V, num_classes)
    voxel_labels = out["semantic_logits"].argmax(dim=1).cpu().numpy()  # (V,)

    # Map voxel predictions back to original points
    point_labels = voxel_labels[inv_map].astype(np.int32)  # (N,)
    print(f"[predictor] Done. Label counts: {dict(zip(*np.unique(point_labels, return_counts=True)))}")
    return point_labels

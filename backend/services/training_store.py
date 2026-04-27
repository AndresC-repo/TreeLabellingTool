from __future__ import annotations
import json
import uuid
from pathlib import Path
import numpy as np

from config import STORAGE_DIR

TRAINING_DIR = STORAGE_DIR / "training"


def _ensure_dir():
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)


def _index_path() -> Path:
    return TRAINING_DIR / "index.json"


def _load_index() -> list[dict]:
    p = _index_path()
    return json.loads(p.read_text()) if p.exists() else []


def _save_index(entries: list[dict]):
    _index_path().write_text(json.dumps(entries, indent=2))


def save_training_example(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    original_cls: np.ndarray,
    semantic_labels: np.ndarray,    # 0/101 from inference
    gt_instance_labels: np.ndarray, # 201+ corrected by user
    patch_id: str,
) -> str:
    """Persist a training example and return its ID.

    Re-saving the same patch_id replaces the previous entry so the user can
    keep correcting and re-saving without accumulating stale examples.
    """
    _ensure_dir()
    # Delete old files for this patch if it was saved before
    old_entries = [e for e in _load_index() if e.get("patch_id") == patch_id]
    for old in old_entries:
        for suffix in ("x", "y", "z", "cls", "sem", "gt"):
            p = TRAINING_DIR / f"{old['id']}_{suffix}.npy"
            if p.exists():
                p.unlink()

    entries = [e for e in _load_index() if e.get("patch_id") != patch_id]
    eid = str(uuid.uuid4())[:8]

    for name, arr in [("x", x), ("y", y), ("z", z),
                      ("cls", original_cls),
                      ("sem", semantic_labels),
                      ("gt",  gt_instance_labels)]:
        np.save(str(TRAINING_DIR / f"{eid}_{name}.npy"), arr)

    entries.append({
        "id":       eid,
        "patch_id": patch_id,
        "n_points": int(len(x)),
        "n_trees":  int((gt_instance_labels >= 201).sum()),
    })
    _save_index(entries)
    return eid


def load_all_training_examples() -> list[dict]:
    """
    Returns a list of dicts, each containing:
      id, patch_id, n_points, n_trees,
      x, y, z, original_cls, semantic_labels, gt_instance_labels
    """
    _ensure_dir()
    examples = []
    for entry in _load_index():
        eid = entry["id"]
        try:
            examples.append({
                **entry,
                "x":                  np.load(str(TRAINING_DIR / f"{eid}_x.npy")),
                "y":                  np.load(str(TRAINING_DIR / f"{eid}_y.npy")),
                "z":                  np.load(str(TRAINING_DIR / f"{eid}_z.npy")),
                "original_cls":       np.load(str(TRAINING_DIR / f"{eid}_cls.npy")),
                "semantic_labels":    np.load(str(TRAINING_DIR / f"{eid}_sem.npy")),
                "gt_instance_labels": np.load(str(TRAINING_DIR / f"{eid}_gt.npy")),
            })
        except FileNotFoundError:
            pass  # stale index entry — skip silently
    return examples


def count_training_examples() -> int:
    return len(_load_index())

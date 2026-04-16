from __future__ import annotations
from typing import Optional
import numpy as np

# In-memory store: { patch_id: { "labels": np.ndarray(int32), "used": set[int] } }
_state: dict = {}
# Per-session patch counter
_patch_counters: dict[str, int] = {}
_patch_number_map: dict[str, int] = {}


def register_patch(session_id: str, patch_id: str) -> int:
    """Assign the next sequential patch number for a session. Returns the number."""
    n = _patch_counters.get(session_id, 0) + 1
    _patch_counters[session_id] = n
    _patch_number_map[patch_id] = n
    return n


def get_patch_number(patch_id: str) -> int:
    return _patch_number_map.get(patch_id, 0)


def init_patch(
    patch_id: str,
    original_classification: np.ndarray,
    current_labels: "np.ndarray | None" = None,
) -> None:
    """Initialize label state for a patch.

    original_classification: the raw ASPRS classification from the LAS file —
        used as the immutable reference for protect-classes filtering.
    current_labels: the labels to start with (e.g. previously applied labels
        loaded from a saved file). Defaults to original_classification.
    """
    orig = original_classification.astype(np.int32)
    labels = current_labels.astype(np.int32) if current_labels is not None else orig.copy()
    _state[patch_id] = {
        "labels":   labels,
        "orig_cls": orig,          # immutable reference — used for protect-classes filtering
        "used": {int(v) for v in np.unique(labels) if v != 0},
    }


def get_next_label(patch_id: str) -> int:
    """Return the next label to suggest (max used + 1, or 101 if no labels yet)."""
    state = _state.get(patch_id)
    if not state or not state["used"]:
        return 101
    return max(state["used"]) + 1


_PROTECTED_CLASSES = frozenset({2, 6})   # ASPRS ground, building


def apply_label(
    patch_id: str,
    indices: list[int],
    label_value: int,
    protect_classes: bool = True,
) -> dict:
    """Apply label_value to the given point indices. Returns label statistics.

    When protect_classes is True, points whose *original* ASPRS classification
    is 2 (ground) or 6 (building) are silently skipped.
    """
    state = _state[patch_id]
    label_len = len(state["labels"])
    if indices and max(indices) >= label_len:
        raise IndexError(
            f"Index {max(indices)} out of range for patch with {label_len} points"
        )

    if protect_classes and "orig_cls" in state:
        orig = state["orig_cls"]
        indices = [i for i in indices if orig[i] not in _PROTECTED_CLASSES]

    state["labels"][indices] = label_value
    if label_value != 0:
        state["used"].add(label_value)
    unique, counts = np.unique(state["labels"], return_counts=True)
    return {
        "label_value": label_value,
        "points_labeled": len(indices),
        "label_stats": {str(int(u)): int(c) for u, c in zip(unique, counts)},
    }


def apply_labels_bulk(patch_id: str, labels: np.ndarray) -> dict:
    """Replace the entire label array with the provided one-per-point labels."""
    state = _state.get(patch_id)
    if state is None:
        raise KeyError(f"Patch {patch_id} not initialized")
    if len(labels) != len(state["labels"]):
        raise ValueError(
            f"Label count mismatch: got {len(labels)}, expected {len(state['labels'])}"
        )
    state["labels"] = labels.astype(np.int32)
    state["used"] = {int(v) for v in np.unique(labels) if v != 0}
    unique, counts = np.unique(state["labels"], return_counts=True)
    return {
        "points_labeled": int(len(labels)),
        "label_stats": {str(int(u)): int(c) for u, c in zip(unique, counts)},
    }


def get_labels(patch_id: str) -> Optional[np.ndarray]:
    """Return the label array for a patch, or None if not initialized."""
    state = _state.get(patch_id)
    return state["labels"] if state else None


def get_used_labels(patch_id: str) -> set[int]:
    """Return the set of non-zero labels used for a patch."""
    state = _state.get(patch_id)
    return state["used"] if state else set()

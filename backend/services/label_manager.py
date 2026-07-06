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
        "labels":     labels,
        "orig_cls":   orig,
        "used":       {int(v) for v in np.unique(labels) if v != 0},
        "undo_stack": [],
    }


def get_next_label(patch_id: str) -> int:
    """Return the next label to suggest (max used + 1, or 101 if no labels yet)."""
    state = _state.get(patch_id)
    if not state or not state["used"]:
        return 101
    return max(state["used"]) + 1


_PROTECTED_CLASSES = frozenset({2, 6})   # ASPRS ground, building
_UNDO_LIMIT = 20


def _push_undo(state: dict, entry: dict) -> None:
    state["undo_stack"].append(entry)
    if len(state["undo_stack"]) > _UNDO_LIMIT:
        state["undo_stack"].pop(0)


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
        orig   = state["orig_cls"]
        labels = state["labels"]
        indices = [
            i for i in indices
            if orig[i] not in _PROTECTED_CLASSES and labels[i] not in _PROTECTED_CLASSES
        ]

    if indices:
        prev = state["labels"][list(indices)].copy()
        _push_undo(state, {"type": "selective", "indices": list(indices), "prev": prev})

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
    """Replace the entire label array with the provided one-per-point labels.

    Points whose original ASPRS classification is 2 (ground) or 6 (building)
    are always preserved — their original class is kept regardless of what the
    incoming labels array says.
    """
    state = _state.get(patch_id)
    if state is None:
        raise KeyError(f"Patch {patch_id} not initialized")
    if len(labels) != len(state["labels"]):
        raise ValueError(
            f"Label count mismatch: got {len(labels)}, expected {len(state['labels'])}"
        )
    _push_undo(state, {"type": "full", "prev": state["labels"].copy()})
    new_labels = labels.astype(np.int32)
    if "orig_cls" in state:
        orig = state["orig_cls"]
        for cls in _PROTECTED_CLASSES:
            mask = orig == cls
            new_labels[mask] = cls
    state["labels"] = new_labels
    state["used"] = {int(v) for v in np.unique(labels) if v != 0}
    unique, counts = np.unique(state["labels"], return_counts=True)
    return {
        "points_labeled": int(len(labels)),
        "label_stats": {str(int(u)): int(c) for u, c in zip(unique, counts)},
    }


def undo_last(patch_id: str) -> "dict | None":
    """Pop the last operation from the undo stack and restore previous labels.

    Returns a dict describing what was restored, or None if the stack is empty.
    For selective undos: { full_reload: False, indices: [int], label_values: [int] }
    For full undos:      { full_reload: True,  indices: [],    label_values: [int] }
    """
    state = _state.get(patch_id)
    if not state or not state["undo_stack"]:
        return None
    entry = state["undo_stack"].pop()
    if entry["type"] == "selective":
        idx = entry["indices"]
        prev = entry["prev"]
        state["labels"][idx] = prev
        state["used"] = {int(v) for v in np.unique(state["labels"]) if v != 0}
        return {"full_reload": False, "indices": idx, "label_values": prev.tolist()}
    else:  # "full"
        prev = entry["prev"]
        state["labels"] = prev
        state["used"] = {int(v) for v in np.unique(prev) if v != 0}
        return {"full_reload": True, "indices": [], "label_values": prev.tolist()}


def get_labels(patch_id: str) -> Optional[np.ndarray]:
    """Return the label array for a patch, or None if not initialized."""
    state = _state.get(patch_id)
    return state["labels"] if state else None


def get_used_labels(patch_id: str) -> set[int]:
    """Return the set of non-zero labels used for a patch."""
    state = _state.get(patch_id)
    return state["used"] if state else set()

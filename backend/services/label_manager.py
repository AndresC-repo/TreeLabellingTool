from __future__ import annotations
from typing import Optional
import numpy as np

# In-memory store: { patch_id: { "labels": np.ndarray(int32), "used": set[int] } }
_state: dict = {}
# Per-session patch counter
_patch_counters: dict[str, int] = {}
_patch_number_map: dict[str, int] = {}


def register_patch(session_id: str, patch_id: str, start_after: int = 0) -> int:
    """Assign the next sequential patch number for a session. Returns the number.

    start_after: highest number already used on disk, so numbering continues
    correctly after a backend restart (the in-memory counter starts at 0).
    """
    n = max(_patch_counters.get(session_id, 0), start_after) + 1
    _patch_counters[session_id] = n
    _patch_number_map[patch_id] = n
    return n


def forget_session(session_id: str, patch_ids: list[str]) -> None:
    """Drop all in-memory label state for a deleted session."""
    _patch_counters.pop(session_id, None)
    for pid in patch_ids:
        _state.pop(pid, None)
        _patch_number_map.pop(pid, None)


def forget_patch(patch_id: str) -> None:
    _state.pop(patch_id, None)
    _patch_number_map.pop(patch_id, None)


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
        "redo_stack": [],
    }


def get_next_label(patch_id: str) -> int:
    """Return the next label to suggest (max used + 1, or 101 if no labels yet)."""
    state = _state.get(patch_id)
    if not state or not state["used"]:
        return 101
    return max(state["used"]) + 1


_PROTECTED_CLASSES = frozenset({2, 6})   # ASPRS ground, building

# History: up to _UNDO_LIMIT steps per patch, but never more than _HISTORY_BYTES of
# saved labels (a "full" step stores a copy of every point's label — 4 MB per million
# points — so on big patches the byte budget, not the step count, is the limit).
_UNDO_LIMIT = 200
_HISTORY_BYTES = 256 * 1024 ** 2


def _entry_bytes(entry: dict) -> int:
    n = entry["prev"].nbytes
    if entry["type"] == "selective":
        n += len(entry["indices"]) * 8
    return n


def _trim(stack: list) -> None:
    while len(stack) > _UNDO_LIMIT:
        stack.pop(0)
    while len(stack) > 1 and sum(_entry_bytes(e) for e in stack) > _HISTORY_BYTES:
        stack.pop(0)


def _push_undo(state: dict, entry: dict) -> None:
    """Record a new user operation. A new operation invalidates anything to redo."""
    state["undo_stack"].append(entry)
    state.setdefault("redo_stack", []).clear()
    _trim(state["undo_stack"])


def history_depth(patch_id: str) -> dict:
    state = _state.get(patch_id)
    if not state:
        return {"undo_depth": 0, "redo_depth": 0}
    return {"undo_depth": len(state["undo_stack"]), "redo_depth": len(state.get("redo_stack", []))}


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


def _restore(state: dict, entry: dict) -> tuple[dict, dict]:
    """Apply a history entry; return (inverse entry for the other stack, response)."""
    if entry["type"] == "selective":
        idx = entry["indices"]
        inverse = {"type": "selective", "indices": idx, "prev": state["labels"][idx].copy()}
        state["labels"][idx] = entry["prev"]
        state["used"] = {int(v) for v in np.unique(state["labels"]) if v != 0}
        return inverse, {"full_reload": False, "indices": idx, "label_values": entry["prev"].tolist()}
    inverse = {"type": "full", "prev": state["labels"].copy()}
    state["labels"] = entry["prev"].copy()
    state["used"] = {int(v) for v in np.unique(state["labels"]) if v != 0}
    return inverse, {"full_reload": True, "indices": [], "label_values": state["labels"].tolist()}


def undo_last(patch_id: str) -> "dict | None":
    """Undo the last operation (it moves to the redo stack).

    Returns a dict describing what was restored, or None if there is nothing to undo.
    For selective undos: { full_reload: False, indices: [int], label_values: [int] }
    For full undos:      { full_reload: True,  indices: [],    label_values: [int] }
    """
    state = _state.get(patch_id)
    if not state or not state["undo_stack"]:
        return None
    inverse, response = _restore(state, state["undo_stack"].pop())
    state.setdefault("redo_stack", []).append(inverse)
    _trim(state["redo_stack"])
    return response


def redo_last(patch_id: str) -> "dict | None":
    """Re-apply the last undone operation (it moves back to the undo stack)."""
    state = _state.get(patch_id)
    if not state or not state.get("redo_stack"):
        return None
    inverse, response = _restore(state, state["redo_stack"].pop())
    state["undo_stack"].append(inverse)
    _trim(state["undo_stack"])
    return response


def get_labels(patch_id: str) -> Optional[np.ndarray]:
    """Return the label array for a patch, or None if not initialized."""
    state = _state.get(patch_id)
    return state["labels"] if state else None


def get_used_labels(patch_id: str) -> set[int]:
    """Return the set of non-zero labels used for a patch."""
    state = _state.get(patch_id)
    return state["used"] if state else set()

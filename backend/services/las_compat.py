"""Small helpers so every LAS/LAZ flavour can be cut into plain .las files."""
from __future__ import annotations
import copy


def _is_copc(vlr) -> bool:
    return getattr(vlr, "user_id", "").strip("\x00") == "copc"


def plain_header(header):
    """Copy of `header` that can be written as an ordinary .las file.

    Cloud-optimised (COPC) LAZ files carry 'copc' records that describe their own
    octree layout; laspy refuses to write them, and they would be wrong for a subset of
    the points anyway. Everything else (CRS, extra dimensions, scales, offsets) is kept."""
    h = copy.deepcopy(header)
    h.vlrs = type(h.vlrs)([v for v in h.vlrs if not _is_copc(v)])
    if getattr(h, "evlrs", None):
        kept = [v for v in h.evlrs if not _is_copc(v)]
        h.evlrs = type(h.evlrs)(kept) if kept else None
    return h

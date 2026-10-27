"""Dataset registry: which source tiles and patches have been labelled.

Stored as JSON next to the training labels (DATASET_DIR, normally the NN repo's
`data/` folder mounted into the container), so it survives Docker rebuilds and lives
with the files it describes:

    <DATASET_DIR>/labels/*.las              exported training patches
    <DATASET_DIR>/labelling_registry.json   this registry

Two record types:
  sources[<original file name>]  one per USGS tile / uploaded file
  patches[<key>]                 one per cut patch ("<source>#p<n>"), plus files found
                                 in the labels folder that the tool didn't write
                                 ("file:<name>", origin "folder")
"""
from __future__ import annotations
import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np
import laspy

import config

SOURCE_STATUSES = ["to do", "in progress", "done", "skipped"]
PATCH_STATUSES = ["in progress", "labelled", "needs fix", "reviewed", "excluded"]

_lock = threading.RLock()
_EMPTY = {"version": 1, "sources": {}, "patches": {}}


# ── Locations ─────────────────────────────────────────────────────────────────

def dataset_root() -> tuple[Path, bool]:
    """(folder, connected). Falls back to the Docker volume if the mount is missing."""
    d = Path(config.DATASET_DIR)
    if d.is_dir() and os.access(d, os.W_OK):
        return d, True
    fb = config.STORAGE_DIR / "dataset"
    fb.mkdir(parents=True, exist_ok=True)
    return fb, False


def labels_dir() -> Path:
    p = dataset_root()[0] / "labels"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _registry_path() -> Path:
    return dataset_root()[0] / "labelling_registry.json"


def _load() -> dict:
    p = _registry_path()
    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    for k, v in _EMPTY.items():
        data.setdefault(k, {} if isinstance(v, dict) else v)
    return data


def _save(data: dict) -> None:
    p = _registry_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(p)


def _now() -> float:
    return round(time.time(), 1)


# ── Places & names ────────────────────────────────────────────────────────────

_USGS_STATE = re.compile(r"USGS_LPC_([A-Z]{2})_")


def guess_state(name: str) -> str:
    """State code from a USGS name or the prefixes used so far (NY_, G_ = Gainesville FL)."""
    m = _USGS_STATE.search(name)
    if m:
        return m.group(1)
    low = name.lower()
    if low.startswith("ny_"):
        return "NY"
    if low.startswith(("az_",)):
        return "AZ"
    if low.startswith(("g_", "fl_")):
        return "FL"
    return ""


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "", s.replace(" ", "-")) if s else ""


def export_name(source: str, patch_number: int, trees: int, city: str = "", state: str = "",
                labeller: str = "") -> str:
    """<City or state>_<source tile>_p<n>[_<labeller>]_t<trees>.las"""
    stem = re.sub(r"[^\w\-]+", "_", Path(source).stem).strip("_") or "patch"
    place = _slug(city) or _slug(state)
    prefix = f"{place}_" if place and not stem.lower().startswith(place.lower() + "_") else ""
    who = f"_{_slug(labeller)}" if _slug(labeller) else ""
    return f"{prefix}{stem}_p{patch_number}{who}_t{trees}.las"


def session_source(session_id: str) -> str:
    """Original file name of an uploaded session (the source tile)."""
    from services.las_reader import get_session_dir
    try:
        meta = json.loads((get_session_dir(session_id) / "meta.json").read_text())
        return meta.get("source") or meta.get("filename") or session_id
    except (OSError, ValueError):
        return session_id


def count_trees(labels: np.ndarray) -> int:
    labels = np.asarray(labels)
    return int(np.unique(labels[labels >= 100]).size)


# ── Sources ───────────────────────────────────────────────────────────────────

def upsert_source(name: str, **info) -> dict:
    with _lock:
        data = _load()
        src = data["sources"].get(name)
        if src is None:
            src = {
                "name": name, "city": "", "state": guess_state(name), "status": "to do",
                "notes": "", "added": _now(), "max_patch_number": 0,
            }
            data["sources"][name] = src
        src.update({k: v for k, v in info.items() if v is not None})
        src["last_opened"] = _now()
        if src.get("status") == "to do":
            src["status"] = "in progress"
        _save(data)
        return dict(src)


def get_source(name: str) -> dict | None:
    with _lock:
        s = _load()["sources"].get(name)
        return dict(s) if s else None


def next_patch_number(name: str, floor: int) -> int:
    """Patch numbers continue across re-uploads of the same tile, so names never repeat."""
    with _lock:
        data = _load()
        src = data["sources"].get(name)
        if src is None:
            src = {"name": name, "city": "", "state": guess_state(name), "status": "in progress",
                   "notes": "", "added": _now(), "max_patch_number": 0}
            data["sources"][name] = src
        n = max(int(src.get("max_patch_number", 0)), int(floor)) + 1
        src["max_patch_number"] = n
        _save(data)
        return n


def update_source(name: str, fields: dict) -> dict:
    allowed = {"city", "state", "status", "notes"}
    with _lock:
        data = _load()
        src = data["sources"].get(name)
        if src is None:
            raise KeyError(name)
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "status" and v not in SOURCE_STATUSES:
                raise ValueError(f"status must be one of {SOURCE_STATUSES}")
            src[k] = str(v)
        _save(data)
        return dict(src)


# ── Patches ───────────────────────────────────────────────────────────────────

def patch_key(source: str, patch_number: int) -> str:
    return f"{source}#p{patch_number}"


def record_patch(source: str, patch_number: int, session_id: str, patch_id: str, points: int) -> None:
    with _lock:
        data = _load()
        key = patch_key(source, patch_number)
        p = data["patches"].setdefault(key, {
            "key": key, "source": source, "patch_number": patch_number, "origin": "tool",
            "status": "in progress", "notes": "", "trees": 0, "file": None, "created": _now(),
            "labeller": config.LABELLER,
        })
        p.update({"session_id": session_id, "patch_id": patch_id, "points": int(points)})
        _save(data)


def find_patch(session_id: str, patch_id: str) -> dict | None:
    with _lock:
        for p in _load()["patches"].values():
            if p.get("patch_id") == patch_id and p.get("session_id") == session_id:
                return dict(p)
    return None


def file_owner(file_name: str) -> str | None:
    """Registry key of the patch that wrote this file (or the folder entry for it)."""
    with _lock:
        for k, p in _load()["patches"].items():
            if p.get("file") == file_name:
                return k
    return None


def record_export(key: str, file_name: str, trees: int, units: str | None) -> dict:
    """Remember the exported file; delete the patch's previous file if the name changed."""
    with _lock:
        data = _load()
        p = data["patches"][key]
        old = p.get("file")
        if old and old != file_name:
            try:
                (labels_dir() / old).unlink(missing_ok=True)
            except OSError:
                pass
        # drop a folder-scan entry for the same file name, now owned by this patch
        if key != f"file:{file_name}":
            data["patches"].pop(f"file:{file_name}", None)
        p.update({"file": file_name, "trees": int(trees), "exported_at": _now(), "units": units})
        if not p.get("labeller") and config.LABELLER:
            p["labeller"] = config.LABELLER
        if p.get("status") in ("in progress", "excluded", None):
            p["status"] = "labelled"
        src = data["sources"].get(p["source"])
        if src and src.get("status") == "to do":
            src["status"] = "in progress"
        _save(data)
        return dict(p)


def get_patch(key: str) -> dict | None:
    with _lock:
        p = _load()["patches"].get(key)
        return dict(p) if p else None


def link_patch(key: str, session_id: str, patch_id: str) -> None:
    """A saved file was opened again in the tool: point its entry at the new patch."""
    with _lock:
        data = _load()
        p = data["patches"][key]
        p.update({"session_id": session_id, "patch_id": patch_id})
        _save(data)


_TREES_SUFFIX = re.compile(r"_t\d+(?=\.la[sz]$)", re.IGNORECASE)


def default_name(rec: dict, trees: int) -> str:
    """Name used when saving: the automatic <place>_<tile>_p<n>_t<trees>.las, unless the
    file was renamed by hand or came from the folder — then its own name is kept with
    only the _t<trees> part updated."""
    f = rec.get("file")
    if f and (rec.get("custom_name") or not rec.get("source") or rec.get("origin") == "folder"):
        return _TREES_SUFFIX.sub(f"_t{trees}", f)
    src = get_source(rec.get("source") or "") or {}
    return export_name(rec.get("source") or "patch", rec.get("patch_number") or 1, trees,
                       src.get("city", ""), src.get("state", ""),
                       rec.get("labeller") or config.LABELLER)


def clean_file_name(name: str, like: str = ".las") -> str:
    name = re.sub(r"[^\w\-.]", "_", (name or "").strip()).strip("._")
    if not name:
        raise ValueError("Empty file name")
    if not name.lower().endswith((".las", ".laz")):
        name += Path(like).suffix.lower() or ".las"
    return name


def rename_file(key: str, new_name: str) -> dict:
    """Rename a saved file in the labels folder (the real file on disk) and its entry."""
    with _lock:
        data = _load()
        p = data["patches"].get(key)
        if p is None:
            raise KeyError(key)
        old = p.get("file")
        if not old:
            raise ValueError("This patch has no saved file yet")
        new = clean_file_name(new_name, old)
        if new == old:
            return dict(p)
        folder = labels_dir()
        src_path, dest = folder / old, folder / new
        if not src_path.exists():
            raise FileNotFoundError(old)
        # Windows folders ignore case: "a.las" -> "A.las" is the same file, not a clash
        if dest.exists() and new.lower() != old.lower():
            raise FileExistsError(new)
        if any(q.get("file") == new for k, q in data["patches"].items() if k != key):
            raise FileExistsError(new)
        src_path.rename(dest)
        p["file"] = new
        p["custom_name"] = True
        if key.startswith("file:"):
            del data["patches"][key]
            key = f"file:{new}"
            p["key"] = key
            data["patches"][key] = p
        _save(data)
        return dict(p)


def forget_patch(session_id: str, patch_id: str) -> None:
    """Patch deleted in the tool: drop it unless it was exported (the file still counts)."""
    with _lock:
        data = _load()
        for k, p in list(data["patches"].items()):
            if p.get("patch_id") == patch_id and p.get("session_id") == session_id:
                if p.get("file"):
                    p.pop("session_id", None); p.pop("patch_id", None)
                else:
                    del data["patches"][k]
        _save(data)


def forget_session(session_id: str) -> None:
    with _lock:
        data = _load()
        for k, p in list(data["patches"].items()):
            if p.get("session_id") == session_id:
                if p.get("file"):
                    p.pop("session_id", None); p.pop("patch_id", None)
                else:
                    del data["patches"][k]
        _save(data)


def update_patch(key: str, fields: dict) -> dict:
    allowed = {"status", "notes", "labeller"}
    with _lock:
        data = _load()
        p = data["patches"].get(key)
        if p is None:
            raise KeyError(key)
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "status" and v not in PATCH_STATUSES:
                raise ValueError(f"status must be one of {PATCH_STATUSES}")
            if k == "labeller":
                v = _slug(str(v))[:16]
            p[k] = str(v)
        _save(data)
        return dict(p)


# ── Labels folder scan ────────────────────────────────────────────────────────

def _file_trees(path: Path) -> tuple[int, int]:
    las = laspy.read(str(path))
    if "label" in las.point_format.extra_dimension_names:
        lab = np.asarray(las.label)
        if (lab >= 100).any():
            return count_trees(lab), len(las.points)
    return count_trees(np.asarray(las.classification)), len(las.points)


def scan_labels_folder() -> dict:
    """Add files in the labels folder that the registry doesn't know yet; refresh
    tree counts of folder entries whose file changed; flag missing files."""
    folder = labels_dir()
    added = updated = 0
    with _lock:
        data = _load()
        owned = {p.get("file"): k for k, p in data["patches"].items() if p.get("file")}
        present = set()
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in (".las", ".laz") or not f.is_file():
                continue
            present.add(f.name)
            st = f.stat()
            sig = [st.st_size, round(st.st_mtime, 1)]
            key = owned.get(f.name) or f"file:{f.name}"
            p = data["patches"].get(key)
            if p is not None and p.get("file_sig") == sig:
                continue
            try:
                trees, points = _file_trees(f)
            except Exception:
                trees, points = -1, 0
            if p is None:
                data["patches"][key] = {
                    "key": key, "source": "", "patch_number": None, "origin": "folder",
                    "status": "labelled", "notes": "", "file": f.name, "created": _now(),
                    "state": guess_state(f.name), "city": "",
                }
                added += 1
            else:
                updated += 1
            data["patches"][key].update({"trees": trees, "points": points, "file_sig": sig})
        for k, p in data["patches"].items():
            if p.get("file"):
                p["file_missing"] = p["file"] not in present
        data["last_scan"] = _now()
        _save(data)
    return {"added": added, "updated": updated, "files": len(present)}


# ── Overview ──────────────────────────────────────────────────────────────────

def overview() -> dict:
    from services.las_reader import get_session_dir
    root, connected = dataset_root()
    with _lock:
        data = _load()
    sources = data["sources"]
    patches = []
    for p in data["patches"].values():
        p = dict(p)
        src = sources.get(p.get("source") or "", {})
        p["city"] = src.get("city") or p.get("city", "")
        p["state"] = src.get("state") or p.get("state") or guess_state(p.get("file") or "")
        sid, pid = p.get("session_id"), p.get("patch_id")
        p["openable"] = bool(sid and pid and (get_session_dir(sid) / "patches" / f"{pid}.las").exists())
        patches.append(p)
    patches.sort(key=lambda p: (p.get("source") or "~", p.get("patch_number") or 0, p.get("file") or ""))

    srcs = []
    for s in sources.values():
        own = [p for p in patches if p.get("source") == s["name"]]
        srcs.append({**s,
                     "patches": len(own),
                     "exported": sum(1 for p in own if p.get("file")),
                     "trees": sum(max(0, p.get("trees") or 0) for p in own if p.get("file")
                                  and p.get("status") != "excluded")})
    srcs.sort(key=lambda s: (s.get("state", ""), s.get("city", ""), s["name"]))
    return {
        "sources": srcs,
        "patches": patches,
        "source_statuses": SOURCE_STATUSES,
        "patch_statuses": PATCH_STATUSES,
        "labels_folder": {"connected": connected, "path": str(root / "labels"),
                          "registry": str(_registry_path().name)},
        "last_scan": data.get("last_scan"),
        "labeller": config.LABELLER,
    }

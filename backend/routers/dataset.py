"""Dataset overview API: sources (tiles), patches, statuses and notes."""
import csv
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services import dataset_registry as dreg

router = APIRouter(prefix="/api/v1/dataset", tags=["dataset"])


class SourceUpdate(BaseModel):
    name: str
    fields: dict


class KeyRequest(BaseModel):
    key: str


class RenameRequest(BaseModel):
    key: str
    new_name: str


class PatchUpdate(BaseModel):
    key: str
    fields: dict


@router.get("")
def get_overview():
    return dreg.overview()


@router.post("/scan")
def scan_folder():
    """Pick up files in the labels folder the tool didn't write, refresh tree counts."""
    return dreg.scan_labels_folder()


@router.patch("/sources")
def patch_source(req: SourceUpdate):
    try:
        return dreg.update_source(req.name, req.fields)
    except KeyError:
        raise HTTPException(404, "Unknown source")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/patches")
def patch_patch(req: PatchUpdate):
    try:
        return dreg.update_patch(req.key, req.fields)
    except KeyError:
        raise HTTPException(404, "Unknown patch")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/open")
def open_patch(req: KeyRequest):
    """Open a patch in the 3D view. If its session is gone, the saved file in the labels
    folder is loaded as a new session (labels included), so it can be edited and re-saved."""
    import json
    import shutil
    import uuid
    import laspy
    from services.las_reader import create_session, get_session_dir, read_metadata
    from services.units import detect_units
    from services import label_manager as lm
    from services import regions as reg

    rec = dreg.get_patch(req.key)
    if rec is None:
        raise HTTPException(404, "Unknown patch")
    sid, pid = rec.get("session_id"), rec.get("patch_id")
    if sid and pid and (get_session_dir(sid) / "patches" / f"{pid}.las").exists():
        n = next((r["patch_number"] for r in reg.list_regions(sid) if r["patch_id"] == pid),
                 rec.get("patch_number") or 1)
        return {"session_id": sid, "patch_id": pid, "patch_number": n, "reopened": False}

    if not rec.get("file"):
        raise HTTPException(404, "This patch was never saved and its tile was removed from the tool.")
    path = dreg.labels_dir() / rec["file"]
    if not path.exists():
        raise HTTPException(404, f"{rec['file']} is no longer in the labels folder.")

    session_id = create_session()
    sdir = get_session_dir(session_id)
    try:
        orig = sdir / f"original{path.suffix.lower()}"
        shutil.copyfile(path, orig)
        meta = read_metadata(session_id)
        src = dreg.get_source(rec.get("source") or "") or {}
        if src.get("units"):
            units = {"code": src["units"], "source": src.get("units_source") or "crs"}
        else:
            units = detect_units(orig, meta["bounds"]["x"][0])
        (sdir / "meta.json").write_text(json.dumps({
            "filename": rec["file"], "source": rec.get("source") or rec["file"],
            "opened_from": req.key, **meta, "units": units,
        }))
        patch_id = str(uuid.uuid4())
        if orig.suffix == ".las":
            shutil.copyfile(orig, sdir / "patches" / f"{patch_id}.las")
        else:                                   # patches are always stored as .las
            laspy.read(str(orig)).write(str(sdir / "patches" / f"{patch_id}.las"))
    except Exception as e:
        shutil.rmtree(sdir, ignore_errors=True)
        raise HTTPException(500, f"Could not open {rec['file']}: {e}")

    n = lm.register_patch(session_id, patch_id, (rec.get("patch_number") or 1) - 1)
    b = meta["bounds"]
    reg.add_region(session_id, patch_id, n, int(meta["point_count"]), "rectangle",
                   {"x_min": b["x"][0], "x_max": b["x"][1], "y_min": b["y"][0], "y_max": b["y"][1]}, None)
    reg.mark_labelled(session_id, patch_id)
    from routers.patches import ensure_label_state
    ensure_label_state(session_id, patch_id)
    dreg.link_patch(req.key, session_id, patch_id)
    return {"session_id": session_id, "patch_id": patch_id, "patch_number": n, "reopened": True}


@router.post("/rename")
def rename_file(req: RenameRequest):
    """Rename a saved patch file in the labels folder (renames the real file)."""
    try:
        return dreg.rename_file(req.key, req.new_name)
    except KeyError:
        raise HTTPException(404, "Unknown patch")
    except FileNotFoundError as e:
        raise HTTPException(404, f"{e} is not in the labels folder (press Rescan).")
    except FileExistsError as e:
        raise HTTPException(409, f"{e} already exists in the labels folder.")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/patches.csv")
def patches_csv():
    ov = dreg.overview()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["file", "source", "patch", "labeller", "state", "city", "trees", "points", "status",
                "units", "notes"])
    for p in ov["patches"]:
        w.writerow([p.get("file") or "", p.get("source") or "", p.get("patch_number") or "",
                    p.get("labeller") or "", p.get("state") or "", p.get("city") or "", p.get("trees"),
                    p.get("points") or "", p.get("status") or "", p.get("units") or "", p.get("notes") or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="labelled_patches.csv"'})

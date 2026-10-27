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


@router.get("/patches.csv")
def patches_csv():
    ov = dreg.overview()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["file", "source", "patch", "state", "city", "trees", "points", "status", "units", "notes"])
    for p in ov["patches"]:
        w.writerow([p.get("file") or "", p.get("source") or "", p.get("patch_number") or "",
                    p.get("state") or "", p.get("city") or "", p.get("trees"), p.get("points") or "",
                    p.get("status") or "", p.get("units") or "", p.get("notes") or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="labelled_patches.csv"'})

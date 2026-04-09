import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from models.schemas import UploadResponse, Bounds
from services.las_reader import create_session, get_las_path, read_metadata, get_session_dir
import config

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=UploadResponse)
def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".las", ".laz"):
        raise HTTPException(400, "Only .las and .laz files are supported")

    session_id = create_session()
    try:
        dest = get_session_dir(session_id) / f"original{ext}"
        # Stream to disk while enforcing size limit
        written = 0
        with open(dest, "wb") as out:
            while chunk := file.file.read(1024 * 1024):  # 1MB chunks
                written += len(chunk)
                if written > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_BYTES} byte limit")
                out.write(chunk)

        meta = read_metadata(session_id)
    except HTTPException:
        shutil.rmtree(get_session_dir(session_id), ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(get_session_dir(session_id), ignore_errors=True)
        raise HTTPException(500, "Failed to process uploaded file")

    # Persist original filename
    (get_session_dir(session_id) / "meta.json").write_text(
        __import__("json").dumps({"filename": file.filename})
    )

    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        point_count=meta["point_count"],
        bounds=Bounds(**meta["bounds"]),
        available_fields=meta["available_fields"],
    )


@router.get("/{session_id}/info", response_model=UploadResponse)
def get_info(session_id: str):
    import json
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")

    # Read persisted original filename
    meta_path = get_session_dir(session_id) / "meta.json"
    filename = json.loads(meta_path.read_text())["filename"] if meta_path.exists() else las_path.name

    meta = read_metadata(session_id)
    return UploadResponse(
        session_id=session_id,
        filename=filename,
        point_count=meta["point_count"],
        bounds=Bounds(**meta["bounds"]),
        available_fields=meta["available_fields"],
    )

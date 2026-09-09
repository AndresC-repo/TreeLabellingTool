import io
import shutil
import zipfile
import tempfile
import numpy as np
import laspy
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
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


# ---------------------------------------------------------------------------
# File splitting
# ---------------------------------------------------------------------------

_SPLIT_GRIDS = {4: (2, 2), 8: (2, 4), 16: (4, 4), 32: (4, 8)}


@router.post("/split")
async def split_file(
    file: UploadFile = File(...),
    n_tiles: int = Form(...),
):
    """Tile a large LAS/LAZ file into an NxM grid and return a ZIP of the patches.

    Grid layouts: 4→2×2  8→2×4  16→4×4  32→4×8
    Each non-empty tile is saved as <stem>/<stem>_patch_N.las inside the ZIP.
    """
    if n_tiles not in _SPLIT_GRIDS:
        raise HTTPException(400, f"n_tiles must be one of {list(_SPLIT_GRIDS)}")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".las", ".laz"):
        raise HTTPException(400, "Only .las and .laz files are supported")

    stem = Path(file.filename).stem
    rows, cols = _SPLIT_GRIDS[n_tiles]

    # Buffer upload to a temp file (laspy needs seekable file)
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=ext)
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)

        las = laspy.read(tmp_path_str)
        x = np.array(las.x, dtype=np.float64)
        y = np.array(las.y, dtype=np.float64)

        x_min, x_max = float(x.min()), float(x.max())
        y_min, y_max = float(y.min()), float(y.max())
        x_step = (x_max - x_min) / cols
        y_step = (y_max - y_min) / rows

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            patch_num = 0
            for row in range(rows):
                for col in range(cols):
                    xs = x_min + col * x_step
                    xe = x_min + (col + 1) * x_step if col < cols - 1 else x_max + 1e-6
                    ys = y_min + row * y_step
                    ye = y_min + (row + 1) * y_step if row < rows - 1 else y_max + 1e-6

                    mask = (x >= xs) & (x < xe) & (y >= ys) & (y < ye)
                    if not mask.any():
                        continue

                    patch_num += 1

                    new_header = laspy.LasHeader(
                        point_format=las.header.point_format,
                        version=las.header.version,
                    )
                    new_las = laspy.LasData(header=new_header)
                    new_las.x = las.x[mask]
                    new_las.y = las.y[mask]
                    new_las.z = las.z[mask]
                    new_las.classification = las.classification[mask]

                    try:
                        new_las.intensity = las.intensity[mask]
                    except Exception:
                        pass

                    for dim in las.point_format.extra_dimension_names:
                        try:
                            setattr(new_las, dim, getattr(las, dim)[mask])
                        except Exception:
                            pass

                    patch_buf = io.BytesIO()
                    new_las.write(patch_buf)
                    patch_buf.seek(0)
                    zf.writestr(f"{stem}/{stem}_patch_{patch_num}.las", patch_buf.read())

        zip_buf.seek(0)
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stem}.zip"'},
        )

    finally:
        tmp_path.unlink(missing_ok=True)


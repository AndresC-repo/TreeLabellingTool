import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from models.schemas import UploadResponse, Bounds
from services.las_reader import create_session, get_las_path, read_metadata

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".las"):
        raise HTTPException(400, "Only .las files are supported")

    session_id = create_session()
    dest = get_las_path(session_id)

    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    meta = read_metadata(session_id)
    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        point_count=meta["point_count"],
        bounds=Bounds(**meta["bounds"]),
        available_fields=meta["available_fields"],
    )


@router.get("/{session_id}/info", response_model=UploadResponse)
def get_info(session_id: str):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")
    meta = read_metadata(session_id)
    return UploadResponse(
        session_id=session_id,
        filename=las_path.name,
        point_count=meta["point_count"],
        bounds=Bounds(**meta["bounds"]),
        available_fields=meta["available_fields"],
    )

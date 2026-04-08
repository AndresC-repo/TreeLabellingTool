import numpy as np
import laspy
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from models.schemas import ExtractionRequest, ExtractionResponse, Bounds
from services.patch_extractor import extract_patch
from services import label_manager as lm
from services.las_reader import get_session_dir
from services.projection import classification_to_rgb

router = APIRouter(prefix="/api/v1/patches", tags=["patches"])


def get_patch_path(session_id: str, patch_id: str) -> Path:
    return get_session_dir(session_id) / "patches" / f"{patch_id}.las"


@router.post("/{session_id}/extract", response_model=ExtractionResponse)
def extract(session_id: str, req: ExtractionRequest):
    # Validate request
    if req.selection_type == "rectangle" and not req.bounds_2d:
        raise HTTPException(400, "bounds_2d required for rectangle selection")
    if req.selection_type == "polygon" and not req.polygon_2d:
        raise HTTPException(400, "polygon_2d required for polygon selection")
    if req.selection_type not in ("rectangle", "polygon"):
        raise HTTPException(400, "selection_type must be 'rectangle' or 'polygon'")

    result = extract_patch(
        session_id,
        req.selection_type,
        req.bounds_2d,
        req.polygon_2d,
    )
    if result["point_count"] == 0:
        raise HTTPException(400, "No points found in selection")

    # Initialize label state from the saved patch's original classification
    patch_path = get_patch_path(session_id, result["patch_id"])
    las = laspy.read(str(patch_path))
    lm.init_patch(result["patch_id"], np.array(las.classification))

    return ExtractionResponse(
        patch_id=result["patch_id"],
        point_count=result["point_count"],
        bounds_3d=Bounds(**result["bounds_3d"]),
    )


@router.get("/{session_id}/{patch_id}/points")
def get_patch_points(session_id: str, patch_id: str):
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    las = laspy.read(str(patch_path))
    x = np.array(las.x, dtype=np.float32)
    y = np.array(las.y, dtype=np.float32)
    z = np.array(las.z, dtype=np.float32)
    classification = np.array(las.classification)
    rgb = classification_to_rgb(classification).astype(np.float32)

    # Binary layout: [x, y, z, r, g, b, classification] — 7 float32 per point
    out = np.empty((len(x), 7), dtype=np.float32)
    out[:, 0] = x
    out[:, 1] = y
    out[:, 2] = z
    out[:, 3:6] = rgb
    out[:, 6] = classification.astype(np.float32)
    buf = out.tobytes()

    return Response(
        content=buf,
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(len(x)),
            "Access-Control-Expose-Headers": "X-Point-Count",
        },
    )

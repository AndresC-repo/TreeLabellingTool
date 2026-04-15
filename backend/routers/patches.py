import re
import numpy as np
import laspy
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, FileResponse
from models.schemas import ExtractionRequest, ExtractionResponse, Bounds, LabelRequest, LabelResponse, BulkLabelRequest, SaveRequest, SaveResponse
from services.patch_extractor import extract_patch
from services import label_manager as lm
from services.las_reader import get_session_dir
from services.projection import elevation_to_rgb
from services.las_writer import save_labeled_patch

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

    # Initialize label state from the extracted classification (avoids redundant file read)
    lm.init_patch(result["patch_id"], result["classification"])
    patch_number = lm.register_patch(session_id, result["patch_id"])

    return ExtractionResponse(
        patch_id=result["patch_id"],
        patch_number=patch_number,
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
    # Use full int32 label dim if present (supports values > 255)
    if "label" in las.point_format.extra_dimension_names:
        classification = np.array(las.label, dtype=np.int32)
    else:
        classification = np.array(las.classification, dtype=np.int32)
    rgb = elevation_to_rgb(z).astype(np.float32)

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


@router.post("/{session_id}/{patch_id}/label", response_model=LabelResponse)
def label_points(session_id: str, patch_id: str, req: LabelRequest):
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found — was the patch extracted?")
    if not req.point_indices:
        raise HTTPException(400, "point_indices must not be empty")
    try:
        result = lm.apply_label(patch_id, req.point_indices, req.label_value)
    except IndexError as e:
        raise HTTPException(400, str(e))
    return LabelResponse(**result)


@router.post("/{session_id}/{patch_id}/apply-labels-bulk")
def apply_labels_bulk(session_id: str, patch_id: str, req: BulkLabelRequest):
    """Replace the entire label array with inference (or other bulk) results."""
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found — was the patch extracted?")
    try:
        result = lm.apply_labels_bulk(patch_id, np.array(req.labels, dtype=np.int32))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    return result


@router.get("/{session_id}/{patch_id}/next-label")
def next_label(session_id: str, patch_id: str):
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found")
    return {"next_label": lm.get_next_label(patch_id)}


@router.get("/{session_id}/{patch_id}/colormap")
def get_patch_colormap(session_id: str, patch_id: str):
    """Return label color map for the current in-memory label state of a patch."""
    from services.projection import get_classification_color
    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found")
    unique, counts = np.unique(labels, return_counts=True)
    entries = []
    for code, count in zip(unique.tolist(), counts.tolist()):
        r, g, b = get_classification_color(int(code))
        entries.append({
            "value": int(code),
            "color": "#{:02x}{:02x}{:02x}".format(
                round(r * 255), round(g * 255), round(b * 255)
            ),
            "count": int(count),
        })
    return {"entries": entries}


@router.get("/{session_id}/{patch_id}/predict")
def run_prediction(session_id: str, patch_id: str, version: str = "v1"):
    """Run NN inference on a patch and return per-point predicted class labels.

    Query params:
        version: 'v1' (XYZ) | 'v2' (XYZ+cls) | 'v3' (XYZ+int) | 'v4' (XYZ+int+cls)
    """
    from services.predictor import predict, VALID_VERSIONS, _MODEL_CONFIGS
    if version not in VALID_VERSIONS:
        raise HTTPException(400, f"version must be one of {VALID_VERSIONS}")
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    try:
        cfg = _MODEL_CONFIGS[version]
        las = laspy.read(str(patch_path))
        labels = predict(
            np.array(las.x, dtype=np.float32),
            np.array(las.y, dtype=np.float32),
            np.array(las.z, dtype=np.float32),
            intensity      = np.array(las.intensity,       dtype=np.float32) if cfg['use_intensity']      else None,
            classification = np.array(las.classification,  dtype=np.float32) if cfg['use_classification'] else None,
            version=version,
        )
    except Exception as e:
        raise HTTPException(500, f"Inference error: {e}")
    return {"labels": labels.tolist()}


@router.post("/{session_id}/{patch_id}/save", response_model=SaveResponse)
def save_patch(session_id: str, patch_id: str, req: SaveRequest):
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found")
    # Sanitize filename: only allow alphanumerics, dashes, underscores, dots
    safe_name = re.sub(r"[^\w\-.]", "_", req.output_filename)
    if not safe_name.lower().endswith((".las", ".laz")):
        safe_name += ".las"
    output_dir = get_session_dir(session_id) / "outputs" / patch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_name
    count = save_labeled_patch(patch_path, output_path, labels)
    return SaveResponse(
        download_url=f"/api/v1/patches/{session_id}/{patch_id}/download",
        output_filename=safe_name,
        point_count=count,
    )


@router.get("/{session_id}/{patch_id}/download")
def download_patch(session_id: str, patch_id: str):
    output_dir = get_session_dir(session_id) / "outputs" / patch_id
    if not output_dir.exists():
        raise HTTPException(404, "No saved output found")
    files = sorted(output_dir.glob("*.las"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise HTTPException(404, "No saved output found")
    latest = files[0]
    return FileResponse(
        str(latest),
        media_type="application/octet-stream",
        filename=latest.name,
    )

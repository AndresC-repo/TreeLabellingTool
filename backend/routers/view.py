import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from services.las_reader import get_las_path
from services.decimator import read_decimated
from services.point_cache import get_session_points
from services.projection import (
    classification_to_rgb,
    intensity_to_rgb,
    returns_to_rgb,
    build_2d_buffer,
    CLASSIFICATION_COLORS,
    get_classification_color,
)
from services.renderer2d import render_top_view
from config import DEFAULT_MAX_POINTS

router = APIRouter(prefix="/api/v1/view", tags=["view"])

VALID_SCALAR_FIELDS = {"classification", "intensity", "number_of_returns", "elevation"}

# ASPRS human-readable labels for classification codes
_CLASS_LABELS = {
    0: "Never Classified",
    1: "Unclassified",
    2: "Ground",
    3: "Low Vegetation",
    4: "Medium Vegetation",
    5: "High Vegetation",
    6: "Building",
    7: "Low Point (Noise)",
    9: "Water",
    17: "Bridge Deck",
    18: "High Noise",
}


@router.get("/{session_id}/points")
def get_2d_points(
    session_id: str,
    scalar_field: str = "classification",
    max_points: int = Query(DEFAULT_MAX_POINTS, ge=1, le=10_000_000),
):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")

    if scalar_field not in VALID_SCALAR_FIELDS:
        raise HTTPException(400, f"scalar_field must be one of {sorted(VALID_SCALAR_FIELDS)}")

    data, total = read_decimated(las_path, max_points, ["x", "y", scalar_field])

    x = data["x"].astype(np.float32)
    y = data["y"].astype(np.float32)
    scalar = data[scalar_field]

    if scalar_field == "classification":
        rgb = classification_to_rgb(scalar)
    elif scalar_field == "intensity":
        rgb = intensity_to_rgb(scalar)
    else:
        rgb = returns_to_rgb(scalar)

    buf = build_2d_buffer(x, y, rgb)
    actual_count = len(x)
    ratio = actual_count / total if total > 0 else 1.0

    return Response(
        content=buf,
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(actual_count),
            "X-Decimation-Ratio": f"{ratio:.4f}",
            "Access-Control-Expose-Headers": "X-Point-Count, X-Decimation-Ratio",
        },
    )


@router.get("/{session_id}/image")
def get_2d_image(
    session_id: str,
    scalar_field: str = "classification",
    width: int = Query(2048, ge=256, le=4096),
    height: int = Query(2048, ge=256, le=4096),
    point_size: int = Query(1, ge=1, le=8),
):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")
    if scalar_field not in VALID_SCALAR_FIELDS:
        raise HTTPException(400, f"scalar_field must be one of {sorted(VALID_SCALAR_FIELDS)}")

    png_bytes, meta = render_top_view(session_id, las_path, scalar_field, width, height, point_size)
    b = meta["bounds"]
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Point-Count": str(meta["point_count"]),
            "X-Decimation-Ratio": f"{meta['decimation_ratio']:.4f}",
            "X-Bounds-XMin": str(b["xmin"]),
            "X-Bounds-XMax": str(b["xmax"]),
            "X-Bounds-YMin": str(b["ymin"]),
            "X-Bounds-YMax": str(b["ymax"]),
            "X-Image-Width": str(meta["image_width"]),
            "X-Image-Height": str(meta["image_height"]),
            "Access-Control-Expose-Headers": "X-Point-Count,X-Decimation-Ratio,X-Bounds-XMin,X-Bounds-XMax,X-Bounds-YMin,X-Bounds-YMax,X-Image-Width,X-Image-Height",
        },
    )


@router.get("/{session_id}/colormap")
def get_colormap(
    session_id: str,
    scalar_field: str = "classification",
):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")

    if scalar_field not in VALID_SCALAR_FIELDS:
        raise HTTPException(400, f"scalar_field must be one of {sorted(VALID_SCALAR_FIELDS)}")

    if scalar_field == "classification":
        cached = get_session_points(session_id, las_path)
        classification = cached["data"]["classification"]
        unique_codes, counts = np.unique(classification, return_counts=True)
        entries = []
        for code, count in zip(unique_codes.tolist(), counts.tolist()):
            r, g, b = get_classification_color(int(code))
            label = _CLASS_LABELS.get(int(code), f"Label {int(code)}" if int(code) >= 100 else f"Class {int(code)}")
            entries.append({
                "value": int(code),
                "label": label,
                "color": "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255)),
                "count": int(count),
            })
        return {"field": scalar_field, "type": "categorical", "entries": entries}

    return {"field": scalar_field, "type": "continuous", "entries": []}

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from services.las_reader import get_las_path
from services.decimator import read_decimated
from services.projection import (
    classification_to_rgb,
    intensity_to_rgb,
    returns_to_rgb,
    build_2d_buffer,
    CLASSIFICATION_COLORS,
)
from config import DEFAULT_MAX_POINTS

router = APIRouter(prefix="/api/v1/view", tags=["view"])

VALID_SCALAR_FIELDS = {"classification", "intensity", "number_of_returns"}

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
        entries = [
            {
                "value": code,
                "label": _CLASS_LABELS.get(code, f"Class {code}"),
                "color": "#{:02x}{:02x}{:02x}".format(
                    round(r * 255), round(g * 255), round(b * 255)
                ),
            }
            for code, (r, g, b) in CLASSIFICATION_COLORS.items()
        ]
        return {"field": scalar_field, "type": "categorical", "entries": entries}

    return {"field": scalar_field, "type": "continuous", "entries": []}

import numpy as np
import laspy
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from services.las_reader import get_las_path
from services.decimator import read_decimated
from services import projection as proj
from config import DEFAULT_MAX_POINTS

router = APIRouter(prefix="/api/v1/view", tags=["view"])


@router.get("/{session_id}/points")
def get_2d_points(
    session_id: str,
    scalar_field: str = "classification",
    max_points: int = DEFAULT_MAX_POINTS,
):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")

    valid_fields = {"classification", "intensity", "number_of_returns"}
    if scalar_field not in valid_fields:
        raise HTTPException(400, f"scalar_field must be one of {sorted(valid_fields)}")

    fields = ["x", "y", scalar_field]
    data = read_decimated(las_path, max_points, fields)

    x = data["x"].astype(np.float32) if hasattr(data["x"], "astype") else data["x"]
    y = data["y"].astype(np.float32) if hasattr(data["y"], "astype") else data["y"]
    scalar = data[scalar_field]

    if scalar_field == "classification":
        rgb = proj.classification_to_rgb(scalar)
    elif scalar_field == "intensity":
        rgb = proj.intensity_to_rgb(scalar)
    else:  # number_of_returns
        rgb = proj.returns_to_rgb(scalar)

    buf = proj.build_2d_buffer(x.astype(np.float32), y.astype(np.float32), rgb)
    actual_count = len(x)

    with laspy.open(las_path) as f:
        total = f.header.point_count
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
def get_colormap(session_id: str, scalar_field: str = "classification"):
    las_path = get_las_path(session_id)
    if not las_path.exists():
        raise HTTPException(404, "Session not found")

    if scalar_field == "classification":
        entries = [
            {
                "value": k,
                "label": label,
                "color": f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}",
            }
            for k, (r, g, b), label in [
                (0,  (0.5, 0.5, 0.5),    "Never Classified"),
                (1,  (0.7, 0.7, 0.7),    "Unclassified"),
                (2,  (0.55, 0.27, 0.07), "Ground"),
                (3,  (0.13, 0.55, 0.13), "Low Vegetation"),
                (4,  (0.0, 0.8, 0.0),    "Medium Vegetation"),
                (5,  (0.0, 0.5, 0.0),    "High Vegetation"),
                (6,  (1.0, 0.0, 0.0),    "Building"),
                (7,  (1.0, 0.5, 0.0),    "Low Point (Noise)"),
                (9,  (0.0, 0.5, 1.0),    "Water"),
                (17, (0.8, 0.8, 1.0),    "Bridge Deck"),
                (18, (1.0, 0.0, 1.0),    "High Noise"),
            ]
        ]
        return {"field": scalar_field, "type": "categorical", "entries": entries}

    return {"field": scalar_field, "type": "continuous", "entries": []}

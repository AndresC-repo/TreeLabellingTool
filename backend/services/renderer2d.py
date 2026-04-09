"""Render a top-down 2D view of a point cloud as a PNG image."""
from __future__ import annotations
import numpy as np
from io import BytesIO
from PIL import Image
from services.point_cache import get_session_points
from services.projection import classification_to_rgb, intensity_to_rgb, returns_to_rgb

_render_cache: dict = {}  # (session_id, field, width, height, point_size) -> (png_bytes, meta)


def render_top_view(
    session_id: str,
    las_path,
    scalar_field: str,
    width: int = 2048,
    height: int = 2048,
    point_size: int = 1,
) -> tuple[bytes, dict]:
    point_size = max(1, min(point_size, 8))
    key = (session_id, scalar_field, width, height, point_size)
    if key in _render_cache:
        return _render_cache[key]

    cached = get_session_points(session_id, las_path)
    data = cached["data"]
    total = cached["total"]

    x = data["x"].astype(np.float32)
    y = data["y"].astype(np.float32)

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    xpad = max((xmax - xmin) * 0.01, 1e-3)
    ypad = max((ymax - ymin) * 0.01, 1e-3)
    xmin -= xpad; xmax += xpad
    ymin -= ypad; ymax += ypad

    # Map points to pixel coordinates (Y flipped: ymax at top of image)
    px = np.clip(((x - xmin) / (xmax - xmin) * (width - 1)).astype(np.int32), 0, width - 1)
    py = np.clip(((ymax - y) / (ymax - ymin) * (height - 1)).astype(np.int32), 0, height - 1)

    scalar = data[scalar_field]
    if scalar_field == "classification":
        rgb_f = classification_to_rgb(scalar)
    elif scalar_field == "intensity":
        rgb_f = intensity_to_rgb(scalar)
    else:
        rgb_f = returns_to_rgb(scalar)
    rgb8 = (rgb_f * 255).clip(0, 255).astype(np.uint8)

    img_arr = np.full((height, width, 3), [26, 26, 46], dtype=np.uint8)

    if point_size == 1:
        img_arr[py, px] = rgb8
    else:
        # Draw square footprint of radius r around each point
        r = point_size // 2
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                py_off = np.clip(py + dy, 0, height - 1)
                px_off = np.clip(px + dx, 0, width - 1)
                img_arr[py_off, px_off] = rgb8

    img = Image.fromarray(img_arr, "RGB")
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=1)
    png_bytes = buf.getvalue()

    n = len(x)
    meta = {
        "point_count": n,
        "total_count": total,
        "decimation_ratio": n / max(total, 1),
        "bounds": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax},
        "image_width": width,
        "image_height": height,
    }
    _render_cache[key] = (png_bytes, meta)
    return png_bytes, meta

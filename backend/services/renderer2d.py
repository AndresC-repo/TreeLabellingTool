"""Render a top-down 2D view of a point cloud as a PNG image."""
from __future__ import annotations
import numpy as np
from io import BytesIO
from PIL import Image
from services.point_cache import get_session_points
from services.projection import classification_to_rgb, intensity_to_rgb, returns_to_rgb, elevation_to_rgb

_render_cache: dict = {}  # (session_id, field, width, height, point_size) -> (png_bytes, meta)

# Zoomed renders never draw more than this many points (evenly thinned beyond it)
MAX_VIEWPORT_POINTS = 8_000_000
_BG = [26, 26, 46]


def _z_range(session_id: str, fallback: np.ndarray) -> tuple[float, float]:
    """File-wide elevation range, so overview and zoomed renders share one colour scale."""
    import json
    from services.las_reader import get_session_dir
    try:
        z = json.loads((get_session_dir(session_id) / "meta.json").read_text())["bounds"]["z"]
        return float(z[0]), float(z[1])
    except Exception:
        return float(fallback.min()), float(fallback.max())


def _colorize(scalar_field: str, values: np.ndarray, z_range: tuple[float, float]) -> np.ndarray:
    if scalar_field == "elevation":
        z0, z1 = z_range
        # Append the file-wide min/max so elevation_to_rgb normalises to that range
        rgb_f = elevation_to_rgb(np.concatenate([values.astype(np.float32), [z0, z1]]))[:-2]
    elif scalar_field == "classification":
        rgb_f = classification_to_rgb(values)
    elif scalar_field == "intensity":
        rgb_f = intensity_to_rgb(values)
    else:
        rgb_f = returns_to_rgb(values)
    return (rgb_f * 255).clip(0, 255).astype(np.uint8)


def _rasterize(px: np.ndarray, py: np.ndarray, rgb8: np.ndarray, width: int, height: int, point_size: int) -> bytes:
    img_arr = np.full((height, width, 3), _BG, dtype=np.uint8)
    if point_size == 1:
        img_arr[py, px] = rgb8
    else:
        # Draw square footprint of radius r around each point
        r = point_size // 2
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                img_arr[np.clip(py + dy, 0, height - 1), np.clip(px + dx, 0, width - 1)] = rgb8
    buf = BytesIO()
    Image.fromarray(img_arr, "RGB").save(buf, format="PNG", optimize=False, compress_level=1)
    return buf.getvalue()


def render_viewport(
    session_id: str,
    las_path,
    scalar_field: str,
    view: tuple[float, float, float, float],   # world xmin, xmax, ymin, ymax
    width: int,
    height: int,
    point_size: int = 1,
) -> tuple[bytes, dict]:
    """Render only the visible area from ALL points in it (not the decimated sample)."""
    from services.full_cache import get_xy, get_field
    point_size = max(1, min(point_size, 8))
    vx0, vx1, vy0, vy1 = view
    xy, offsets = get_xy(session_id)
    rx0, rx1 = vx0 - offsets[0], vx1 - offsets[0]
    ry0, ry1 = vy0 - offsets[1], vy1 - offsets[1]

    x_all = xy[:, 0]
    y_all = xy[:, 1]
    idx = np.flatnonzero((x_all >= rx0) & (x_all <= rx1) & (y_all >= ry0) & (y_all <= ry1))
    in_view = len(idx)
    if in_view > MAX_VIEWPORT_POINTS:
        idx = idx[:: int(np.ceil(in_view / MAX_VIEWPORT_POINTS))]

    x = np.asarray(xy[idx, 0], dtype=np.float64)
    y = np.asarray(xy[idx, 1], dtype=np.float64)
    px = np.clip(((x - rx0) / (rx1 - rx0) * (width - 1)).astype(np.int32), 0, width - 1)
    py = np.clip(((ry1 - y) / (ry1 - ry0) * (height - 1)).astype(np.int32), 0, height - 1)

    values = np.asarray(get_field(session_id, las_path, scalar_field)[idx])
    z_range = _z_range(session_id, values if len(values) else np.zeros(1)) if scalar_field == "elevation" else (0.0, 1.0)
    rgb8 = _colorize(scalar_field, values, z_range)
    png_bytes = _rasterize(px, py, rgb8, width, height, point_size)

    n = len(idx)
    meta = {
        "point_count": n,
        "total_count": in_view,
        "decimation_ratio": n / max(in_view, 1),
        "bounds": {"xmin": vx0, "xmax": vx1, "ymin": vy0, "ymax": vy1},
        "image_width": width,
        "image_height": height,
    }
    return png_bytes, meta


def invalidate_session(session_id: str) -> None:
    """Drop all cached renders for a session (e.g. after re-labeling)."""
    for key in [k for k in _render_cache if k[0] == session_id]:
        del _render_cache[key]


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

    # float64: float32 only resolves ~0.5 m at UTM northings (~5.4e6), which shows as banding
    x = data["x"].astype(np.float64)
    y = data["y"].astype(np.float64)

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    xpad = max((xmax - xmin) * 0.01, 1e-3)
    ypad = max((ymax - ymin) * 0.01, 1e-3)
    xmin -= xpad; xmax += xpad
    ymin -= ypad; ymax += ypad

    # Map points to pixel coordinates (Y flipped: ymax at top of image)
    px = np.clip(((x - xmin) / (xmax - xmin) * (width - 1)).astype(np.int32), 0, width - 1)
    py = np.clip(((ymax - y) / (ymax - ymin) * (height - 1)).astype(np.int32), 0, height - 1)

    scalar_key = "z" if scalar_field == "elevation" else scalar_field
    scalar = data[scalar_key]
    z_range = _z_range(session_id, scalar) if scalar_field == "elevation" else (0.0, 1.0)
    rgb8 = _colorize(scalar_field, scalar, z_range)
    png_bytes = _rasterize(px, py, rgb8, width, height, point_size)

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

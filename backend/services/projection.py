import numpy as np

# ASPRS classification code palette (value → RGB 0-1 float)
CLASSIFICATION_COLORS = {
    0:  (0.28, 0.28, 0.32),  # GND / Never classified
    1:  (0.7,  0.7,  0.7),   # Unclassified
    2:  (0.55, 0.27, 0.07),  # Ground
    3:  (0.13, 0.55, 0.13),  # Low vegetation
    4:  (0.0,  0.8,  0.0),   # Medium vegetation
    5:  (0.0,  0.5,  0.0),   # High vegetation
    6:  (1.0,  0.0,  0.0),   # Building
    7:  (1.0,  0.5,  0.0),   # Low point (noise)
    9:  (0.0,  0.5,  1.0),   # Water
    17: (0.8,  0.8,  1.0),   # Bridge deck
    18: (1.0,  0.0,  1.0),   # High noise
}

# Explicit palette for first 8 custom labels (101-108) — must match frontend LABEL_PALETTE
_LABEL_PALETTE = [
    (1.0, 0.0, 1.0),  # magenta
    (0.0, 1.0, 1.0),  # cyan
    (1.0, 1.0, 0.0),  # yellow
    (1.0, 0.5, 0.0),  # orange
    (0.5, 0.0, 1.0),  # purple
    (0.0, 1.0, 0.5),  # spring green
    (1.0, 0.0, 0.5),  # hot pink
    (0.5, 1.0, 0.0),  # chartreuse
]
_DEFAULT_COLOR = (0.55, 0.55, 0.55)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    """h, s, l all in [0, 1] → r, g, b in [0, 1]"""
    def hue2rgb(p: float, q: float, t: float) -> float:
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1 / 6: return p + (q - p) * 6 * t
        if t < 1 / 2: return q
        if t < 2 / 3: return p + (q - p) * (2 / 3 - t) * 6
        return p

    if s == 0:
        return l, l, l
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return hue2rgb(p, q, h + 1/3), hue2rgb(p, q, h), hue2rgb(p, q, h - 1/3)


def get_classification_color(code: int) -> tuple[float, float, float]:
    """Return consistent RGB (0-1 float) for any classification code."""
    if code in CLASSIFICATION_COLORS:
        return CLASSIFICATION_COLORS[code]
    if 101 <= code <= 108:
        return _LABEL_PALETTE[code - 101]
    # Any other custom label (109+, 1001, 1201, …): golden-angle hue hash
    # Gives perceptually distinct, collision-resistant, deterministic colours
    hue = (code * 137.508) % 360 / 360
    return _hsl_to_rgb(hue, 0.85, 0.55)


def classification_to_rgb(values: np.ndarray) -> np.ndarray:
    """Map classification values to RGB float32 array of shape (N, 3)."""
    rgb = np.full((len(values), 3), _DEFAULT_COLOR, dtype=np.float32)
    for code in np.unique(values):
        rgb[values == code] = get_classification_color(int(code))
    return rgb


def intensity_to_rgb(values: np.ndarray) -> np.ndarray:
    norm = values.astype(np.float32) / 65535.0
    return np.stack([norm, norm, norm], axis=1)


def elevation_to_rgb(values: np.ndarray) -> np.ndarray:
    z_min, z_max = float(values.min()), float(values.max())
    if z_max == z_min:
        return np.full((len(values), 3), [0.0, 0.5, 1.0], dtype=np.float32)
    t = (values.astype(np.float32) - z_min) / (z_max - z_min)
    r = np.where(t < 1/3, 0.0, np.where(t < 2/3, (t - 1/3) * 3.0, 1.0)).astype(np.float32)
    g = np.where(t < 1/3, t * 3.0, np.where(t < 2/3, 1.0, 1.0 - (t - 2/3) * 3.0)).astype(np.float32)
    b = np.where(t < 1/3, 1.0 - t * 3.0, 0.0).astype(np.float32)
    return np.stack([r, g, b], axis=1)


def returns_to_rgb(values: np.ndarray) -> np.ndarray:
    norm = np.clip((values.astype(np.float32) - 1) / 6.0, 0.0, 1.0)
    return np.stack([norm, 1.0 - norm, np.zeros_like(norm)], axis=1)


def dsm_grid_to_rgb(grid: np.ndarray, no_data_mask: np.ndarray) -> np.ndarray:
    """
    Colorize a 2D DSM grid (max-Z per pixel) with the elevation gradient.
    no_data_mask is True where the pixel has no points.
    Returns uint8 (H, W, 3) image array.
    """
    h, w = grid.shape
    img = np.full((h, w, 3), [26, 26, 46], dtype=np.uint8)
    valid = ~no_data_mask
    if not valid.any():
        return img
    z_valid = grid[valid]
    z_min, z_max = float(z_valid.min()), float(z_valid.max())
    z_range = max(z_max - z_min, 1e-6)
    t = np.zeros((h, w), dtype=np.float32)
    t[valid] = (grid[valid] - z_min) / z_range
    r = np.where(t < 1/3, 0.0, np.where(t < 2/3, (t - 1/3) * 3.0, 1.0)).astype(np.float32)
    g = np.where(t < 1/3, t * 3.0, np.where(t < 2/3, 1.0, 1.0 - (t - 2/3) * 3.0)).astype(np.float32)
    b = np.where(t < 1/3, 1.0 - t * 3.0, 0.0).astype(np.float32)
    rgb_f = np.stack([r, g, b], axis=2)
    img[valid] = (rgb_f[valid] * 255).clip(0, 255).astype(np.uint8)
    return img


def chm_grid_to_rgb(chm: np.ndarray, no_data_mask: np.ndarray) -> np.ndarray:
    """
    Colorize a 2D CHM grid (height above ground per pixel).
    Uses a dark→bright green gradient.
    Returns uint8 (H, W, 3) image array.
    """
    h, w = chm.shape
    img = np.full((h, w, 3), [26, 26, 46], dtype=np.uint8)
    valid = ~no_data_mask
    if not valid.any():
        return img
    chm_max = float(chm[valid].max())
    chm_max = max(chm_max, 1.0)
    t = np.zeros((h, w), dtype=np.float32)
    t[valid] = np.clip(chm[valid] / chm_max, 0.0, 1.0)
    # Dark green at 0 → bright yellow-green at max
    r = (t * 0.75).astype(np.float32)
    g = (0.25 + t * 0.75).astype(np.float32)
    b = np.zeros((h, w), dtype=np.float32)
    rgb_f = np.stack([r, g, b], axis=2)
    img[valid] = (rgb_f[valid] * 255).clip(0, 255).astype(np.uint8)
    return img


def build_2d_buffer(x: np.ndarray, y: np.ndarray, rgb: np.ndarray) -> bytes:
    out = np.empty((len(x), 5), dtype=np.float32)
    out[:, 0] = x
    out[:, 1] = y
    out[:, 2:5] = rgb
    return out.tobytes()

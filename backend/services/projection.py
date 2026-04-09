import numpy as np

# ASPRS classification code palette (value → RGB 0-1 float)
CLASSIFICATION_COLORS = {
    0:  (0.28, 0.28, 0.32),  # GND / Never classified (matches 3D unlabeled gray)
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

# Custom label palette (code 101+ maps into this cycle) — must match frontend LABEL_PALETTE
_LABEL_PALETTE = [
    (1.0, 0.0, 1.0),    # magenta
    (0.0, 1.0, 1.0),    # cyan
    (1.0, 1.0, 0.0),    # yellow
    (1.0, 0.5, 0.0),    # orange
    (0.5, 0.0, 1.0),    # purple
    (0.0, 1.0, 0.5),    # spring green
    (1.0, 0.0, 0.5),    # hot pink
    (0.5, 1.0, 0.0),    # chartreuse
]
_DEFAULT_COLOR = (0.55, 0.55, 0.55)


def get_classification_color(code: int) -> tuple[float, float, float]:
    """Return the RGB (0-1 float) colour for any classification code."""
    if code in CLASSIFICATION_COLORS:
        return CLASSIFICATION_COLORS[code]
    if code >= 101:
        return _LABEL_PALETTE[(code - 101) % len(_LABEL_PALETTE)]
    return _DEFAULT_COLOR


def classification_to_rgb(values: np.ndarray) -> np.ndarray:
    """Map classification values to RGB float32 array of shape (N, 3)."""
    rgb = np.full((len(values), 3), _DEFAULT_COLOR, dtype=np.float32)
    unique_codes = np.unique(values)
    for code in unique_codes:
        rgb[values == code] = get_classification_color(int(code))
    return rgb


def intensity_to_rgb(values: np.ndarray) -> np.ndarray:
    """Map intensity (uint16) to greyscale float32 RGB."""
    norm = values.astype(np.float32) / 65535.0
    return np.stack([norm, norm, norm], axis=1)


def elevation_to_rgb(values: np.ndarray) -> np.ndarray:
    """Map Z elevation to Blue→Green→Yellow→Red gradient (matches CloudCompare default)."""
    z_min, z_max = float(values.min()), float(values.max())
    if z_max == z_min:
        return np.full((len(values), 3), [0.0, 0.5, 1.0], dtype=np.float32)
    t = (values.astype(np.float32) - z_min) / (z_max - z_min)

    r = np.where(t < 1/3, 0.0,
        np.where(t < 2/3, (t - 1/3) * 3.0, 1.0)).astype(np.float32)
    g = np.where(t < 1/3, t * 3.0,
        np.where(t < 2/3, 1.0,
        1.0 - (t - 2/3) * 3.0)).astype(np.float32)
    b = np.where(t < 1/3, 1.0 - t * 3.0, 0.0).astype(np.float32)

    return np.stack([r, g, b], axis=1)


def returns_to_rgb(values: np.ndarray) -> np.ndarray:
    """Map number_of_returns (1-7) to a red→green color gradient."""
    norm = np.clip((values.astype(np.float32) - 1) / 6.0, 0.0, 1.0)
    return np.stack([norm, 1.0 - norm, np.zeros_like(norm)], axis=1)


def build_2d_buffer(x: np.ndarray, y: np.ndarray, rgb: np.ndarray) -> bytes:
    out = np.empty((len(x), 5), dtype=np.float32)
    out[:, 0] = x
    out[:, 1] = y
    out[:, 2:5] = rgb
    return out.tobytes()

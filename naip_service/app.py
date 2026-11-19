"""Optional NAIP service for the labelling tool (separate container, TensorFlow).

POST /hints  {bounds: [xmin, ymin, xmax, ymax], crs_wkt, unit_scale, year?}
  1. finds NAIP (USDA aerial imagery, RGB + near infrared, 0.6 m) on Microsoft's Planetary
     Computer for the box,
  2. resamples it onto a grid in the PATCH's own coordinate system (so it lies exactly under
     the points, also for files in feet),
  3. runs the image tree detector of Ventura et al. (github.com/jonathanventura/urban-tree-detection,
     MIT licence, code in ventura/) if its weights are mounted at /weights/pretrained_rgbn,
  4. returns the image (RGB and NDVI as PNG), its bounds, and the detected trees (x, y, NDVI).

Without weights only the image is returned. NAIP covers the USA only.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import threading
from functools import lru_cache

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ventura"))

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
WEIGHTS = os.environ.get("NAIP_WEIGHTS", "/weights/pretrained_rgbn")
PIXEL_M = 0.6          # NAIP resolution, metres
MAX_PIXELS = 8192      # longest side of the analysis grid (~4.9 km at 0.6 m); bigger areas get a coarser grid
PNG_MAX = 2048         # longest side of the display images sent to the browser
TILE = 512             # Ventura model runs on TILE x TILE pieces (+ OVERLAP each side): low memory
OVERLAP = 32

app = FastAPI(title="NAIP hints")
_lock = threading.Lock()   # one TensorFlow run at a time (CPU, memory)


class HintsRequest(BaseModel):
    bounds: list[float]            # xmin, ymin, xmax, ymax in the patch CRS
    crs_wkt: str
    unit_scale: float = 1.0        # metres per CRS unit
    year: int | None = None        # None = newest available


def _png(arr: np.ndarray) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def _ndvi_rgb(ndvi: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """NDVI -0.2..0.8 -> brown..yellow..green; no data transparent black."""
    t = np.clip((ndvi + 0.2) / 1.0, 0, 1)
    stops = np.array([[120, 80, 50], [200, 190, 120], [150, 200, 80], [30, 120, 40]], float)
    pos = t * (len(stops) - 1)
    i = np.clip(pos.astype(int), 0, len(stops) - 2)
    f = (pos - i)[..., None]
    rgb = stops[i] * (1 - f) + stops[i + 1] * f
    rgb[~valid] = 0
    return rgb.astype(np.uint8)


@lru_cache(maxsize=1)
def _params():
    import yaml
    p = os.path.join(WEIGHTS, "params.yaml")
    if not os.path.exists(p):
        return dict(min_distance=1, threshold_abs=None, threshold_rel=0.2)
    prm = yaml.safe_load(open(p))
    return dict(min_distance=prm["min_distance"],
                threshold_abs=prm["threshold_abs"] if prm["mode"] == "abs" else None,
                threshold_rel=prm["threshold_rel"] if prm["mode"] == "rel" else None)


def _has_model() -> bool:
    return os.path.exists(os.path.join(WEIGHTS, "weights.best.h5"))


@lru_cache(maxsize=1)
def _model():
    """Ventura's SFANet for one (TILE + 2*OVERLAP)^2 RGBN piece. The ImageNet VGG16 download is
    skipped: weights.best.h5 overwrites every layer anyway."""
    import tensorflow.keras.applications as apps
    import models.VGG as vgg
    orig = apps.VGG16

    def vgg16_no_download(*a, **k):
        k["weights"] = None
        return orig(*a, **k)
    vgg.VGG16 = vgg16_no_download
    from models import SFANet
    from utils.preprocess import preprocess_RGBN
    size = TILE + 2 * OVERLAP
    training_model, model = SFANet.build_model((size, size, 4), preprocess_fn=preprocess_RGBN)
    training_model.load_weights(os.path.join(WEIGHTS, "weights.best.h5"))
    return model


def _confidence(img: np.ndarray) -> np.ndarray:
    """Tiled inference over an (4, h, w) uint8 image -> (h, w) tree-centre confidence."""
    _, h, w = img.shape
    pad = np.zeros((h + 2 * OVERLAP + TILE, w + 2 * OVERLAP + TILE, 4), np.float32)
    pad[OVERLAP:OVERLAP + h, OVERLAP:OVERLAP + w] = np.transpose(img, (1, 2, 0))
    conf = np.zeros((h, w), np.float32)
    model = _model()
    size = TILE + 2 * OVERLAP
    for r in range(0, h, TILE):
        for c in range(0, w, TILE):
            piece = pad[r:r + size, c:c + size][None]
            out = model.predict(piece, verbose=False)[0, OVERLAP:OVERLAP + TILE, OVERLAP:OVERLAP + TILE, 0]
            hh, ww = min(TILE, h - r), min(TILE, w - c)
            conf[r:r + hh, c:c + ww] = out[:hh, :ww]
    return conf


def _peaks(conf: np.ndarray, size: int = 256, overlap: int = 32) -> np.ndarray:
    """Tree centres = local maxima, found in size x size windows like Ventura's
    _tiled_peak_finding: their thresholds are relative to each window's maximum."""
    from skimage.feature import peak_local_max
    h, w = conf.shape
    pad = np.zeros((h + 2 * overlap + size, w + 2 * overlap + size), np.float32)
    pad[overlap:overlap + h, overlap:overlap + w] = conf
    out = []
    for r in range(0, h, size):
        for c in range(0, w, size):
            win = pad[r:r + size + 2 * overlap, c:c + size + 2 * overlap]
            idx = peak_local_max(win, **_params())
            keep = ((idx[:, 0] >= overlap) & (idx[:, 0] < overlap + size) &
                    (idx[:, 1] >= overlap) & (idx[:, 1] < overlap + size))
            idx = idx[keep] - overlap + [r, c]
            out.append(idx[(idx[:, 0] < h) & (idx[:, 1] < w)])
    return np.concatenate(out) if out else np.empty((0, 2), int)


def _thumb(arr: np.ndarray) -> np.ndarray:
    """Shrink an (h, w, 3) image so its longest side is at most PNG_MAX."""
    h, w = arr.shape[:2]
    f = max(h, w) / PNG_MAX
    if f <= 1:
        return arr
    from PIL import Image
    return np.asarray(Image.fromarray(arr).resize((max(1, round(w / f)), max(1, round(h / f))), Image.BILINEAR))


@app.get("/health")
def health():
    return {"status": "ok", "model": _has_model()}


_cache: dict = {}        # (bounds, crs, year) -> response; labelling a tree re-asks for the same patch
_CACHE_MAX = 16


@app.post("/hints")
def hints(req: HintsRequest):
    key = (tuple(round(v, 2) for v in req.bounds), req.crs_wkt, req.unit_scale, req.year)
    if key in _cache:
        return _cache[key]
    out = _hints(req)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = out
    return out


def _hints(req: HintsRequest):
    import planetary_computer
    import pystac_client
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    xmin, ymin, xmax, ymax = req.bounds
    try:
        dst_crs = CRS.from_wkt(req.crs_wkt)
    except Exception as e:
        raise HTTPException(400, f"Unusable coordinate system: {e}")
    lon0, lat0, lon1, lat1 = transform_bounds(dst_crs, "EPSG:4326", xmin, ymin, xmax, ymax, densify_pts=21)

    try:
        catalog = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
        items = list(catalog.search(collections=["naip"], bbox=[lon0, lat0, lon1, lat1]).items())
    except Exception as e:
        raise HTTPException(502, f"Planetary Computer not reachable: {e}")
    if not items:
        raise HTTPException(404, "No NAIP imagery here (NAIP covers the USA only).")
    years = sorted({int(i.properties["naip:year"]) for i in items})
    year = req.year if req.year in years else years[-1]
    items = [i for i in items if int(i.properties["naip:year"]) == year]

    out = render([i.assets["image"].href for i in items], req.bounds, dst_crs, req.unit_scale)
    out.update(year=year, years=years, items=[i.id for i in items])
    out.update(hand_labels(req.bounds, dst_crs, (lon0, lat0, lon1, lat1)))
    return out


# ── Hand labels of Ventura et al. (urban-tree-detection-data, CC BY 4.0) ──────────────────────
# data/ventura_labels.csv: one row per hand-placed tree (lon, lat, year, crop);
# data/ventura_crops.csv: the 154 m image crops that were labelled (4 corners in lon/lat).
# Labels exist only INSIDE those crops (8 Californian cities, 2016/2018/2020).
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@lru_cache(maxsize=1)
def _label_table():
    import csv
    p = os.path.join(DATA, "ventura_labels.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p)))
    return (np.array([float(r["lon"]) for r in rows]), np.array([float(r["lat"]) for r in rows]),
            np.array([int(r["year"]) for r in rows]), np.array([r["crop"] for r in rows]))


@lru_cache(maxsize=1)
def _crop_table():
    import csv
    p = os.path.join(DATA, "ventura_crops.csv")
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def hand_labels(bounds, dst_crs, lonlat_box):
    """Hand labels and labelled-crop outlines inside the patch, in the patch CRS."""
    from rasterio.warp import transform
    t = _label_table()
    if t is None:
        return {"hand_labels": [], "hand_crops": []}
    lon, lat, year, crop = t
    lo0, la0, lo1, la1 = lonlat_box
    pad = 0.001
    sel = (lon >= lo0 - pad) & (lon <= lo1 + pad) & (lat >= la0 - pad) & (lat <= la1 + pad)
    xmin, ymin, xmax, ymax = bounds
    labels = []
    if sel.any():
        xs, ys = transform("EPSG:4326", dst_crs, lon[sel].tolist(), lat[sel].tolist())
        for x, y, yr, cr in zip(xs, ys, year[sel], crop[sel]):
            if xmin <= x <= xmax and ymin <= y <= ymax:
                labels.append([float(x), float(y), int(yr), str(cr)])
    crops = []
    for r in _crop_table():
        clon = [float(r[f"lon{k}"]) for k in range(4)]
        clat = [float(r[f"lat{k}"]) for k in range(4)]
        if max(clon) < lo0 or min(clon) > lo1 or max(clat) < la0 or min(clat) > la1:
            continue
        xs, ys = transform("EPSG:4326", dst_crs, clon, clat)
        crops.append({"crop": r["crop"], "city": r["city"], "year": int(r["year"]), "split": r["split"],
                      "ring": [[float(x), float(y)] for x, y in zip(xs, ys)]})
    return {"hand_labels": labels, "hand_crops": crops}


def render(hrefs, bounds, dst_crs, unit_scale):
    """Resample the NAIP files onto a grid in the patch CRS, run the image model, encode."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    xmin, ymin, xmax, ymax = bounds
    res = PIXEL_M / max(unit_scale, 1e-9)                       # ~0.6 m in CRS units
    res = max(res, max(xmax - xmin, ymax - ymin) / MAX_PIXELS)
    w = max(int(np.ceil((xmax - xmin) / res)), 1)
    h = max(int(np.ceil((ymax - ymin) / res)), 1)
    transform = from_origin(xmin, ymax, res, res)
    img = np.zeros((4, h, w), np.uint8)
    for href in hrefs:
        with rasterio.open(href) as src:
            band = np.zeros((4, h, w), np.uint8)
            for b in range(4):
                reproject(rasterio.band(src, b + 1), band[b], dst_transform=transform, dst_crs=dst_crs,
                          resampling=Resampling.bilinear, dst_nodata=0)
            fill = (img.sum(0) == 0) & (band.sum(0) > 0)
            img[:, fill] = band[:, fill]
    valid = img.sum(0) > 0
    if not valid.any():
        raise HTTPException(404, "The NAIP image has no pixels in this patch.")

    r, n = img[0].astype(float), img[3].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(r + n > 0, (n - r) / (n + r), 0.0)

    trees, note = [], ""
    if _has_model():
        with _lock:
            conf = _confidence(img)
        conf[~valid] = 0
        for row, col in _peaks(conf):
            tx, ty = rasterio.transform.xy(transform, int(row), int(col))
            trees.append([float(tx), float(ty)])
    else:
        note = "Image-tree model not found (weights/pretrained_rgbn): showing the image only."

    return {
        "bounds": [xmin, ymax - h * res, xmin + w * res, ymax],   # exact image extent
        "rgb_png": _png(_thumb(np.transpose(img[:3], (1, 2, 0)))),
        "ndvi_png": _png(_thumb(_ndvi_rgb(ndvi, valid))),
        "trees": trees,
        "model": _has_model(),
        "note": note,
    }

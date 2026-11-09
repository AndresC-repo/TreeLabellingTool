"""Where a tile is: its state and nearest city, from the coordinates stored in the file.

The file's coordinate system (CRS) converts the tile's centre to latitude/longitude; the
state is the US state polygon containing it, the city the nearest of the 1,000 largest US
cities within CITY_MAX_KM (population >= CITY_MIN_POP). Files without a CRS, or outside
the US, return None (the file-name rules in dataset_registry.guess_state still apply).
"""
from __future__ import annotations
import csv
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
CITY_MAX_KM = 20.0
CITY_MIN_POP = 50_000

_STATE_NAMES = {}


@lru_cache(maxsize=1)
def _states():
    """[(code, name, [rings as Nx2 arrays], bbox)] — all rings of a state, holes included."""
    fc = json.loads((DATA / "us_states.geojson").read_text())
    out = []
    for f in fc["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = [np.asarray(r, dtype=np.float64) for poly in polys for r in poly]
        allpts = np.vstack(rings)
        bbox = (allpts[:, 0].min(), allpts[:, 1].min(), allpts[:, 0].max(), allpts[:, 1].max())
        out.append((f["properties"]["code"], f["properties"]["name"], rings, bbox))
        _STATE_NAMES[f["properties"]["name"]] = f["properties"]["code"]
    return out


@lru_cache(maxsize=1)
def _cities():
    rows = list(csv.DictReader(open(DATA / "us_cities.csv", newline="")))
    _states()   # fills _STATE_NAMES
    return [(r["city"], _STATE_NAMES.get(r["state"], ""), int(r["population"]), float(r["lat"]), float(r["lon"]))
            for r in rows]


def _in_ring(lon, lat, ring) -> bool:
    x, y = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cross = (y > lat) != (y2 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        xin = (x2 - x) * (lat - y) / (y2 - y) + x
    return bool(np.count_nonzero(cross & (lon < xin)) % 2)


def state_at(lon: float, lat: float) -> str:
    """Postal code of the state containing the point ('' if none)."""
    for code, _name, rings, (x0, y0, x1, y1) in _states():
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            # even-odd over all rings handles holes and multi-part states
            if sum(_in_ring(lon, lat, r) for r in rings) % 2:
                return code
    return ""


def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def nearest_city(lon: float, lat: float, state: str = "") -> tuple[str, float] | None:
    """(city, distance km) of the nearest large city within CITY_MAX_KM, preferring cities
    in the same state (a tile in Arlington VA is not "Washington")."""
    best = None
    for name, st, pop, clat, clon in _cities():
        if pop < CITY_MIN_POP:
            continue
        d = _km(lat, lon, clat, clon)
        if d > CITY_MAX_KM:
            continue
        key = (0 if (state and st == state) else 1, d)
        if best is None or key < best[0]:
            best = (key, name, d)
    return (best[1], round(best[2], 1)) if best else None


def tile_location(las_path) -> dict | None:
    """{"lat", "lon", "state", "city", "city_km"} for a LAS/LAZ file, or None without a usable CRS."""
    import laspy
    from pyproj import CRS, Transformer
    with laspy.open(str(las_path)) as f:
        h = f.header
        try:
            crs = h.parse_crs()
        except Exception:
            crs = None
        cx = (float(h.mins[0]) + float(h.maxs[0])) / 2
        cy = (float(h.mins[1]) + float(h.maxs[1])) / 2
    if crs is None:
        return None
    if crs.is_compound:                      # horizontal + vertical: use the horizontal part
        crs = next((c for c in crs.sub_crs_list if c.is_projected or c.is_geographic), crs)
    lon, lat = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True).transform(cx, cy)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    state = state_at(lon, lat)
    city = nearest_city(lon, lat, state)
    return {"lat": round(lat, 5), "lon": round(lon, 5), "state": state,
            "city": city[0] if city else "", "city_km": city[1] if city else None}

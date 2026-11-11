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


_USER_DEFINED = 32767
_CS_AXES = {9001: "EASTING_NORTHING", 9002: "EASTING_NORTHING_FT", 9003: "EASTING_NORTHING_US_FT"}


def _crs_from_geokeys(header):
    """CRS from GeoTIFF keys that laspy can't turn into one: a "user-defined" projected
    system that still names its projection (e.g. key 3074 = 16019, UTM zone 19N) and
    linear unit. The datum is taken as NAD83, which is what USGS tiles use; for finding
    a state and city the difference to WGS84 (about 1 m) does not matter."""
    from pyproj import CRS
    from pyproj.crs import ProjectedCRS, CoordinateOperation
    from pyproj.crs.coordinate_system import Cartesian2DCS
    from pyproj.crs.enums import Cartesian2DCSAxis
    keys, dbl = {}, {}
    doubles = next((list(v.doubles) for v in header.vlrs
                    if getattr(v, "record_id", None) == 34736 and hasattr(v, "doubles")), [])
    for vlr in header.vlrs:
        if getattr(vlr, "record_id", None) == 34735 and hasattr(vlr, "geo_keys"):
            for k in vlr.geo_keys:
                if k.tiff_tag_location == 0:
                    keys[k.id] = k.value_offset
                elif k.tiff_tag_location == 34736 and k.value_offset < len(doubles):
                    dbl[k.id] = float(getattr(doubles[k.value_offset], "value", doubles[k.value_offset]))
    pcs = keys.get(3072)
    if pcs and pcs != _USER_DEFINED:
        return CRS.from_epsg(pcs)
    unit = {9001: "m", 9002: "ft", 9003: "us-ft"}.get(keys.get(3076, 9001), "m")
    proj = keys.get(3074)
    if (not proj or proj == _USER_DEFINED) and keys.get(3075) == 1 and 3082 in dbl:
        # fully user-defined Transverse Mercator: parameters in the doubles VLR
        lon0 = dbl.get(3088, dbl.get(3080, 0.0))
        return CRS.from_proj4(
            f"+proj=tmerc +lat_0={dbl.get(3081, 0.0)} +lon_0={lon0} +k={dbl.get(3092, 1.0)} "
            f"+x_0={dbl[3082]} +y_0={dbl.get(3083, 0.0)} +ellps=GRS80 +units={unit} +no_defs")
    if not proj or proj == _USER_DEFINED:
        return None
    geog = keys.get(2048)
    base = CRS.from_epsg(geog if geog and geog != _USER_DEFINED else 4269)
    axes = getattr(Cartesian2DCSAxis, _CS_AXES.get(keys.get(3076, 9001), "EASTING_NORTHING"))
    return ProjectedCRS(conversion=CoordinateOperation.from_epsg(proj),
                        geodetic_crs=base, cartesian_cs=Cartesian2DCS(axis=axes))


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
            try:
                crs = _crs_from_geokeys(h)
            except Exception:
                crs = None
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

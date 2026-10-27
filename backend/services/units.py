"""Linear units of a point cloud (metres vs feet).

All segmentation settings in the UI are in metres. Many US datasets (e.g. USGS / FDEM
state-plane tiles) are in US survey feet, so every distance has to be converted into
the file's own units before it is compared with coordinates.

Detection order:
  1. CRS stored in the LAS file (GeoTIFF keys or OGC WKT, VLR or EVLR) -> source "crs"
  2. No CRS: state-plane-in-feet style coordinates                     -> source "guess"
     (eastings above 1,000,000 are not used by UTM or most metric grids)
  3. No CRS, easting below 1,000,000, and the point density read as metres
     is implausibly low (< 4 pts/m²) — e.g. FL FDEM tiles in the grid at
     x ≈ 505,000 / y ≈ 1,535,000, which are US feet                    -> source "uncertain"
     (metres assumed but flagged in the UI; exports carry no units marker)
  4. Otherwise metres                                                  -> source "default"
The user can override it per file                                      -> source "user"
"""
from __future__ import annotations
import json
import re
import struct

import laspy

# metres per unit
UNITS = {
    "m":    {"scale": 1.0,                 "name": "metres"},
    "ftUS": {"scale": 1200.0 / 3937.0,     "name": "US survey feet"},
    "ft":   {"scale": 0.3048,              "name": "feet"},
}
_EPSG_UNIT = {9001: "m", 9002: "ft", 9003: "ftUS"}   # GeoTIFF ProjLinearUnits / VerticalUnits
_MIN_METRIC_DENSITY = 4.0   # pts/m²; below this, "metres" is suspicious (feet read as m look ~10.8x sparser)


def _all_vlrs(header):
    return list(header.vlrs or []) + list(getattr(header, "evlrs", None) or [])


def _from_geokeys(header) -> str | None:
    for vlr in _all_vlrs(header):
        if getattr(vlr, "record_id", None) != 34735:
            continue
        try:
            raw = vlr.record_data_bytes() if hasattr(vlr, "record_data_bytes") else bytes(vlr.record_data)
        except Exception:
            try:
                keys = vlr.geo_keys   # laspy GeoKeyDirectoryVlr
                for k in keys:
                    if k.id in (3076, 4099) and k.value_offset in _EPSG_UNIT:
                        return _EPSG_UNIT[k.value_offset]
            except Exception:
                pass
            continue
        vals = struct.unpack(f"<{len(raw) // 2}H", raw[: len(raw) // 2 * 2])
        n = vals[3]
        for i in range(n):
            key_id, loc, _count, value = vals[4 + i * 4: 8 + i * 4]
            if key_id in (3076, 4099) and loc == 0 and value in _EPSG_UNIT:
                return _EPSG_UNIT[value]
    return None


def _from_wkt(header) -> str | None:
    for vlr in _all_vlrs(header):
        if getattr(vlr, "record_id", None) != 2112:
            continue
        try:
            wkt = vlr.string if hasattr(vlr, "string") else bytes(vlr.record_data).decode("utf-8", "ignore")
        except Exception:
            continue
        # The projected CRS's own UNIT is the last top-level UNIT[...] before AXIS/AUTHORITY
        units = re.findall(r'(?:LENGTHUNIT|UNIT)\["([^"]+)"', wkt)
        for u in reversed(units):
            ul = u.lower()
            if "us survey" in ul or "foot_us" in ul or "ftus" in ul:
                return "ftUS"
            if "foot" in ul or "feet" in ul:
                return "ft"
            if "metre" in ul or "meter" in ul:
                return "m"
    return None


def _from_tool_vlr(header) -> str | None:
    """Units stored by this tool's export (LabellingTool VLR, JSON with "units")."""
    for vlr in _all_vlrs(header):
        if getattr(vlr, "user_id", "") == "LabellingTool" and getattr(vlr, "record_id", None) == 1:
            try:
                code = json.loads(bytes(vlr.record_data).decode("utf-8")).get("units")
            except Exception:
                return None
            return code if code in UNITS else None
    return None


def detect_units(las_path, x_min: float | None = None) -> dict:
    with laspy.open(las_path) as f:
        header = f.header
        code = _from_geokeys(header) or _from_wkt(header)
        if code:
            return {"code": code, "source": "crs"}
        code = _from_tool_vlr(header)
        if code:
            return {"code": code, "source": "export"}
        if x_min is None:
            x_min = float(header.mins[0])
        extent = (float(header.maxs[0] - header.mins[0]), float(header.maxs[1] - header.mins[1]))
        n_points = int(header.point_count)
    if abs(x_min) > 1_000_000:
        return {"code": "ftUS", "source": "guess"}
    area = extent[0] * extent[1]
    density = n_points / area if area > 0 else None
    if density is not None and density < _MIN_METRIC_DENSITY:
        return {"code": "m", "source": "uncertain", "density_as_m": round(density, 2)}
    return {"code": "m", "source": "default"}


def describe(units: dict) -> dict:
    u = UNITS.get(units.get("code", "m"), UNITS["m"])
    out = {"code": units.get("code", "m"), "name": u["name"], "scale": u["scale"],
           "source": units.get("source", "default")}
    if "density_as_m" in units:
        out["density_as_m"] = units["density_as_m"]
    return out


def get_session_units(session_id: str) -> dict:
    """Units for a session (detected once and cached in meta.json)."""
    from services.las_reader import get_session_dir, get_las_path
    meta_path = get_session_dir(session_id) / "meta.json"
    try:
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    except (OSError, ValueError):
        meta = {}
    if "units" not in meta:
        las_path = get_las_path(session_id)
        if not las_path.exists():
            return describe({"code": "m", "source": "default"})
        meta["units"] = detect_units(las_path)
        try:
            meta_path.write_text(json.dumps(meta))
        except OSError:
            pass
    return describe(meta["units"])


def set_session_units(session_id: str, code: str) -> dict:
    from services.las_reader import get_session_dir
    if code not in UNITS:
        raise ValueError(f"units must be one of {list(UNITS)}")
    meta_path = get_session_dir(session_id) / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["units"] = {"code": code, "source": "user"}
    meta_path.write_text(json.dumps(meta))
    return describe(meta["units"])

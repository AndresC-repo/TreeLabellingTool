from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict

class Bounds(BaseModel):
    x: List[float]
    y: List[float]
    z: Optional[List[float]] = None

class UploadResponse(BaseModel):
    session_id: str
    filename: str
    folder: Optional[str] = None      # folder it was loaded from (e.g. "Gainesville/tiles"), for grouping
    point_count: int
    bounds: Bounds
    available_fields: List[str]
    patch_count: int = 0
    # Linear units of the file: {code: m|ftUS|ft, name, scale (metres per unit), source: crs|guess|default|user}
    units: Optional[Dict[str, Any]] = None

class UnitsRequest(BaseModel):
    units: str   # "m" | "ftUS" | "ft"
    force: bool = False   # allow units that contradict the file's coordinate system

class ExtractionRequest(BaseModel):
    selection_type: str  # "rectangle" or "polygon"
    bounds_2d: Optional[Dict[str, float]] = None  # x_min, x_max, y_min, y_max
    polygon_2d: Optional[List[List[float]]] = None  # [[x1,y1], ...]
    remove_noise: bool = True   # drop noise-classified and isolated extreme points (services/noise.py)

class ExtractionResponse(BaseModel):
    patch_id: str
    patch_number: int
    point_count: int
    bounds_3d: Bounds
    noise_removed: int = 0      # points dropped as noise

class LabelRequest(BaseModel):
    point_indices: List[int]
    label_value: int
    protect_classes: bool = True   # if True, skip ASPRS class 2 (ground) and 6 (building)

class LabelResponse(BaseModel):
    label_value: int
    points_labeled: int
    label_stats: Dict[str, int]

class BulkLabelRequest(BaseModel):
    labels: List[int]   # one label value per point, length must equal patch point count

class SaveRequest(BaseModel):
    output_filename: Optional[str] = None   # None/empty = automatic name
    to_labels: bool = True                  # also write into the training labels folder
    confirm_units: bool = False             # save even if the units checks complain

class SaveResponse(BaseModel):
    download_url: str
    output_filename: str
    point_count: int
    trees: int = 0
    saved_to: Optional[str] = None          # path in the labels folder (None if not written)
    labels_folder_connected: bool = False

class SegmentTreesNNRequest(BaseModel):
    labels: List[int]                       # tree mask: >= 100 = tree
    min_peak_distance: Optional[float] = None   # m; None = setting from clustering json
    sigma: Optional[float] = None               # m
    min_crown_area: Optional[float] = None      # m²
    min_points: Optional[int] = None

class SegmentTreesRequest(BaseModel):
    labels: List[int]            # per-point semantic labels (0=non-tree, 101=tree)
    # Defaults = the panel's tuned defaults (InferenceLegend.vue), so a call without the
    # panel behaves the same. All lengths in metres.
    cell_size: float = 0.75
    smooth_window: int = 5
    smooth_sigma: float = 0.0
    min_height: float = 2.5
    min_distance: int = 10       # legacy (cells); ignored when min_tree_spacing is set
    max_radius: float = 3.0
    min_tree_points: int = 30
    min_crown_cells: int = 70    # legacy (cells); ignored when min_crown_area is set
    # Local maxima lower than this (m) are not used as seeds; None = same as min_height
    min_peak_height: Optional[float] = 2.5
    # Blob filter as an area (m²); when set it replaces min_crown_cells
    min_crown_area: Optional[float] = 2.0
    # Minimum distance between tree tops (m); when set it replaces min_distance (cells).
    min_tree_spacing: Optional[float] = 2.5
    # A tree top is dropped when a taller one is closer than factor × that tree's height (m),
    # capped at max_tree_spacing. 0 = fixed spacing only.
    spacing_height_factor: float = 0.5
    max_tree_spacing: float = 8.0
    # Canopy no seed reached becomes its own tree (if large and tall enough) instead of non-tree.
    rescue_orphans: bool = True
    # Split off trees standing under another crown: a vertical gap of at least this many
    # metres with no points separates them. 0 = off.
    understory_gap: float = 2.0
    # Optional DTM grid pre-computed on the frontend from ASPRS class-2 ground points.
    # When provided it is used for per-point terrain height instead of re-deriving from the LAS file.
    dtm_grid: Optional[List[float]] = None   # flat array, dtm_rows * dtm_cols values
    dtm_rows: int = 64
    dtm_cols: int = 64
    dtm_x_min: float = 0.0
    dtm_y_min: float = 0.0
    dtm_x_range: float = 1.0
    dtm_y_range: float = 1.0

class SegmentTreesResponse(BaseModel):
    labels: List[int]              # per-point instance labels (0=non-tree, 201+=instances)
    tree_count: int
    peaks: List[List[float]]       # [[x, y, z], ...] — valid tree tops (after merge filter)
    seed_peaks: List[List[float]]  # [[x, y, z], ...] — ALL CHM local maxima (watershed seeds)
    rejected_peaks: List[List[float]] = []   # maxima dropped by min_peak_height
    stats: Optional[Dict[str, Any]] = None   # what each step did (counts, warning)

class TreeMetricsRequest(BaseModel):
    labels: List[int]              # per-point instance labels (201+=instances)
    cell_size: float = 1.5         # no longer used by the metrics (kept for old clients)
    dtm_grid: Optional[List[float]] = None
    dtm_rows: int = 64
    dtm_cols: int = 64
    dtm_x_min: float = 0.0
    dtm_y_min: float = 0.0
    dtm_x_range: float = 1.0
    dtm_y_range: float = 1.0

class TreeMetrics(BaseModel):
    """One tree. Lengths in metres, areas in m², volumes in m³ (see services/tree_metrics.py)."""
    id: int
    # position: crown centre and tree top, in file coordinates and (with a CRS) WGS84
    x: float
    y: float
    top_x: float
    top_y: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    top_lat: Optional[float] = None
    top_lon: Optional[float] = None
    height: float            # highest point above the ground under it
    height_p95: float
    height_p50: float
    height_p10: float
    crown_area: float        # convex outline seen from above
    crown_diameter: float    # diameter of a circle with that area
    crown_volume: float      # 3D convex hull
    ground_elevation: float
    ground_source: str       # ground_points | grid | lowest_point
    point_count: int
    point_density: float     # points per m² of crown
    quality: str             # "ok" or reasons separated by ";" (tree_metrics.QUALITY_NOTES)

class TreeMetricsResponse(BaseModel):
    trees: List[TreeMetrics]
    crs: str = ""            # coordinate system of x/y, e.g. "EPSG:26917"; "" = unknown (no lat/lon)
    csv: str = ""            # the same table as CSV text, ready to download
    quality_notes: dict = {}

class PredictRequest(BaseModel):
    version: str = "metric"   # "metric" (latest) | "metric_old"
    # Optional DTM grid pre-computed on the frontend from ASPRS class-2 ground points.
    # When provided, used for accurate per-point height-above-ground normalisation.
    dtm_grid: Optional[List[float]] = None   # flat array, dtm_rows * dtm_cols values
    dtm_rows: int = 64
    dtm_cols: int = 64
    dtm_x_min: float = 0.0
    dtm_y_min: float = 0.0
    dtm_x_range: float = 1.0
    dtm_y_range: float = 1.0


class RelabelSelectionRequest(BaseModel):
    point_indices: List[int]
    from_label: int
    to_label: int

class RelabelAllRequest(BaseModel):
    from_label: int
    to_label: int = Field(ge=0, le=2_147_483_647)

class RelabelSelectionResponse(BaseModel):
    applied: int
    applied_indices: List[int]

class UndoResponse(BaseModel):
    had_operation: bool
    full_reload: bool = False
    indices: List[int] = []
    label_values: List[int] = []
    undo_depth: int = 0      # steps left to undo
    redo_depth: int = 0      # steps available to redo

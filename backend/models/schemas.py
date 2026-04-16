from pydantic import BaseModel
from typing import Optional, List, Dict

class Bounds(BaseModel):
    x: List[float]
    y: List[float]
    z: Optional[List[float]] = None

class UploadResponse(BaseModel):
    session_id: str
    filename: str
    point_count: int
    bounds: Bounds
    available_fields: List[str]

class ExtractionRequest(BaseModel):
    selection_type: str  # "rectangle" or "polygon"
    bounds_2d: Optional[Dict[str, float]] = None  # x_min, x_max, y_min, y_max
    polygon_2d: Optional[List[List[float]]] = None  # [[x1,y1], ...]

class ExtractionResponse(BaseModel):
    patch_id: str
    patch_number: int
    point_count: int
    bounds_3d: Bounds

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
    output_filename: str

class SaveResponse(BaseModel):
    download_url: str
    output_filename: str
    point_count: int

class SegmentTreesRequest(BaseModel):
    labels: List[int]            # per-point semantic labels (0=non-tree, 101=tree)
    cell_size: float = 0.5
    smooth_window: int = 5       # Duncanson uniform-filter window size (cells); paper: 5
    smooth_sigma: float = 0.0   # optional additional Gaussian σ after window filter
    min_height: float = 2.0
    min_distance: int = 5
    max_radius: float = 15.0
    min_tree_points: int = 50
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

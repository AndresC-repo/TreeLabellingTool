import re
import numpy as np
import laspy
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel
from models.schemas import ExtractionRequest, ExtractionResponse, Bounds, LabelRequest, LabelResponse, BulkLabelRequest, SaveRequest, SaveResponse, SegmentTreesRequest, SegmentTreesResponse, TreeMetricsRequest, TreeMetricsResponse, AutoTuneRequest, AutoTuneResponse, MarkTrainingRequest, MarkTrainingResponse, RelabelSelectionRequest, RelabelSelectionResponse, UndoResponse
from services.patch_extractor import extract_patch
from services import label_manager as lm
from services.las_reader import get_session_dir
from services.projection import elevation_to_rgb
from services.las_writer import save_labeled_patch

router = APIRouter(prefix="/api/v1/patches", tags=["patches"])


def get_patch_path(session_id: str, patch_id: str) -> Path:
    return get_session_dir(session_id) / "patches" / f"{patch_id}.las"


@router.post("/{session_id}/extract", response_model=ExtractionResponse)
def extract(session_id: str, req: ExtractionRequest):
    # Validate request
    if req.selection_type == "rectangle" and not req.bounds_2d:
        raise HTTPException(400, "bounds_2d required for rectangle selection")
    if req.selection_type == "polygon" and not req.polygon_2d:
        raise HTTPException(400, "polygon_2d required for polygon selection")
    if req.selection_type not in ("rectangle", "polygon"):
        raise HTTPException(400, "selection_type must be 'rectangle' or 'polygon'")

    result = extract_patch(
        session_id,
        req.selection_type,
        req.bounds_2d,
        req.polygon_2d,
    )
    if result["point_count"] == 0:
        raise HTTPException(400, "No points found in selection")

    # Initialize label state from the extracted classification (avoids redundant file read)
    lm.init_patch(result["patch_id"], result["classification"])
    patch_number = lm.register_patch(session_id, result["patch_id"])

    return ExtractionResponse(
        patch_id=result["patch_id"],
        patch_number=patch_number,
        point_count=result["point_count"],
        bounds_3d=Bounds(**result["bounds_3d"]),
    )


@router.get("/{session_id}/{patch_id}/points")
def get_patch_points(session_id: str, patch_id: str):
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    las = laspy.read(str(patch_path))
    x = np.array(las.x, dtype=np.float32)
    y = np.array(las.y, dtype=np.float32)
    z = np.array(las.z, dtype=np.float32)

    # Prefer in-memory labels (reflect any labeling done this session) over the LAS file.
    # If state is missing (e.g. after a server restart), auto-initialize from the LAS file
    # so that labeling works immediately without requiring a re-extraction.
    in_memory = lm.get_labels(patch_id)
    if in_memory is not None:
        classification = in_memory.astype(np.int32)
    else:
        # original ASPRS classification — always the unmodified field from the LAS file
        orig_cls = np.array(las.classification, dtype=np.int32)
        # current labels — prefer saved int32 'label' dim, fall back to classification
        if "label" in las.point_format.extra_dimension_names:
            classification = np.array(las.label, dtype=np.int32)
        else:
            classification = orig_cls.copy()
        # Re-initialize the label manager so subsequent label/save calls work.
        # Pass orig_cls separately so protect-classes filtering uses the real ASPRS codes
        # even for patches that were previously saved with custom labels.
        lm.init_patch(patch_id, orig_cls, current_labels=classification)
    rgb = elevation_to_rgb(z).astype(np.float32)
    # Original ASPRS classification — always from las.classification (never overwritten by labelling).
    # Sent as field 8 so the frontend can show the original scan structure in "show only <100" mode.
    orig_asprs = np.array(las.classification, dtype=np.float32)

    # Binary layout: [x, y, z, r, g, b, current_label, orig_classification] — 8 float32 per point
    out = np.empty((len(x), 8), dtype=np.float32)
    out[:, 0] = x
    out[:, 1] = y
    out[:, 2] = z
    out[:, 3:6] = rgb
    out[:, 6] = classification.astype(np.float32)
    out[:, 7] = orig_asprs
    buf = out.tobytes()

    return Response(
        content=buf,
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(len(x)),
            "Access-Control-Expose-Headers": "X-Point-Count",
        },
    )


@router.post("/{session_id}/{patch_id}/label", response_model=LabelResponse)
def label_points(session_id: str, patch_id: str, req: LabelRequest):
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found — was the patch extracted?")
    if not req.point_indices:
        raise HTTPException(400, "point_indices must not be empty")
    try:
        result = lm.apply_label(patch_id, req.point_indices, req.label_value, req.protect_classes)
    except IndexError as e:
        raise HTTPException(400, str(e))
    return LabelResponse(**result)


@router.post("/{session_id}/{patch_id}/apply-labels-bulk")
def apply_labels_bulk(session_id: str, patch_id: str, req: BulkLabelRequest):
    """Replace the entire label array with inference (or other bulk) results."""
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found — was the patch extracted?")
    try:
        result = lm.apply_labels_bulk(patch_id, np.array(req.labels, dtype=np.int32))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    return result


@router.post("/{session_id}/{patch_id}/segment-trees", response_model=SegmentTreesResponse)
def segment_trees(session_id: str, patch_id: str, req: SegmentTreesRequest):
    """CHM-based tree instance segmentation.

    Accepts per-point semantic labels (0=non-tree, 101=tree) and returns
    per-point instance labels (0=non-tree, 201+=individual tree instances).
    Does NOT mutate the in-memory label state — caller must apply-labels-bulk separately.
    """
    from services.tree_segmentor import segment_tree_instances

    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    labels_in = np.array(req.labels, dtype=np.int32)

    try:
        las = laspy.read(str(patch_path))
        x   = np.array(las.x,              dtype=np.float32)
        y   = np.array(las.y,              dtype=np.float32)
        z   = np.array(las.z,              dtype=np.float32)
        cls = np.array(las.classification, dtype=np.int32)
    except Exception as e:
        raise HTTPException(500, f"Failed to read patch: {e}")

    if len(labels_in) != len(x):
        raise HTTPException(
            400,
            f"Label array length {len(labels_in)} does not match patch point count {len(x)}",
        )

    try:
        new_labels, tree_count, peaks, seed_peaks = segment_tree_instances(
            x, y, z, labels_in, cls,
            cell_size=req.cell_size,
            smooth_window=req.smooth_window,
            smooth_sigma=req.smooth_sigma,
            min_height=req.min_height,
            min_distance=req.min_distance,
            max_radius=req.max_radius,
            min_tree_points=req.min_tree_points,
            min_crown_cells=req.min_crown_cells,
            dtm_grid=req.dtm_grid,
            dtm_rows=req.dtm_rows,
            dtm_cols=req.dtm_cols,
            dtm_x_min=req.dtm_x_min,
            dtm_y_min=req.dtm_y_min,
            dtm_x_range=req.dtm_x_range,
            dtm_y_range=req.dtm_y_range,
        )
    except Exception as e:
        raise HTTPException(500, f"Segmentation error: {e}")

    return SegmentTreesResponse(
        labels=new_labels.tolist(),
        tree_count=tree_count,
        peaks=peaks.tolist(),
        seed_peaks=seed_peaks.tolist(),
    )


@router.post("/{session_id}/{patch_id}/tree-metrics", response_model=TreeMetricsResponse)
def tree_metrics(session_id: str, patch_id: str, req: TreeMetricsRequest):
    """Compute per-tree crown metrics (height, crown width, area, etc.) from instance labels."""
    from services.tree_metrics import compute_tree_metrics

    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    try:
        las = laspy.read(str(patch_path))
        x   = np.array(las.x,              dtype=np.float32)
        y   = np.array(las.y,              dtype=np.float32)
        z   = np.array(las.z,              dtype=np.float32)
        cls = np.array(las.classification, dtype=np.int32)
    except Exception as e:
        raise HTTPException(500, f"Failed to read patch: {e}")

    labels_in = np.array(req.labels, dtype=np.int32)
    if len(labels_in) != len(x):
        raise HTTPException(400, f"Label count {len(labels_in)} != point count {len(x)}")

    try:
        metrics = compute_tree_metrics(
            x, y, z, labels_in, cls,
            cell_size=req.cell_size,
            dtm_grid=req.dtm_grid,
            dtm_rows=req.dtm_rows,
            dtm_cols=req.dtm_cols,
            dtm_x_min=req.dtm_x_min,
            dtm_y_min=req.dtm_y_min,
            dtm_x_range=req.dtm_x_range,
            dtm_y_range=req.dtm_y_range,
        )
    except Exception as e:
        raise HTTPException(500, f"Metrics error: {e}")

    return TreeMetricsResponse(trees=metrics)


@router.get("/{session_id}/{patch_id}/next-label")
def next_label(session_id: str, patch_id: str):
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found")
    return {"next_label": lm.get_next_label(patch_id)}


@router.get("/{session_id}/{patch_id}/colormap")
def get_patch_colormap(session_id: str, patch_id: str):
    """Return label color map for the current in-memory label state of a patch."""
    from services.projection import get_classification_color
    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found")
    unique, counts = np.unique(labels, return_counts=True)
    entries = []
    for code, count in zip(unique.tolist(), counts.tolist()):
        r, g, b = get_classification_color(int(code))
        entries.append({
            "value": int(code),
            "color": "#{:02x}{:02x}{:02x}".format(
                round(r * 255), round(g * 255), round(b * 255)
            ),
            "count": int(count),
        })
    return {"entries": entries}


@router.get("/{session_id}/{patch_id}/predict")
def run_prediction(session_id: str, patch_id: str, version: str = "v1"):
    """Run NN inference on a patch and return per-point predicted class labels.

    Query params:
        version: 'v1' (XYZ) | 'v2' (XYZ+cls) | 'v3' (XYZ+int) | 'v4' (XYZ+int+cls)
    """
    from services.predictor import predict, VALID_VERSIONS, _MODEL_CONFIGS
    if version not in VALID_VERSIONS:
        raise HTTPException(400, f"version must be one of {VALID_VERSIONS}")
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    try:
        cfg = _MODEL_CONFIGS[version]
        las = laspy.read(str(patch_path))
        labels = predict(
            np.array(las.x, dtype=np.float32),
            np.array(las.y, dtype=np.float32),
            np.array(las.z, dtype=np.float32),
            intensity      = np.array(las.intensity,       dtype=np.float32) if cfg['use_intensity']      else None,
            classification = np.array(las.classification,  dtype=np.float32) if cfg['use_classification'] else None,
            version=version,
            cache_key=f"{session_id}:{patch_id}:{version}",
        )
    except Exception as e:
        raise HTTPException(500, f"Inference error: {e}")
    return {"labels": labels.tolist()}

@router.get("/{session_id}/{patch_id}/predict-instances")
def run_prediction_instances(
    session_id: str, patch_id: str,
    version: str = "v1",
    bandwidth: float = 2.0,
    min_points: int = 100,
    embed_weight: float = 0.3,
    max_spread: float = 5.0,
):
    """Run 3-head instance segmentation inference on a patch.

    Uses the model's offset and embedding heads plus mean-shift clustering to
    produce per-point instance labels directly (no CHM watershed step).

    Returns: { labels: [int] }  — 0=non-tree, 201,202,… = individual tree instances
    """
    from services.predictor import predict_instances, VALID_VERSIONS, _MODEL_CONFIGS
    if version not in VALID_VERSIONS:
        raise HTTPException(400, f"version must be one of {VALID_VERSIONS}")
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    try:
        cfg = _MODEL_CONFIGS[version]
        las = laspy.read(str(patch_path))
        labels = predict_instances(
            np.array(las.x, dtype=np.float32),
            np.array(las.y, dtype=np.float32),
            np.array(las.z, dtype=np.float32),
            intensity      = np.array(las.intensity,      dtype=np.float32) if cfg['use_intensity']      else None,
            classification = np.array(las.classification, dtype=np.float32) if cfg['use_classification'] else None,
            version=version,
            bandwidth=bandwidth,
            min_points=min_points,
            embed_weight=embed_weight,
            max_spread=max_spread,
            cache_key=f"{session_id}:{patch_id}:{version}",
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Instance inference error: {e}")
    n_inst = int(np.unique(labels[labels > 0]).size) if (labels > 0).any() else 0
    return {"labels": labels.tolist(), "n_instances": n_inst}


@router.post("/{session_id}/{patch_id}/save", response_model=SaveResponse)
def save_patch(session_id: str, patch_id: str, req: SaveRequest):
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found")
    # Sanitize filename: only allow alphanumerics, dashes, underscores, dots
    safe_name = re.sub(r"[^\w\-.]", "_", req.output_filename)
    if not safe_name.lower().endswith((".las", ".laz")):
        safe_name += ".las"
    output_dir = get_session_dir(session_id) / "outputs" / patch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_name
    count = save_labeled_patch(patch_path, output_path, labels)
    return SaveResponse(
        download_url=f"/api/v1/patches/{session_id}/{patch_id}/download",
        output_filename=safe_name,
        point_count=count,
    )


@router.get("/{session_id}/{patch_id}/download")
def download_patch(session_id: str, patch_id: str):
    output_dir = get_session_dir(session_id) / "outputs" / patch_id
    if not output_dir.exists():
        raise HTTPException(404, "No saved output found")
    files = sorted(output_dir.glob("*.las"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise HTTPException(404, "No saved output found")
    latest = files[0]
    return FileResponse(
        str(latest),
        media_type="application/octet-stream",
        filename=latest.name,
    )

@router.post("/{session_id}/{patch_id}/auto-tune-segmentation", response_model=AutoTuneResponse)
def auto_tune_segmentation(session_id: str, patch_id: str, req: AutoTuneRequest):
    """Bayesian hyperparameter search for CHM tree segmentation.

    Runs req.n_trials Optuna trials and returns the best parameter set and quality score.
    Does NOT mutate any label state — caller applies results via the segment endpoint.
    """
    from services.seg_autotuner import autotune, _build_dtm_kwargs
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")
    labels_in = np.array(req.labels, dtype=np.int32)
    try:
        las = laspy.read(str(patch_path))
        x   = np.array(las.x,              dtype=np.float32)
        y   = np.array(las.y,              dtype=np.float32)
        z   = np.array(las.z,              dtype=np.float32)
        cls = np.array(las.classification, dtype=np.int32)
    except Exception as e:
        raise HTTPException(500, f"Failed to read patch: {e}")
    if len(labels_in) != len(x):
        raise HTTPException(400, f"Label count {len(labels_in)} != point count {len(x)}")
    dtm_kwargs = _build_dtm_kwargs(req.dict())
    try:
        result = autotune(x, y, z,
                          semantic_labels=labels_in,
                          original_cls=cls,
                          dtm_kwargs=dtm_kwargs,
                          n_trials=max(1, min(req.n_trials, 100)))
    except Exception as e:
        raise HTTPException(500, f"Auto-tune error: {e}")
    return AutoTuneResponse(**result)

@router.post("/{session_id}/{patch_id}/mark-training", response_model=MarkTrainingResponse)
def mark_training(session_id: str, patch_id: str, req: MarkTrainingRequest):
    """Save current in-memory label state as a ground-truth training example.

    semantic_labels (0/101) come from the frontend (store.semanticLabels).
    Ground-truth instance labels (201+) are read from the in-memory label state
    which reflects any manual corrections the user made after applying segmentation.
    """
    from services.training_store import save_training_example, count_training_examples

    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    semantic = np.array(req.semantic_labels, dtype=np.int32)

    if req.gt_instance_labels is not None:
        gt_labels = np.array(req.gt_instance_labels, dtype=np.int32)
        if len(gt_labels) != len(semantic):
            raise HTTPException(400, f"gt_instance_labels length {len(gt_labels)} != semantic_labels length {len(semantic)}")
    else:
        gt_labels = lm.get_labels(patch_id)
        if gt_labels is None:
            raise HTTPException(404, "Patch label state not found — extract and apply labels first")
        if len(semantic) != len(gt_labels):
            raise HTTPException(400, f"Semantic label count {len(semantic)} != patch size {len(gt_labels)}")

    try:
        las = laspy.read(str(patch_path))
        x   = np.array(las.x,              dtype=np.float32)
        y   = np.array(las.y,              dtype=np.float32)
        z   = np.array(las.z,              dtype=np.float32)
        cls = np.array(las.classification, dtype=np.int32)
    except Exception as e:
        raise HTTPException(500, f"Failed to read patch: {e}")

    eid = save_training_example(x, y, z, cls, semantic, gt_labels.copy(), patch_id)
    total   = count_training_examples()
    n_trees = int((gt_labels >= 201).sum())

    return MarkTrainingResponse(
        example_id=eid,
        n_points=int(len(x)),
        n_trees=n_trees,
        total_examples=total,
    )

@router.post("/{session_id}/{patch_id}/undo", response_model=UndoResponse)
def undo_label(session_id: str, patch_id: str):
    """Undo the last labelling operation on this patch."""
    if lm.get_labels(patch_id) is None:
        raise HTTPException(404, "Patch label state not found")
    result = lm.undo_last(patch_id)
    if result is None:
        return UndoResponse(had_operation=False)
    return UndoResponse(had_operation=True, **result)

@router.post("/{session_id}/{patch_id}/relabel-selection", response_model=RelabelSelectionResponse)
def relabel_selection(session_id: str, patch_id: str, req: RelabelSelectionRequest):
    """Within point_indices, replace from_label with to_label; all other labels are untouched."""
    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found")
    filtered = [i for i in req.point_indices if labels[i] == req.from_label]
    if not filtered:
        return RelabelSelectionResponse(applied=0, applied_indices=[])
    result = lm.apply_label(patch_id, filtered, req.to_label, protect_classes=False)
    return RelabelSelectionResponse(applied=result["points_labeled"], applied_indices=filtered)

@router.post("/{session_id}/{patch_id}/restore-from-client")
async def restore_patch_from_client(session_id: str, patch_id: str, request: Request):
    """Recreate the patch LAS file using point data sent from the browser.

    Used for recovery when the server-side patch file is lost (e.g. after a volume wipe)
    while the in-memory label state is still intact.

    Body: raw binary float32 array, 4 values per point: x, y, z, orig_classification.
    """
    body = await request.body()
    if not body or len(body) % 16 != 0:
        raise HTTPException(400, "Body must be a multiple of 16 bytes (4 float32 per point)")

    data = np.frombuffer(body, dtype=np.float32).reshape(-1, 4)
    x   = np.array(data[:, 0], dtype=np.float64)
    y   = np.array(data[:, 1], dtype=np.float64)
    z   = np.array(data[:, 2], dtype=np.float64)
    cls = np.array(data[:, 3], dtype=np.int32)

    patch_dir = get_session_dir(session_id) / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{patch_id}.las"

    new_las = laspy.LasData(header=laspy.LasHeader(point_format=0))
    new_las.x = x
    new_las.y = y
    new_las.z = z
    new_las.classification = np.clip(cls, 0, 255).astype(np.uint8)
    new_las.write(str(patch_path))

    return {"ok": True, "point_count": int(len(x))}


class DeletePointsRequest(BaseModel):
    point_indices: list[int]  # indices to DELETE (not keep)


@router.post("/{session_id}/{patch_id}/delete-points")
def delete_patch_points(session_id: str, patch_id: str, req: DeletePointsRequest):
    """Permanently delete points by index from the patch LAS file.

    The label manager is re-initialised with the surviving points so that
    subsequent label / save operations work correctly.  The NN inference
    cache for this patch is also cleared because point indices have changed.
    """
    patch_path = get_patch_path(session_id, patch_id)
    if not patch_path.exists():
        raise HTTPException(404, "Patch not found")

    labels = lm.get_labels(patch_id)
    if labels is None:
        raise HTTPException(404, "Patch label state not found — was the patch extracted?")

    las = laspy.read(str(patch_path))
    n = len(las.x)

    if not req.point_indices:
        raise HTTPException(400, "point_indices must not be empty")

    delete_set = set(req.point_indices)
    if any(i < 0 or i >= n for i in delete_set):
        raise HTTPException(400, f"Some indices are out of range [0, {n})")
    if len(delete_set) >= n:
        raise HTTPException(400, "Cannot delete all points from a patch")

    keep = np.ones(n, dtype=bool)
    for i in delete_set:
        keep[i] = False

    # Build new LAS preserving all standard and extra dimensions
    new_header = laspy.LasHeader(point_format=las.header.point_format, version=las.header.version)
    new_las = laspy.LasData(header=new_header)
    new_las.x = las.x[keep]
    new_las.y = las.y[keep]
    new_las.z = las.z[keep]
    new_las.classification = las.classification[keep]

    # Copy intensity if present
    try:
        new_las.intensity = las.intensity[keep]
    except Exception:
        pass

    # Copy extra dimensions (e.g. 'label' field written by save_labeled_patch)
    for dim_name in las.point_format.extra_dimension_names:
        try:
            setattr(new_las, dim_name, getattr(las, dim_name)[keep])
        except Exception:
            pass

    new_las.write(str(patch_path))

    # Re-initialise label manager with surviving point labels
    new_labels = labels[keep]
    orig_cls = np.array(new_las.classification, dtype=np.int32)
    lm.init_patch(patch_id, orig_cls, current_labels=new_labels)

    # Invalidate NN cache entries for this patch (indices have changed)
    try:
        from services.predictor import _NN_CACHE
        stale = [k for k in list(_NN_CACHE) if f":{patch_id}:" in k]
        for k in stale:
            _NN_CACHE.pop(k, None)
    except Exception:
        pass

    remaining = int(keep.sum())
    return {"ok": True, "deleted": len(delete_set), "remaining": remaining}

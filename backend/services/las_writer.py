import json
from pathlib import Path
import numpy as np
import laspy

# LAS point formats 0-5 store classification in 5 bits (0-31), too small for tree IDs
# (>= 100). Such files are upgraded to the LAS 1.4 format with the same attributes.
_UPGRADE_FORMAT = {0: 6, 1: 6, 2: 7, 3: 7, 4: 9, 5: 10}
_TREE_MIN = 100          # labels >= 100 are trees (101+ semantic, 201+ instances)
_TREE_CLASS = 5          # ASPRS "high vegetation" — tree points in `classification`
_CLS_MAX = 255           # classification is uint8 in formats 6-10


def save_labeled_patch(patch_path: Path, output_path: Path, label_array: np.ndarray,
                       units: dict | None = None) -> int:
    """Write a labelled patch that both the tool and the training import can read.

    - 'label' (int32 extra dimension): exact labels — the authoritative field
      (trees >= 100; tree IDs can exceed 255).
    - 'classification': real ASPRS classes. Tree points get 5 (high vegetation);
      every other point keeps its class (ground 2, building 6, …).
    - Everything else from the patch is kept: CRS (VLRs/EVLRs), return_number,
      number_of_returns, GPS time, RGB, …
    - A 'LabellingTool' VLR (record_id 1) holds JSON {"units", "metres_per_unit"} with
      the units the tool decided for the file. If the units are only "uncertain",
      they are left out, so the training import applies its own checks.
    """
    las = laspy.read(str(patch_path))
    if len(label_array) != len(las.points):
        raise ValueError(
            f"label_array length {len(label_array)} does not match "
            f"point count {len(las.points)}"
        )
    fmt = las.header.point_format.id
    if fmt in _UPGRADE_FORMAT:
        las = laspy.convert(las, point_format_id=_UPGRADE_FORMAT[fmt], file_version="1.4")

    labels = np.asarray(label_array, dtype=np.int32)
    if "label" not in las.point_format.extra_dimension_names:
        las.add_extra_dims([laspy.ExtraBytesParams(name="label", type=np.int32)])
    las.label = labels

    cls = np.where(labels >= _TREE_MIN, _TREE_CLASS, labels)
    las.classification = np.clip(cls, 0, _CLS_MAX).astype(np.uint8)

    info = {"label_field": "label", "tree_labels": ">= 100"}
    if units and units.get("source") != "uncertain":
        info["units"] = units.get("code")
        info["metres_per_unit"] = units.get("scale")
        info["units_source"] = units.get("source")
    las.header.vlrs = [v for v in las.header.vlrs
                       if not (getattr(v, "user_id", "") == "LabellingTool" and v.record_id == 1)]
    las.header.vlrs.append(laspy.VLR(
        user_id="LabellingTool", record_id=1, description="labels+units",
        record_data=json.dumps(info).encode("utf-8"),
    ))
    las.write(str(output_path))
    return len(labels)

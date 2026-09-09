from pathlib import Path
import numpy as np
import laspy


def save_labeled_patch(patch_path: Path, output_path: Path, label_array: np.ndarray) -> int:
    """Copy patch .las and write labels as both uint8 classification (compatibility)
    and a full int32 'label' extra bytes dimension (supports values > 255)."""
    las = laspy.read(str(patch_path))
    if len(label_array) != len(las.points):
        raise ValueError(
            f"label_array length {len(label_array)} does not match "
            f"point count {len(las.points)}"
        )
    if "label" not in las.point_format.extra_dimension_names:
        las.add_extra_dims([laspy.ExtraBytesParams(name="label", type=np.int32)])
    las.label = label_array.astype(np.int32)
    # Keep classification for compatibility with external tools.
    # LAS point format 0-5 uses only 5 bits (max 31), so we remap:
    #   0 = non-tree, 1 = tree/instance (any label > 0).
    # Full label values are preserved in the int32 'label' extra dimension above.
    compat_cls = np.where(label_array > 0, 1, 0).astype(np.uint8)
    las.classification = compat_cls
    las.write(str(output_path))
    return len(label_array)

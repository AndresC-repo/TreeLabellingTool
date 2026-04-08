from pathlib import Path
import numpy as np
import laspy


def save_labeled_patch(patch_path: Path, output_path: Path, label_array: np.ndarray) -> int:
    """
    Copy patch .las and overwrite the classification field with label_array.
    Returns the number of points written.
    """
    las = laspy.read(str(patch_path))
    las.classification = label_array.astype(np.uint8)
    las.write(str(output_path))
    return len(label_array)

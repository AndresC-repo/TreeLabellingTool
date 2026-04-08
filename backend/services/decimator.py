import numpy as np
import laspy
from config import DECIMATION_CHUNK_SIZE


def read_decimated(las_path, max_points: int, fields: list[str]) -> dict[str, np.ndarray]:
    """
    Read a .las file and return decimated arrays for the requested fields.
    Uses stride-based decimation across chunks to stay within max_points.
    """
    with laspy.open(las_path) as f:
        total = f.header.point_count
    stride = max(1, total // max_points)

    results = {field: [] for field in fields}
    with laspy.open(las_path) as f:
        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
            indices = np.arange(0, len(chunk), stride)
            for field in fields:
                arr = getattr(chunk, field)
                results[field].append(np.asarray(arr)[indices])

    return {k: np.concatenate(v) for k, v in results.items()}

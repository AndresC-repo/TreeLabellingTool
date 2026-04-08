import numpy as np
import laspy
from config import DECIMATION_CHUNK_SIZE


def read_decimated(las_path, max_points: int, fields: list[str]) -> tuple[dict[str, np.ndarray], int]:
    """
    Read a .las file and return (decimated arrays, total_point_count).
    Uses stride-based decimation across chunks to stay within max_points.
    Returns total count so callers can compute decimation ratio without reopening the file.
    """
    results = {field: [] for field in fields}
    total = 0
    with laspy.open(las_path) as f:
        total = f.header.point_count
        stride = max(1, total // max_points)
        for chunk in f.chunk_iterator(DECIMATION_CHUNK_SIZE):
            indices = np.arange(0, len(chunk), stride)
            for field in fields:
                arr = getattr(chunk, field)
                results[field].append(np.asarray(arr)[indices])

    return {k: np.concatenate(v) for k, v in results.items()}, total

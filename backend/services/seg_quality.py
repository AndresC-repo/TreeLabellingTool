from __future__ import annotations
import numpy as np


def quality_score(
    tree_metrics: list[dict],
    n_assigned: int,
    n_total_tree: int,
    x: "np.ndarray | None" = None,
    y: "np.ndarray | None" = None,
    new_labels: "np.ndarray | None" = None,
) -> float:
    """
    Geometric quality score for CHM tree instance segmentation. Range [0, 1].

    No ground truth required. Four components:

    coverage    (0.30) — fraction of semantic tree pts assigned to an instance.
                         Measures how little is left unclassified.

    ca_score    (0.25) — fraction of trees with plausible crown area (8–400 m²).
                         Filters both tiny over-split fragments and giant merged blobs.

    compactness (0.30) — spatial compactness of each crown.
                         Measured as the fraction of a crown's points that fall within
                         the radius expected for a circular crown of its area.
                         Elongated / fragmented / merged crowns score poorly.
                         Requires x, y, new_labels arrays; falls back to 1.0 if absent.

    consistency (0.15) — 1 / (1 + CV(crown_areas)).
                         Penalises mixed solutions where some crowns are huge and others
                         are tiny — typical sign of partial over/under-segmentation.
    """
    if n_total_tree == 0 or not tree_metrics:
        return 0.0

    coverage = n_assigned / n_total_tree

    cas = np.array([t["crown_area"] for t in tree_metrics], dtype=float)

    # Crown-area plausibility: tighter range, steeper penalty above 400 m²
    def _ca_ok(ca: float) -> float:
        if 8.0 <= ca <= 400.0:       return 1.0
        if ca < 2.0 or ca > 1500.0:  return 0.0
        if ca < 8.0:   return (ca - 2.0) / 6.0
        return 1.0 - (ca - 400.0) / 1100.0

    ca_score    = float(np.mean([_ca_ok(ca) for ca in cas]))
    ca_cv       = float(np.std(cas) / (np.mean(cas) + 1e-6))
    consistency = 1.0 / (1.0 + ca_cv)

    # Spatial compactness: what fraction of each crown's points lie within the
    # radius expected for a circular crown of that area?
    compactness = 1.0
    if x is not None and y is not None and new_labels is not None:
        comp_scores: list[float] = []
        for t in tree_metrics:
            mask = new_labels == t["id"]
            n_pts = int(mask.sum())
            if n_pts < 10:
                continue
            tx, ty = x[mask], y[mask]
            dists = np.sqrt((tx - tx.mean()) ** 2 + (ty - ty.mean()) ** 2)
            expected_r = float(np.sqrt(t["crown_area"] / np.pi))
            in_circle  = float((dists <= expected_r).mean())   # fraction inside expected radius
            # A real roughly-circular crown should have ~70 %+ of points inside.
            # Elongated/merged/fragmented crowns drop well below that.
            comp_scores.append(min(1.0, in_circle / 0.70))
        if comp_scores:
            compactness = float(np.mean(comp_scores))

    return (0.30 * coverage
            + 0.25 * ca_score
            + 0.30 * compactness
            + 0.15 * consistency)

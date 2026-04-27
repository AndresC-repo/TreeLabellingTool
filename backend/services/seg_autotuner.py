from __future__ import annotations
import logging
import numpy as np
import optuna
from sklearn.metrics import adjusted_rand_score

from services.tree_segmentor import segment_tree_instances
from services.tree_metrics   import compute_tree_metrics
from services.seg_quality    import quality_score

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger(__name__)


def _build_dtm_kwargs(req_dict: dict) -> dict:
    return {
        "dtm_grid":    req_dict.get("dtm_grid"),
        "dtm_rows":    req_dict.get("dtm_rows",    64),
        "dtm_cols":    req_dict.get("dtm_cols",    64),
        "dtm_x_min":   req_dict.get("dtm_x_min",   0.0),
        "dtm_y_min":   req_dict.get("dtm_y_min",   0.0),
        "dtm_x_range": req_dict.get("dtm_x_range", 1.0),
        "dtm_y_range": req_dict.get("dtm_y_range", 1.0),
    }

# DTM kwargs with no external grid — used for training patches which carry their own
# ASPRS class-2 ground points and don't need the frontend-supplied DTM.
_NO_DTM = {
    "dtm_grid": None, "dtm_rows": 64, "dtm_cols": 64,
    "dtm_x_min": 0.0, "dtm_y_min": 0.0,
    "dtm_x_range": 1.0, "dtm_y_range": 1.0,
}


def autotune(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    semantic_labels: np.ndarray,   # int32 (N,) — 0=non-tree, 101=tree
    original_cls: np.ndarray,      # int32 (N,) — ASPRS classification
    dtm_kwargs: dict,
    n_trials: int = 30,
) -> dict:
    """
    Bayesian hyperparameter search for CHM tree segmentation.

    Supervised mode (training examples exist):
      Objective = mean Adjusted Rand Index across all saved training patches.
      ARI is permutation-invariant — label numbers don't matter, only clustering.

    Geometric mode (no training examples yet):
      Objective = coverage + crown-area plausibility + compactness.
    """
    from services.training_store import load_all_training_examples
    training      = load_all_training_examples()
    use_supervised = len(training) > 0
    n_total_tree  = int((semantic_labels == 101).sum())

    logger.info("[autotuner] %s mode — %d training example(s)",
                "supervised" if use_supervised else "geometric", len(training))

    def objective(trial: optuna.Trial) -> float:
        params = {
            "cell_size":       trial.suggest_float("cell_size",       0.5,  3.0),
            "smooth_window":   trial.suggest_int(  "smooth_window",   1,    15),
            "smooth_sigma":    trial.suggest_float("smooth_sigma",    0.0,  3.0),
            "min_height":      trial.suggest_float("min_height",      0.5,  10.0),
            "min_distance":    trial.suggest_int(  "min_distance",    2,    30),
            "min_tree_points": trial.suggest_int(  "min_tree_points", 50,   2000, log=True),
            "min_crown_cells": trial.suggest_int(  "min_crown_cells", 10,   200),
            "max_radius":      trial.suggest_float("max_radius",      5.0,  40.0),
        }

        if use_supervised:
            ari_scores = []
            for ex in training:
                try:
                    pred, _, _, _ = segment_tree_instances(
                        ex["x"], ex["y"], ex["z"],
                        ex["semantic_labels"], ex["original_cls"],
                        **params, **_NO_DTM)
                except Exception as e:
                    logger.debug("Trial %d ex %s seg failed: %s", trial.number, ex["id"], e)
                    return 0.0

                tree_mask = ex["semantic_labels"] == 101
                if not tree_mask.any():
                    continue
                ari = float(adjusted_rand_score(
                    ex["gt_instance_labels"][tree_mask],
                    pred[tree_mask]))
                ari_scores.append(ari)
                logger.debug("Trial %d ex %s: ARI=%.4f", trial.number, ex["id"], ari)

            score = float(np.mean(ari_scores)) if ari_scores else 0.0
            logger.debug("Trial %d: mean ARI=%.4f", trial.number, score)
            return score

        else:
            try:
                new_labels, _, _, _ = segment_tree_instances(
                    x, y, z, semantic_labels, original_cls, **params, **dtm_kwargs)
            except Exception as e:
                logger.debug("Trial %d seg failed: %s", trial.number, e)
                return 0.0
            n_assigned = int((new_labels >= 201).sum())
            try:
                metrics = compute_tree_metrics(
                    x, y, z, new_labels, original_cls,
                    cell_size=params["cell_size"], **dtm_kwargs)
            except Exception:
                metrics = []
            return quality_score(metrics, n_assigned, n_total_tree, x, y, new_labels)

    study = optuna.create_study(
        study_name="tree_seg_global",
        storage="sqlite:////app/storage/optuna.db",
        load_if_exists=True,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    logger.info("[autotuner] best=%.4f after %d trials | %s",
                best.value, n_trials, best.params)

    return {
        "best_params": {
            "cell_size":       round(best.params["cell_size"],       2),
            "smooth_window":   int(best.params["smooth_window"]),
            "smooth_sigma":    round(best.params["smooth_sigma"],    2),
            "min_height":      round(best.params["min_height"],      2),
            "min_distance":    int(best.params["min_distance"]),
            "min_tree_points": int(best.params["min_tree_points"]),
            "min_crown_cells": int(best.params["min_crown_cells"]),
            "max_radius":      round(best.params["max_radius"],      1),
        },
        "best_score": round(float(best.value), 4),
        "n_trials":   n_trials,
        "mode":       "supervised" if use_supervised else "geometric",
    }

"""PERMANOVA (distance-based multivariate ANOVA) with optional covariates/block."""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler


def _prepare_X(df: pd.DataFrame, samples: List[str]):
    X = df[samples].T.values.copy()
    for col in range(X.shape[1]):
        vals = X[:, col]
        pos = vals[np.isfinite(vals) & (vals > 0)]
        fill = float(np.min(pos) / 2) if len(pos) else 1e-6
        vals[~np.isfinite(vals)] = fill
        vals[vals <= 0] = fill
    # use log10 abundance for ecological distances
    X = np.log10(X)
    return StandardScaler().fit_transform(X).copy()


def _gower_center(D: np.ndarray) -> np.ndarray:
    D2 = D ** 2
    n = D2.shape[0]
    row_mean = D2.mean(axis=1, keepdims=True)
    col_mean = D2.mean(axis=0, keepdims=True)
    grand_mean = D2.mean()
    G = -0.5 * (D2 - row_mean - col_mean + grand_mean)
    return G


def _projection_matrix(X: np.ndarray) -> np.ndarray:
    """H = X (X^T X)^+ X^T."""
    XtX = X.T @ X
    try:
        inv = np.linalg.inv(XtX)
    except Exception:
        inv = np.linalg.pinv(XtX)
    return X @ inv @ X.T


def _ss_model(G: np.ndarray, H: np.ndarray) -> float:
    return float(np.trace(H @ G))


def permanova_analysis(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    group_a: str,
    group_b: str,
    covariates: Optional[Dict[str, float]] = None,
    block: Optional[Dict[str, str]] = None,
    metric: str = "braycurtis",
    n_perm: int = 999,
) -> Dict[str, Any]:
    samples = sorted([s for s, g in sample_meta.items() if g in (group_a, group_b)])
    if len(samples) < 4 or len({sample_meta[s] for s in samples}) < 2:
        return {"error": "Need at least two samples per group for PERMANOVA."}

    y = np.array([1 if sample_meta[s] == group_b else 0 for s in samples])
    X = _prepare_X(df, samples)
    try:
        D = pairwise_distances(X, metric=metric)
    except Exception:
        D = squareform(pdist(X, metric="euclidean"))
    G = _gower_center(D)
    n = len(samples)
    total_ss = float(np.trace(G))

    # Build base design matrix (block + covariates)
    design_cols = []
    col_names = []

    if block:
        block_values = {s: block.get(s, "unknown") for s in samples}
        block_levels = sorted(set(block_values.values()))
        if len(block_levels) > 1 and len(block_levels) < n:
            for level in block_levels[:-1]:  # drop-last dummy
                col = np.array([1.0 if block_values[s] == level else 0.0 for s in samples])
                design_cols.append(col)
                col_names.append(f"block_{level}")

    if covariates:
        for cov_name, cov_vals in covariates.items():
            col = np.array([float(cov_vals.get(s, 0.0)) for s in samples])
            if np.std(col) > 0:
                design_cols.append(col)
                col_names.append(cov_name)

    # Full model including group
    group_col = y.astype(float)
    X_full = np.column_stack(design_cols + [group_col]) if design_cols else group_col[:, None]
    H_full = _projection_matrix(X_full)
    ss_full = _ss_model(G, H_full)
    rank_full = np.linalg.matrix_rank(X_full)

    if design_cols:
        X_base = np.column_stack(design_cols)
        H_base = _projection_matrix(X_base)
        ss_base = _ss_model(G, H_base)
        rank_base = np.linalg.matrix_rank(X_base)
    else:
        ss_base = 0.0
        rank_base = 0

    ss_group = ss_full - ss_base
    df_group = rank_full - rank_base
    df_res = n - 1 - rank_full
    ss_res = total_ss - ss_full
    pseudo_f = (ss_group / df_group) / (ss_res / df_res) if df_group > 0 and df_res > 0 and ss_res > 0 else 0.0

    rng = np.random.default_rng(42)
    perm_f = []
    for _ in range(n_perm):
        y_perm = rng.permutation(y)
        group_perm = y_perm.astype(float)
        X_perm = np.column_stack(design_cols + [group_perm]) if design_cols else group_perm[:, None]
        H_perm = _projection_matrix(X_perm)
        ss_perm_full = _ss_model(G, H_perm)
        ss_perm_group = ss_perm_full - ss_base
        rank_perm = np.linalg.matrix_rank(X_perm)
        df_perm_group = rank_perm - rank_base
        df_perm_res = n - 1 - rank_perm
        ss_perm_res = total_ss - ss_perm_full
        f_perm = (ss_perm_group / df_perm_group) / (ss_perm_res / df_perm_res) if df_perm_group > 0 and df_perm_res > 0 and ss_perm_res > 0 else 0.0
        perm_f.append(float(f_perm))

    p_value = (np.sum(np.array(perm_f) >= pseudo_f) + 1) / (n_perm + 1)

    return {
        "method": "PERMANOVA",
        "metric": metric,
        "n_samples": n,
        "df_group": int(df_group),
        "df_res": int(df_res),
        "ss_group": float(ss_group),
        "ss_res": float(ss_res),
        "pseudo_f": float(pseudo_f),
        "p_value": float(p_value),
        "r2": float(ss_group / total_ss) if total_ss > 0 else 0.0,
        "perm_f": perm_f,
        "samples": samples,
        "groups": [group_a if g == 0 else group_b for g in y],
    }

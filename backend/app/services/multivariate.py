"""Multivariate discriminant analysis: PLS-DA and OPLS-DA.

Provides scores, loadings, VIP scores, model performance (R2X, R2Y, Q2Y,
accuracy), permutation tests and S-plots.
"""

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.cross_decomposition import PLSRegression
from sklearn.metrics import r2_score, accuracy_score, roc_auc_score
from sklearn.model_selection import cross_val_predict, KFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
import logging

logger = logging.getLogger(__name__)


def _encode_groups(sample_meta: Dict[str, str], group_a: str, group_b: str):
    samples = sorted([s for s, g in sample_meta.items() if g in (group_a, group_b)])
    y = np.array([1 if sample_meta[s] == group_b else 0 for s in samples])
    return samples, y


def _prepare_X(df: pd.DataFrame, samples: List[str]):
    X = df[samples].T.values.copy()
    # impute missing per feature with half-min positive
    for col in range(X.shape[1]):
        vals = X[:, col]
        pos = vals[np.isfinite(vals) & (vals > 0)]
        fill = float(np.min(pos) / 2) if len(pos) else 1e-6
        vals[~np.isfinite(vals)] = fill
        vals[vals <= 0] = fill
    return StandardScaler().fit_transform(X).copy()


def _vip_scores(pls: PLSRegression, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute VIP scores for PLS components."""
    n_features = X.shape[1]
    n_components = pls.n_components
    # x_weights_ are the PLS weights (W) for X; normalize per component
    w = pls.x_weights_.copy()
    for a in range(n_components):
        norm = np.linalg.norm(w[:, a])
        if norm > 0:
            w[:, a] /= norm
    # explained sum of squares for y per component
    t = pls.x_scores_
    ssy = np.zeros(n_components)
    for a in range(n_components):
        # predicted Y contribution from component a
        y_pred_a = t[:, a][:, None] @ pls.y_loadings_[:, a][None, :]
        ssy[a] = float(np.sum(y_pred_a ** 2))
    denom = np.sum(ssy)
    if denom == 0:
        return np.zeros(n_features)
    vip = np.sqrt(n_features * np.sum(ssy * (w ** 2), axis=1) / denom)
    return vip


def _permutation_scores(
    X: np.ndarray,
    y: np.ndarray,
    n_components: int,
    n_perm: int = 100,
) -> Tuple[List[float], List[float], List[float]]:
    rng = np.random.RandomState(42)
    r2s, q2s, accs = [], [], []
    for _ in range(n_perm):
        y_perm = rng.permutation(y)
        try:
            pls = PLSRegression(n_components=n_components, scale=False)
            pls.fit(X, y_perm)
            y_pred = pls.predict(X).ravel()
            r2 = r2_score(y_perm, y_pred)
            y_cv = cross_val_predict(PLSRegression(n_components=n_components, scale=False), X, y_perm, cv=KFold(n_splits=min(5, len(y)), shuffle=True, random_state=0))
            q2 = r2_score(y_perm, y_cv)
            acc = accuracy_score(y_perm, (y_pred > 0.5).astype(int))
        except Exception as _exc:
            logger.exception("Unexpected error")
            r2 = q2 = acc = 0.0
        r2s.append(float(r2))
        q2s.append(float(q2))
        accs.append(float(acc))
    return r2s, q2s, accs


def _model_performance(
    X: np.ndarray,
    y: np.ndarray,
    max_components: int,
) -> List[Dict[str, float]]:
    rows = []
    n_splits = min(5, len(y))
    cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    for n in range(1, max_components + 1):
        try:
            pls = PLSRegression(n_components=n, scale=False)
            pls.fit(X, y)
            y_pred = pls.predict(X).ravel()
            y_cv = cross_val_predict(PLSRegression(n_components=n, scale=False), X, y, cv=cv)
            r2 = float(r2_score(y, y_pred))
            q2 = float(r2_score(y, y_cv))
            acc = float(accuracy_score(y, (y_pred > 0.5).astype(int)))
            # R2X cumulative
            X_pred = pls.x_scores_ @ pls.x_loadings_.T
            r2x = float(1 - np.sum((X - X_pred) ** 2) / np.sum((X - X.mean(axis=0)) ** 2))
            rows.append({"n_components": n, "r2y": r2, "q2y": q2, "accuracy": acc, "r2x": r2x})
        except Exception as _exc:
            logger.exception("Unexpected error")
            rows.append({"n_components": n, "r2y": 0.0, "q2y": 0.0, "accuracy": 0.0, "r2x": 0.0})
    return rows


def pls_da_analysis(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    group_a: str,
    group_b: str,
    n_components: int = 2,
    n_perm: int = 100,
    feature_metadata: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    samples, y = _encode_groups(sample_meta, group_a, group_b)
    if len(samples) < 4 or len(np.unique(y)) < 2:
        return {"error": "Need at least two samples per group for PLS-DA."}

    X = _prepare_X(df, samples)
    n_components = min(n_components, X.shape[0] - 1, X.shape[1])
    if n_components < 1:
        return {"error": "Not enough features/samples for PLS-DA."}

    pls = PLSRegression(n_components=n_components, scale=False)
    pls.fit(X, y)

    scores = pls.x_scores_
    loadings = pls.x_loadings_
    y_pred = pls.predict(X).ravel()
    y_pred_class = (y_pred > 0.5).astype(int)

    feat_ids = [m.get("feature_id", i) for i, m in enumerate(feature_metadata or [])]
    if not feat_ids:
        feat_ids = [f"Feature {i}" for i in range(X.shape[1])]

    vip = _vip_scores(pls, X, y)
    top_idx = np.argsort(vip)[::-1][:min(20, len(vip))]
    vip_table = [
        {"feature": feat_ids[i], "vip": float(vip[i]), "loading_pc1": float(loadings[i, 0])}
        for i in top_idx
    ]

    performance = _model_performance(X, y, n_components)
    r2s, q2s, accs = _permutation_scores(X, y, n_components, n_perm)

    cm = {"true_0_pred_0": 0, "true_0_pred_1": 0, "true_1_pred_0": 0, "true_1_pred_1": 0}
    for a, p in zip(y, y_pred_class):
        cm[f"true_{int(a)}_pred_{int(p)}"] += 1

    return {
        "method": "pls_da",
        "samples": samples,
        "groups": [group_a, group_b],
        "y": y.tolist(),
        "y_pred": y_pred.tolist(),
        "scores": scores.tolist(),
        "explained_variance_x": (pls.explained_variance_x_ * 100).tolist() if hasattr(pls, "explained_variance_x_") else [],
        "explained_variance_y": (pls.explained_variance_y_ * 100).tolist() if hasattr(pls, "explained_variance_y_") else [],
        "loadings": loadings.tolist(),
        "feature_ids": feat_ids,
        "vip": vip.tolist(),
        "vip_table": vip_table,
        "performance": performance,
        "r2y": float(r2_score(y, y_pred)),
        "q2y": float(r2_score(y, cross_val_predict(PLSRegression(n_components=n_components, scale=False), X, y, cv=KFold(n_splits=min(5, len(y)), shuffle=True, random_state=42)))),
        "accuracy": float(accuracy_score(y, y_pred_class)),
        "auc": float(roc_auc_score(y, y_pred)) if len(np.unique(y)) == 2 else None,
        "confusion": cm,
        "permutation": {"r2y": r2s, "q2y": q2s, "accuracy": accs},
        "model": pls,
    }


def opls_da_analysis(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    group_a: str,
    group_b: str,
    n_orth: int = 1,
    n_perm: int = 100,
    feature_metadata: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """OPLS-DA: one predictive component + n_orth orthogonal components.

    Orthogonal components are extracted as the dominant eigenvectors of the
    X-variance that is constrained to be uncorrelated with y.
    """
    samples, y = _encode_groups(sample_meta, group_a, group_b)
    if len(samples) < 4 or len(np.unique(y)) < 2:
        return {"error": "Need at least two samples per group for OPLS-DA."}

    X = _prepare_X(df, samples)
    n_features = X.shape[1]
    feat_ids = [m.get("feature_id", i) for i, m in enumerate(feature_metadata or [])]
    if not feat_ids:
        feat_ids = [f"Feature {i}" for i in range(n_features)]

    n_orth = min(n_orth, X.shape[0] - 2, X.shape[1] - 1)
    if n_orth < 0:
        n_orth = 0

    yc = y - y.mean()
    T_orth = []
    P_orth = []
    W_orth = []
    X_o = X.copy()

    # orthogonal signal correction
    for _ in range(n_orth):
        # maximize ||X w||^2 subject to Xw orthogonal to y (yc^T X w = 0)
        H_y = np.outer(yc, yc) / (yc @ yc) if (yc @ yc) > 0 else np.zeros((len(yc), len(yc)))
        M = X_o.T @ (X_o - H_y @ X_o)
        try:
            eigvals, eigvecs = np.linalg.eigh(M)
            w_o = eigvecs[:, np.argmax(eigvals)]
        except Exception as _exc:
            logger.exception("Unexpected error")
            break
        # ensure sign convention points toward maximal variance
        t_o = X_o @ w_o
        if np.linalg.norm(t_o) == 0:
            break
        p_o = X_o.T @ t_o / (t_o @ t_o)
        T_orth.append(t_o)
        P_orth.append(p_o)
        W_orth.append(w_o)
        X_o = X_o - np.outer(t_o, p_o)

    # predictive component on residual X
    w_p = X_o.T @ yc
    norm = np.linalg.norm(w_p)
    if norm > 0:
        w_p /= norm
    t_p = X_o @ w_p
    p_p = X_o.T @ t_p / (t_p @ t_p) if (t_p @ t_p) > 0 else np.zeros(n_features)
    c = (yc @ t_p) / (t_p @ t_p) if (t_p @ t_p) > 0 else 0.0

    y_pred = t_p * c + y.mean()
    y_pred_class = (y_pred > 0.5).astype(int)

    # S-plot: predictive loading vs correlation to predictive score
    pcorr = np.array([np.corrcoef(X_o[:, j], t_p)[0, 1] if np.std(X_o[:, j]) > 0 and np.std(t_p) > 0 else 0.0 for j in range(n_features)])
    splot = [{"feature": feat_ids[i], "p_pred": float(p_p[i]), "p_corr": float(pcorr[i])} for i in range(n_features)]

    # VIP-like metric for OPLS: p_pred-based contribution
    vip = np.sqrt(n_features * (p_p ** 2) / max(np.sum(p_p ** 2), 1e-12))
    top_idx = np.argsort(np.abs(p_p))[::-1][:min(20, n_features)]
    vip_table = [{"feature": feat_ids[i], "vip": float(vip[i]), "p_pred": float(p_p[i])} for i in top_idx]

    # Orthogonal distances for diagnostics (sum of squared orthogonal scores)
    orth_dist = np.zeros(len(y))
    for t_o in T_orth:
        orth_dist += t_o ** 2
    orth_dist = np.sqrt(orth_dist)
    pred_score = t_p

    performance = _model_performance(X, y, 1)
    r2s, q2s, accs = _permutation_scores(X, y, 1, n_perm)

    cm = {"true_0_pred_0": 0, "true_0_pred_1": 0, "true_1_pred_0": 0, "true_1_pred_1": 0}
    for a, p in zip(y, y_pred_class):
        cm[f"true_{int(a)}_pred_{int(p)}"] += 1

    return {
        "method": "opls_da",
        "samples": samples,
        "groups": [group_a, group_b],
        "y": y.tolist(),
        "y_pred": y_pred.tolist(),
        "predictive_score": pred_score.tolist(),
        "orthogonal_scores": [t.tolist() for t in T_orth],
        "orthogonal_distance": orth_dist.tolist(),
        "p_pred": p_p.tolist(),
        "p_orth": [p.tolist() for p in P_orth],
        "w_p": w_p.tolist(),
        "w_orth": [w.tolist() for w in W_orth],
        "vip": vip.tolist(),
        "vip_table": vip_table,
        "splot": splot,
        "feature_ids": feat_ids,
        "performance": performance,
        "r2y": float(r2_score(y, y_pred)),
        "q2y": float(r2_score(y, cross_val_predict(PLSRegression(n_components=1, scale=False), X, y, cv=KFold(n_splits=min(5, len(y)), shuffle=True, random_state=42)))),
        "accuracy": float(accuracy_score(y, y_pred_class)),
        "auc": float(roc_auc_score(y, y_pred)) if len(np.unique(y)) == 2 else None,
        "confusion": cm,
        "permutation": {"r2y": r2s, "q2y": q2s, "accuracy": accs},
    }

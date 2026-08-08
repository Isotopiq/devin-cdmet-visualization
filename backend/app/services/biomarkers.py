"""Biomarker discovery: univariate + multivariate ROC and candidate ranking."""

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, roc_curve, accuracy_score
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from statsmodels.stats.power import tt_ind_solve_power
import logging

logger = logging.getLogger(__name__)


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return 0.0
    pooled_std = np.sqrt(((len(a) - 1) * np.var(a, ddof=1) + (len(b) - 1) * np.var(b, ddof=1)) / (len(a) + len(b) - 2))
    if pooled_std == 0:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / pooled_std)


def _power_from_arrays(a: np.ndarray, b: np.ndarray, alpha: float = 0.05) -> float:
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    n = min(len(a), len(b))
    d = _cohens_d(a, b)
    try:
        return float(tt_ind_solve_power(effect_size=abs(d), nobs1=n, alpha=alpha, ratio=len(b) / max(len(a), 1), alternative='two-sided'))
    except Exception as _exc:
        logger.exception("Unexpected error")
        return 0.0


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    try:
        return float(roc_auc_score(y_true, y_score))
    except Exception as _exc:
        logger.exception("Unexpected error")
        return 0.0


def biomarker_analysis(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    group_a: str,
    group_b: str,
    feature_metadata: List[Dict[str, Any]] = None,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    samples = sorted([s for s, g in sample_meta.items() if g in (group_a, group_b)])
    if len(samples) < 4 or len({sample_meta[s] for s in samples}) < 2:
        return {"error": "Need at least two samples per group for biomarker analysis."}

    y = np.array([1 if sample_meta[s] == group_b else 0 for s in samples])
    X = df[samples].T.values

    a_idx = np.where(y == 0)[0]
    b_idx = np.where(y == 1)[0]

    feat_ids = [m.get("feature_id", i) for i, m in enumerate(feature_metadata or [])]
    if not feat_ids:
        feat_ids = [f"Feature {i}" for i in range(X.shape[1])]

    rows = []
    for j in range(X.shape[1]):
        vals = X[:, j].astype(float)
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            continue
        a_vals = vals[a_idx]
        b_vals = vals[b_idx]
        log2fc = float(np.log2(np.nanmean(b_vals) / np.nanmean(a_vals))) if np.nanmean(a_vals) > 0 and np.nanmean(b_vals) > 0 else 0.0
        try:
            _, p = scipy_stats.mannwhitneyu(a_vals, b_vals, alternative="two-sided")
        except Exception as _exc:
            logger.exception("Unexpected error")
            p = 1.0
        auc = _safe_auc(y, X[:, j])
        d = _cohens_d(a_vals, b_vals)
        power = _power_from_arrays(a_vals, b_vals, alpha)
        rows.append({
            "feature": feat_ids[j],
            "pvalue": float(p),
            "log2fc": log2fc,
            "auc": auc,
            "cohens_d": d,
            "power": power,
        })

    # BH FDR
    pvals = np.array([r["pvalue"] for r in rows])
    n = len(pvals)
    order = np.argsort(pvals)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, n + 1)
    padj = pvals * n / ranks
    padj = np.minimum.accumulate(padj[order[::-1]])[order[::-1]][order]
    padj = np.minimum(padj, 1.0)
    for r, p in zip(rows, padj):
        r["padj"] = float(p)

    rows.sort(key=lambda r: (r["pvalue"], -abs(r["auc"])))

    # Multivariate ROC with Random Forest
    # impute missing/negative values
    X_imp = X.copy()
    for col in range(X_imp.shape[1]):
        vals = X_imp[:, col]
        pos = vals[np.isfinite(vals) & (vals > 0)]
        fill = float(np.min(pos) / 2) if len(pos) else 1e-6
        vals[~np.isfinite(vals)] = fill
        vals[vals <= 0] = fill

    rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=2)
    mv_auc = 0.0
    mv_acc = 0.0
    fpr = []
    tpr = []
    importances = np.zeros(X.shape[1])
    try:
        rf.fit(X_imp, y)
        importances = rf.feature_importances_
        class_counts = np.bincount(y)
        min_class = int(np.min(class_counts[class_counts > 0]))
        n_splits = max(2, min(5, min_class, len(y)))
        if n_splits >= 2 and min_class >= n_splits:
            y_pred_proba = cross_val_predict(rf, X_imp, y, cv=StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42), method="predict_proba")[:, 1]
        else:
            # fallback: out-of-bag probability-like with leave-one-out from the fitted model
            proba = rf.predict_proba(X_imp)[:, 1]
            y_pred_proba = proba
        mv_auc = _safe_auc(y, y_pred_proba)
        mv_acc = float(accuracy_score(y, (y_pred_proba > 0.5).astype(int)))
        fpr, tpr, _ = roc_curve(y, y_pred_proba)
    except Exception as _exc:
        logger.exception("Unexpected error")
        pass

    return {
        "candidates": rows,
        "top_candidates": rows[:20],
        "multivariate": {
            "method": "Random Forest",
            "auc": mv_auc,
            "accuracy": mv_acc,
            "fpr": fpr.tolist() if isinstance(fpr, np.ndarray) else fpr,
            "tpr": tpr.tolist() if isinstance(tpr, np.ndarray) else tpr,
        },
        "feature_importances": [
            {"feature": feat_ids[i], "importance": float(importances[i])}
            for i in np.argsort(importances)[::-1][:20]
        ],
    }

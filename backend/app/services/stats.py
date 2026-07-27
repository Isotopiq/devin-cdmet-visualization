import math
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe


def _safe_log2fc(mean_a: float, mean_b: float, eps: float = 1e-12) -> float:
    """Compute a robust log2 fold change; returns None when the ratio is not positive/finite."""
    if mean_a is None or mean_b is None:
        return None
    if mean_a == 0 and mean_b == 0:
        return 0.0
    denom = mean_a + eps
    numer = mean_b + eps
    if denom == 0:
        return None
    ratio = numer / denom
    if not math.isfinite(ratio) or ratio <= 0:
        return None
    return float(np.log2(ratio))


def run_statistical_test(dataset: models.Dataset, req: schemas.StatsRequest):
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata
    groups = {}
    for col, group in sample_meta.items():
        groups.setdefault(group, []).append(col)

    group_a_cols = groups.get(req.group_a, []) if req.group_a else []
    group_b_cols = groups.get(req.group_b, []) if req.group_b else []

    results = []
    for idx in df.index:
        a = df.loc[idx, group_a_cols].dropna().values if group_a_cols else np.array([])
        b = df.loc[idx, group_b_cols].dropna().values if group_b_cols else np.array([])
        if len(a) < 2 or len(b) < 2:
            continue

        stat = None
        p = None
        try:
            if req.test == "t_test":
                stat, p = stats.ttest_ind(a, b, equal_var=True)
            elif req.test == "welch":
                stat, p = stats.ttest_ind(a, b, equal_var=False)
            elif req.test == "mannwhitney":
                stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            elif req.test == "paired":
                if len(a) == len(b):
                    stat, p = stats.ttest_rel(a, b)
            elif req.test == "wilcoxon":
                if len(a) == len(b):
                    stat, p = stats.wilcoxon(a, b)
            elif req.test == "anova":
                arrays = [df.loc[idx, cols].dropna().values for cols in groups.values() if len(cols) > 1]
                if len(arrays) >= 2:
                    stat, p = stats.f_oneway(*arrays)
            elif req.test == "kruskal":
                arrays = [df.loc[idx, cols].dropna().values for cols in groups.values() if len(cols) > 1]
                if len(arrays) >= 2:
                    stat, p = stats.kruskal(*arrays)
        except Exception:
            continue

        if p is None or not math.isfinite(p):
            continue

        mean_a = float(np.mean(a))
        mean_b = float(np.mean(b))
        log2fc = _safe_log2fc(mean_a, mean_b)

        result = {
            "feature_id": dataset.feature_metadata[idx].get("feature_id", idx) if idx < len(dataset.feature_metadata) else idx,
            "statistic": _to_json_safe(stat),
            "pvalue": _to_json_safe(p),
            "mean_a": _to_json_safe(mean_a),
            "mean_b": _to_json_safe(mean_b),
            "log2fc": _to_json_safe(log2fc),
        }
        results.append(result)

    pvals = [r["pvalue"] for r in results if r["pvalue"] is not None]
    if pvals and req.multiple_testing:
        try:
            _, padj, _, _ = multipletests(pvals, alpha=req.alpha, method=req.multiple_testing)
            pi = 0
            for r in results:
                if r["pvalue"] is not None:
                    r["padj"] = _to_json_safe(padj[pi])
                    pi += 1
        except Exception:
            for r in results:
                if r["pvalue"] is not None:
                    r["padj"] = r["pvalue"]
    else:
        for r in results:
            if r["pvalue"] is not None:
                r["padj"] = r["pvalue"]

    return {"test": req.test, "n_features": len(results), "results": results}

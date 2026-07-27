import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from app import models, schemas
from app.services.preprocessing import to_dataframe


def run_statistical_test(dataset: models.Dataset, req: schemas.StatsRequest):
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata
    groups = {}
    for col, group in sample_meta.items():
        groups.setdefault(group, []).append(col)

    group_a_cols = req.group_a and groups.get(req.group_a, [])
    group_b_cols = req.group_b and groups.get(req.group_b, [])

    results = []
    for idx in df.index:
        a = df.loc[idx, group_a_cols].dropna().values if group_a_cols else np.array([])
        b = df.loc[idx, group_b_cols].dropna().values if group_b_cols else np.array([])
        if len(a) < 2 or len(b) < 2:
            continue

        stat = None
        p = None
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

        if p is not None and not np.isnan(p):
            results.append({
                "feature_id": dataset.feature_metadata[idx].get("feature_id", idx),
                "statistic": float(stat),
                "pvalue": float(p),
                "mean_a": float(np.mean(a)),
                "mean_b": float(np.mean(b)),
                "log2fc": float(np.log2(np.mean(b) / np.mean(a))) if np.mean(a) > 0 else None,
            })

    pvals = [r["pvalue"] for r in results]
    if pvals and req.multiple_testing:
        try:
            _, padj, _, _ = multipletests(pvals, alpha=req.alpha, method=req.multiple_testing)
            for r, pa in zip(results, padj):
                r["padj"] = float(pa)
        except Exception:
            for r in results:
                r["padj"] = r["pvalue"]

    return {"test": req.test, "n_features": len(results), "results": results}

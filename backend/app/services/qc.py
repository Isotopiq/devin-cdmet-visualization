import json
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats
from sklearn.decomposition import PCA as PCA_SKL
from sklearn.preprocessing import StandardScaler

from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe
from app.services.plots import _merge_style, _group_color_map, _apply_base_layout, generate_plot


def _safe_log10(values):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log10(np.where(np.array(values) > 0, np.array(values), np.nan))


def _as_floats(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(pd.to_numeric, errors="coerce")


def _compute_mahalanobis_outliers(scores: np.ndarray, quantile: float = 0.99) -> np.ndarray:
    if len(scores) < 3:
        return np.zeros(len(scores), dtype=bool)
    mean = scores.mean(axis=0)
    cov = np.cov(scores, rowvar=False)
    if cov.ndim < 2 or cov.shape[0] < 2:
        cov = np.atleast_2d(np.var(scores, axis=0, ddof=1))
    try:
        inv_cov = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        return np.zeros(len(scores), dtype=bool)
    centered = scores - mean
    distances = np.array([x @ inv_cov @ x for x in centered])
    # chi2 threshold for 2 df at given quantile
    threshold = stats.chi2.ppf(quantile, df=2)
    return distances > threshold


def qc_analysis(dataset: models.Dataset, style: dict | None = None) -> dict:
    style = _merge_style(style)
    df = _as_floats(to_dataframe(dataset))
    sample_meta = dataset.sample_metadata or {}
    feature_meta = dataset.feature_metadata or []

    samples = list(df.columns)
    groups = [sample_meta.get(s, "Unknown") for s in samples]
    group_order = sorted(set(groups))
    if "Unknown" in group_order:
        group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
    color_map = _group_color_map(style, group_order)

    # Basic metrics
    num_features, num_samples = df.shape
    missing = df.isna().sum()
    missing_pct = (missing / num_features * 100).round(2).to_dict()
    total_missing_pct = round(float(df.isna().sum().sum() / df.size * 100), 2)

    tic = df.sum(numeric_only=True, skipna=True).round(2).to_dict()
    log2_tic = {s: round(float(np.log2(v)) if v and v > 0 else 0.0, 2) for s, v in tic.items()}
    detected = (df.notna().sum(axis=0)).to_dict()

    # Group CV (median per-feature CV within each group)
    group_cvs = {}
    for g in group_order:
        cols = [s for s in samples if sample_meta.get(s, "Unknown") == g]
        if not cols:
            continue
        sub = df[cols]
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = sub.mean(axis=1, skipna=True)
            std = sub.std(axis=1, skipna=True)
            cv = (std / mean).replace([np.inf, -np.inf], np.nan).dropna()
        group_cvs[g] = round(float(cv.median()) * 100, 2) if not cv.empty else None

    qc_groups = {g for g in group_order if "qc" in g.lower() or "quality" in g.lower()}
    blank_groups = {g for g in group_order if any(b in g.lower() for b in ["blank", "solvent", "ntc", "standard", "pool"])}

    qc_median_cv = None
    if qc_groups:
        qc_cols = [s for s in samples if sample_meta.get(s, "Unknown") in qc_groups]
        if qc_cols:
            sub = df[qc_cols]
            with np.errstate(divide="ignore", invalid="ignore"):
                mean = sub.mean(axis=1, skipna=True)
                std = sub.std(axis=1, skipna=True)
                cv = (std / mean).replace([np.inf, -np.inf], np.nan).dropna()
            qc_median_cv = round(float(cv.median()) * 100, 2) if not cv.empty else None

    blank_sample_ratio = None
    if blank_groups:
        blank_cols = [s for s in samples if sample_meta.get(s, "Unknown") in blank_groups]
        sample_cols = [s for s in samples if sample_meta.get(s, "Unknown") not in blank_groups]
        if blank_cols and sample_cols:
            blank_mean = df[blank_cols].mean(axis=1, skipna=True).replace(0, np.nan)
            sample_mean = df[sample_cols].mean(axis=1, skipna=True)
            ratio = (sample_mean / blank_mean).replace([np.inf, -np.inf], np.nan).dropna()
            blank_sample_ratio = round(float(ratio.median()), 2) if not ratio.empty else None

    # PCA outlier detection (log10 + scale)
    pca_df = df.copy().replace(0, np.nan)
    log_df = np.log10(pca_df)
    log_df = log_df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if log_df.shape[0] >= 2 and log_df.shape[1] >= 2:
        log_df = log_df.fillna(log_df.min().min() / 2)
        X = StandardScaler().fit_transform(log_df.T)
        n_comp = min(2, X.shape[0], X.shape[1])
        pca = PCA_SKL(n_components=n_comp)
        scores = pca.fit_transform(X)
        if scores.shape[1] >= 2:
            outliers = _compute_mahalanobis_outliers(scores)
            outlier_count = int(outliers.sum())
            outlier_samples = [samples[i] for i, flag in enumerate(outliers) if flag]
        else:
            outlier_count = 0
            outlier_samples = []
    else:
        outlier_count = 0
        outlier_samples = []

    # Helper for Plotly bar colored by group
    def _bar_figure(title: str, y: dict, y_title: str) -> go.Figure:
        fig = go.Figure()
        for g in group_order:
            xs = [s for s in samples if sample_meta.get(s, "Unknown") == g]
            ys = [y.get(s, 0) for s in xs]
            fig.add_trace(go.Bar(x=xs, y=ys, name=g, marker_color=color_map.get(g, "#94a3b8")))
        fig.update_layout(barmode="group", xaxis_title="Sample", yaxis_title=y_title)
        _apply_base_layout(fig, style, title=title, x_labels=samples)
        fig.update_xaxes(tickangle=45)
        return json.loads(fig.to_json())

    # Box plot of log2 intensities per sample
    def _log2_box_figure() -> go.Figure:
        fig = go.Figure()
        for g in group_order:
            xs = [s for s in samples if sample_meta.get(s, "Unknown") == g]
            for s in xs:
                vals = _safe_log10(df[s].dropna().values)
                vals = vals[~np.isnan(vals)]
                if len(vals) == 0:
                    continue
                fig.add_trace(go.Box(y=vals, name=s, marker_color=color_map.get(g, "#94a3b8"), showlegend=False))
        fig.update_layout(xaxis_title="Sample", yaxis_title="log2 intensity")
        _apply_base_layout(fig, style, title="Sample Intensity Distribution", x_labels=samples)
        fig.update_xaxes(tickangle=45)
        return json.loads(fig.to_json())

    # CV box plot per group
    def _cv_box_figure() -> go.Figure:
        fig = go.Figure()
        for g in group_order:
            cols = [s for s in samples if sample_meta.get(s, "Unknown") == g]
            if not cols:
                continue
            sub = df[cols]
            with np.errstate(divide="ignore", invalid="ignore"):
                mean = sub.mean(axis=1, skipna=True)
                std = sub.std(axis=1, skipna=True)
                cvs = (std / mean * 100).replace([np.inf, -np.inf], np.nan).dropna().values
            cvs = cvs[cvs > 0]
            if len(cvs) == 0:
                continue
            fig.add_trace(go.Box(y=cvs, name=g, marker_color=color_map.get(g, "#94a3b8")))
        fig.update_layout(xaxis_title="Group", yaxis_title="Coefficient of variation (%)")
        _apply_base_layout(fig, style, title="Per-Feature CV by Group")
        return json.loads(fig.to_json())

    figures = {
        "tic": _bar_figure("Total Ion Current (TIC) by Sample", tic, "TIC"),
        "missing_pct": _bar_figure("Missing Values per Sample (%)", missing_pct, "Missing %"),
        "detected_features": _bar_figure("Detected Features per Sample", detected, "Count"),
        "log2_intensity": _log2_box_figure(),
        "cv_by_group": _cv_box_figure(),
    }

    try:
        figures["pca"] = generate_plot(
            dataset,
            schemas.PlotRequest(plot_type="pca", parameters={"plot": "score"}, style=style),
        )
    except Exception:
        pass

    try:
        figures["correlation_heatmap"] = generate_plot(
            dataset,
            schemas.PlotRequest(plot_type="heatmap", parameters={"heatmap_type": "correlation"}, style=style),
        )
    except Exception:
        pass

    return {
        "metrics": {
            "num_features": num_features,
            "num_samples": num_samples,
            "num_groups": len(group_order),
            "group_counts": {g: groups.count(g) for g in group_order},
            "total_missing_pct": total_missing_pct,
            "missing_per_sample": missing_pct,
            "tic": tic,
            "log2_tic": log2_tic,
            "detected_features": detected,
            "group_cv_pct": group_cvs,
            "qc_median_cv_pct": qc_median_cv,
            "sample_to_blank_median_ratio": blank_sample_ratio,
            "pca_outlier_count": outlier_count,
            "pca_outlier_samples": outlier_samples,
        },
        "figures": figures,
    }

"""R-based static plot generation using ggplot2 and pheatmap.

When the requested style engine starts with "r", the main ``generate_plot``
dispatches here.  Each supported plot type runs an R script via ``Rscript``,
which writes a PNG that is returned as a base64 data URL.  If anything fails,
this module logs the error and returns ``None`` so the caller can fall back to
Plotly.
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from app import models, schemas
from app.services.preprocessing import to_dataframe

logger = logging.getLogger(__name__)

_R_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _safe(val: Any) -> Any:
    """Convert numpy/pandas values to JSON-safe Python scalars."""
    if isinstance(val, (np.integer, np.floating)):
        return float(val) if isinstance(val, np.floating) else int(val)
    if isinstance(val, pd.Series):
        return val.tolist()
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return _safe(obj)


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Return a tidy list of dicts; NaNs become None."""
    df = df.reset_index(drop=True)
    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: (None if pd.isna(v) else _json_safe(v)) for k, v in row.items()})
    return records


def _run_r_script(script: str, payload: Dict[str, Any]) -> bytes:
    """Run an R script, passing a JSON payload and returning the generated PNG bytes."""
    script_path = os.path.join(_R_SCRIPT_DIR, script)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"R template not found: {script_path}")

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        output_dir = os.path.join(tmp, "out")
        os.makedirs(output_dir, exist_ok=True)

        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(payload), f)

        cmd = ["Rscript", script_path, input_path, output_dir]
        logger.info("Running R script: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("R script %s failed:\n%s", script, result.stderr)
            raise RuntimeError(result.stderr or "R script failed")

        out_file = os.path.join(output_dir, "plot.png")
        if os.path.exists(out_file):
            with open(out_file, "rb") as f:
                return f.read()

        # Some scripts produce multiple PNGs; the first is the primary one.
        pngs = sorted([p for p in os.listdir(output_dir) if p.endswith(".png")])
        if not pngs:
            raise RuntimeError("R script did not produce any PNG files")
        with open(os.path.join(output_dir, pngs[0]), "rb") as f:
            return f.read()


def _run_r_script_multi(script: str, payload: Dict[str, Any]) -> List[bytes]:
    """Run an R script that produces multiple PNGs; return all in filename order."""
    script_path = os.path.join(_R_SCRIPT_DIR, script)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"R template not found: {script_path}")

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        output_dir = os.path.join(tmp, "out")
        os.makedirs(output_dir, exist_ok=True)

        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(payload), f)

        cmd = ["Rscript", script_path, input_path, output_dir]
        logger.info("Running R script (multi): %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            logger.error("R script %s failed:\n%s", script, result.stderr)
            raise RuntimeError(result.stderr or "R script failed")

        pngs = sorted([p for p in os.listdir(output_dir) if p.endswith(".png")])
        if not pngs:
            raise RuntimeError("R script did not produce any PNG files")

        images = []
        for png in pngs:
            with open(os.path.join(output_dir, png), "rb") as f:
                images.append(f.read())
        return images


def _b64_png_image(data: bytes, width: int, height: int, keep_title: bool = False) -> Dict[str, Any]:
    return {
        "format": "png",
        "image": f"data:image/png;base64,{base64.b64encode(data).decode()}",
        "width": width,
        "height": height,
        "keep_title": keep_title,
    }


def _prepare_heatmap_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    sample_meta = params.get("sample_metadata", {})
    feature_metadata = params.get("feature_metadata", [])
    top_n = int(params.get("top_n", 50))
    scale = params.get("scale", "row_zscore")
    cluster_rows = bool(params.get("cluster_rows", True))
    cluster_cols = bool(params.get("cluster_cols", True))
    metric = params.get("metric", "euclidean")
    method = params.get("method", "average")
    heatmap_type = params.get("heatmap_type", "abundance")

    df = df.copy()
    if heatmap_type == "correlation":
        df = df.T.corr(method="pearson")
        sample_meta = {}
        feature_metadata = []

    numeric_df = df.apply(pd.to_numeric, errors="coerce").fillna(0)
    # select top N variable features
    if top_n and top_n < len(numeric_df):
        variances = numeric_df.var(axis=1, skipna=True).fillna(0)
        keep = variances.nlargest(top_n).index.tolist()
        numeric_df = numeric_df.loc[keep]
        feature_metadata = [feature_metadata[i] for i, fid in enumerate(df.index) if fid in keep] if feature_metadata else []

    # apply row z-score scaling before clustering if requested
    scaled = numeric_df
    if scale == "row_zscore":
        scaled = numeric_df.sub(numeric_df.mean(axis=1), axis=0).div(numeric_df.std(axis=1), axis=0).replace([np.inf, -np.inf], np.nan).fillna(0)
    elif scale == "log2":
        scaled = np.log2(numeric_df.replace(0, np.nan))
        scaled = scaled.fillna(scaled.min().min())

    samples = scaled.columns.tolist()
    features = scaled.index.tolist()
    matrix = scaled.values.tolist()

    annotations = []
    if sample_meta:
        for s in samples:
            annotations.append({"sample": s, "group": sample_meta.get(s, "unknown")})

    return {
        "matrix": matrix,
        "samples": samples,
        "features": features,
        "annotations": annotations,
        "cluster_rows": cluster_rows,
        "cluster_cols": cluster_cols,
        "metric": metric,
        "method": method,
        "scale": "row" if scale == "row_zscore" else "none",
        "colorscale": style.get("heatmap_colorscale", "RdBu_r"),
        "title": params.get("title") or "Heatmap",
        "width": int(style.get("width", 1200)),
        "height": int(style.get("height", 700)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
    }


def _prepare_per_lipid_bars_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from scipy import stats as scipy_stats

    stats_data = params.get("stats", [])
    group_a = params.get("group_a", "A")
    group_b = params.get("group_b", "B")
    selected_groups = params.get("groups") or [group_a, group_b]
    selected_groups = [g for g in selected_groups if g]
    top_n = int(params.get("top_n", 8))
    sample_meta = params.get("sample_metadata", {})
    feature_metadata = params.get("feature_metadata", [])

    sorted_stats = sorted(
        [s for s in stats_data if s.get("padj") is not None],
        key=lambda s: float(s.get("padj", 1.0)),
    )[:top_n]

    feature_ids = [s.get("feature_id") for s in sorted_stats]
    # build index map
    fid_to_idx = {}
    for i, meta in enumerate(feature_metadata):
        fid = meta.get("feature_id")
        if fid:
            fid_to_idx[fid] = i

    plot_data = []
    for s in sorted_stats:
        fid = s.get("feature_id")
        idx = fid_to_idx.get(fid)
        if idx is None:
            # try by name or row index
            for i, meta in enumerate(feature_metadata):
                if meta.get("name") == fid or meta.get("feature_id") == fid:
                    idx = i
                    break
        if idx is None or idx >= len(df):
            continue
        values = df.iloc[idx].values
        samples = df.columns.tolist()
        group_vals: Dict[str, List[float]] = {g: [] for g in selected_groups}
        for c, g in zip(samples, [sample_meta.get(c, "unknown") for c in samples]):
            if g in group_vals:
                group_vals[g].append(float(values[samples.index(c)]) if pd.notna(values[samples.index(c)]) else 0.0)

        ordered = [g for g in selected_groups if group_vals.get(g)]
        if not ordered:
            continue

        padj = float(s.get("padj", 1.0))
        sig = ""
        if padj < 0.001:
            sig = " ***"
        elif padj < 0.01:
            sig = " **"
        elif padj < 0.05:
            sig = " *"

        for g in ordered:
            vals = group_vals[g]
            plot_data.append({
                "feature": f"{_shorten_name(fid, 45)}{sig}",
                "feature_raw": fid,
                "group": g,
                "mean": float(np.mean(vals)) if vals else 0.0,
                "sem": float(scipy_stats.sem(vals)) if len(vals) > 1 else 0.0,
                "values": vals,
                "padj": padj,
            })

    return {
        "plots": plot_data,
        "groups": selected_groups,
        "group_colors": style.get("group_colors", []),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "width": int(style.get("width", 600)),
        "height": int(style.get("height", 400)),
        "per_page": int(params.get("per_page", 4)),
    }


def _shorten_name(name: str, max_len: int = 45) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def _prepare_volcano_data(params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    points = params.get("stats", [])
    fc_thresh = float(params.get("fc_threshold", 1.0))
    p_thresh = float(params.get("p_threshold", 0.05))

    up_color = style.get("up_color", "#c44e52")
    down_color = style.get("down_color", "#2e6575")
    ns_color = style.get("non_significant_color", "#a0aec0")

    rows = []
    for p in points:
        lfc = float(p.get("log2_fold_change", p.get("lfc", 0.0)))
        padj = float(p.get("padj", 1.0))
        neglogp = -np.log10(max(padj, 1e-300)) if padj > 0 else 0.0
        regulation = "up" if lfc >= fc_thresh and padj < p_thresh else ("down" if lfc <= -fc_thresh and padj < p_thresh else "ns")
        rows.append({
            "name": _shorten_name(str(p.get("name", p.get("feature_id", ""))), 40),
            "lfc": lfc,
            "neglogp": float(neglogp),
            "padj": padj,
            "regulation": regulation,
        })

    return {
        "points": rows,
        "fc_threshold": fc_thresh,
        "p_threshold": p_thresh,
        "up_color": up_color,
        "down_color": down_color,
        "ns_color": ns_color,
        "title": params.get("title") or "Volcano Plot",
        "width": int(style.get("width", 1200)),
        "height": int(style.get("height", 700)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
    }


def _prepare_pca_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from sklearn.decomposition import PCA as PCA_SKL
    from sklearn.preprocessing import StandardScaler

    plot = params.get("plot", "score")
    if plot != "score":
        raise ValueError("R engine supports PCA score plot only")

    sample_meta = params.get("sample_metadata", {})
    df = df.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all").fillna(0)
    X = df.T.values
    X = StandardScaler().fit_transform(X)
    pca = PCA_SKL(n_components=min(5, X.shape[0], X.shape[1]))
    scores = pca.fit_transform(X)
    explained = pca.explained_variance_ratio_

    groups = [sample_meta.get(c, "unknown") for c in df.columns]
    unique_groups = sorted(set(groups))
    group_colors = style.get("group_colors", [])
    color_map = {g: group_colors[i % len(group_colors)] if group_colors else "#2e6575" for i, g in enumerate(unique_groups)}

    rows = []
    for i, col in enumerate(df.columns):
        rows.append({
            "sample": col,
            "group": groups[i],
            "pc1": float(scores[i, 0]),
            "pc2": float(scores[i, 1]),
            "color": color_map.get(groups[i], "#2e6575"),
        })

    return {
        "points": rows,
        "pc1_label": f"PC1 ({explained[0]*100:.1f}%)",
        "pc2_label": f"PC2 ({explained[1]*100:.1f}%)",
        "title": params.get("title") or "PCA Score Plot",
        "width": int(style.get("width", 900)),
        "height": int(style.get("height", 700)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
    }


def _prepare_lipid_class_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.plots import _extract_lipid_class

    sample_meta = params.get("sample_metadata", {})
    feature_metadata = params.get("feature_metadata", [])
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    classes = [_extract_lipid_class(f.get("feature_id", ""), f) for f in feature_metadata]
    if len(classes) != len(df):
        classes = classes[: len(df)]
    mat = df.copy()
    mat["class"] = classes
    totals = mat.groupby("class").sum(numeric_only=True)

    sample_groups = {c: sample_meta.get(c, "unknown") for c in totals.columns}
    unique_groups = sorted(set(sample_groups.values()))
    group_colors = style.get("group_colors", [])
    color_map = {g: group_colors[i % len(group_colors)] if group_colors else "#2e6575" for i, g in enumerate(unique_groups)}

    rows = []
    for cls in totals.index.tolist():
        for g in unique_groups:
            cols = [c for c in totals.columns if sample_groups[c] == g]
            vals = [float(totals.loc[cls, c]) for c in cols]
            rows.append({
                "class": cls,
                "group": g,
                "mean": float(np.mean(vals)) if vals else 0.0,
                "color": color_map.get(g, "#2e6575"),
            })

    return {
        "data": rows,
        "groups": unique_groups,
        "title": params.get("title") or "Total abundance by lipid class × group",
        "width": int(style.get("width", 1200)),
        "height": int(style.get("height", 700)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
    }


def generate_plot_r(
    dataset: models.Dataset,
    req: schemas.PlotRequest,
    style: Dict[str, Any],
    df: Optional[pd.DataFrame] = None,
    sample_meta: Optional[Dict[str, Any]] = None,
    feature_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Any]:
    """Return an R-generated figure, or ``None`` to fall back to Plotly."""
    if df is None:
        df = to_dataframe(dataset)
    if sample_meta is None:
        sample_meta = dataset.sample_metadata or {}
    if feature_metadata is None:
        feature_metadata = list(dataset.feature_metadata or [])
    params = dict(req.parameters or {})
    params["sample_metadata"] = sample_meta
    params["feature_metadata"] = feature_metadata

    plot_type = req.plot_type
    engine = str(style.get("engine", "plotly"))

    # heatmap engine can be specific; any R engine can generate a heatmap with pheatmap
    if plot_type == "heatmap":
        try:
            payload = _prepare_heatmap_data(df, params, style)
            png = _run_r_script("heatmap.R", payload)
            return _b64_png_image(png, payload["width"], payload["height"])
        except Exception:
            logger.exception("R heatmap failed")
            return None

    if plot_type == "per_lipid_bars":
        try:
            payload = _prepare_per_lipid_bars_data(df, params, style)
            # per_lipid_bars returns one figure per feature
            images = _run_r_script_multi("per_lipid_bars.R", payload)
            return [_b64_png_image(img, payload["width"], payload["height"], keep_title=True) for img in images]
        except Exception:
            logger.exception("R per_lipid_bars failed")
            return None

    if plot_type == "volcano":
        try:
            payload = _prepare_volcano_data(params, style)
            png = _run_r_script("volcano.R", payload)
            return _b64_png_image(png, payload["width"], payload["height"])
        except Exception:
            logger.exception("R volcano failed")
            return None

    if plot_type == "pca":
        try:
            payload = _prepare_pca_data(df, params, style)
            png = _run_r_script("pca_score.R", payload)
            return _b64_png_image(png, payload["width"], payload["height"])
        except Exception:
            logger.exception("R pca failed")
            return None

    if plot_type == "lipid_class":
        try:
            payload = _prepare_lipid_class_data(df, params, style)
            png = _run_r_script("lipid_class.R", payload)
            return _b64_png_image(png, payload["width"], payload["height"])
        except Exception:
            logger.exception("R lipid_class failed")
            return None

    # Unsupported R plot type
    logger.info("R engine not implemented for plot_type=%s; falling back", plot_type)
    return None

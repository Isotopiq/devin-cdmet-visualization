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
    from app.services.plots import _extract_lipid_class

    sample_meta = dict(params.get("sample_metadata", {}))
    feature_metadata = list(params.get("feature_metadata") or [])
    max_rows = int(params.get("max_heatmap_rows") or style.get("max_heatmap_rows", 120) or 120)
    max_cols = int(params.get("max_heatmap_cols") or style.get("max_heatmap_cols", 120) or 120)
    top_n = int(params.get("top_n", 50) or 0)
    if top_n > max_rows:
        top_n = max_rows
    scale = params.get("scale", "row_zscore")
    cluster_rows = bool(params.get("cluster_rows", True))
    cluster_cols = bool(params.get("cluster_cols", True))
    metric = params.get("metric", "euclidean")
    method = params.get("method", "average")
    heatmap_type = params.get("heatmap_type", "abundance")

    def _meta_for_index(idx: Any) -> Dict[str, Any]:
        if isinstance(idx, (int, np.integer)):
            if idx < len(feature_metadata):
                return feature_metadata[idx]
            return {}
        sidx = str(idx)
        for m in feature_metadata:
            if str(m.get("feature_id", "")) == sidx:
                return m
        return {}

    def _row_name(meta: Dict[str, Any]) -> str:
        for key in ("name", "display_name", "feature_name", "label", "feature_id"):
            val = meta.get(key)
            if val:
                return str(val)
        return ""

    df = df.copy()
    if heatmap_type == "correlation":
        df = df.T.corr(method="pearson")
        sample_meta = {}
        feature_metadata = []
        max_rows = min(max_rows, 100)

    numeric_df = df.apply(pd.to_numeric, errors="coerce")

    if top_n and 0 < top_n < len(numeric_df):
        variances = numeric_df.var(axis=1, skipna=True).fillna(0)
        keep = variances.nlargest(top_n).index
        numeric_df = numeric_df.loc[keep]

    if len(numeric_df.columns) > max_cols:
        col_vars = numeric_df.var(axis=0, skipna=True).fillna(0)
        keep_cols = col_vars.nlargest(max_cols).index.tolist()
        numeric_df = numeric_df[keep_cols]
        sample_meta = {c: sample_meta.get(c, "unknown") for c in numeric_df.columns}

    selected_meta = [_meta_for_index(idx) for idx in numeric_df.index]

    if scale == "row_zscore":
        means = numeric_df.mean(axis=1, skipna=True)
        stds = numeric_df.std(axis=1, skipna=True).replace(0, np.nan)
        scaled = numeric_df.sub(means, axis=0).div(stds, axis=0).replace([np.inf, -np.inf], np.nan).fillna(0)
        center_zero = True
    elif scale in ("log2", "log10"):
        floor = 1e-12
        positive = numeric_df.clip(lower=floor)
        if scale == "log2":
            scaled = np.log2(positive)
        else:
            scaled = np.log10(positive)
        min_val = scaled.min().min()
        scaled = scaled.replace([np.inf, -np.inf], np.nan).fillna(min_val if pd.notna(min_val) else 0)
        center_zero = False
    else:
        scaled = numeric_df.copy()
        center_zero = False

    center_zero = bool(params.get("center_zero", center_zero))

    samples = scaled.columns.tolist()
    labels_row: List[str] = []
    annotation_row: List[Dict[str, Any]] = []
    for idx, meta in zip(numeric_df.index, selected_meta):
        row_label = _row_name(meta) or str(idx)
        labels_row.append(row_label)
        row = {"feature": row_label}
        ann_val = None
        for k in ("lipid_class", "class", "pathway", "compound_class"):
            v = meta.get(k)
            if v:
                ann_val = v
                break
        if ann_val is None:
            ann_val = _extract_lipid_class(row_label, meta) or "Unknown"
        if ann_val:
            row["Class"] = str(ann_val)
        annotation_row.append(row)

    group_colors_list = style.get("group_colors") or ["#2e6575", "#7eb5c9", "#e9a47f", "#f2cc8f", "#81b29a", "#9d8189"]
    groups = sorted({str(g) for g in sample_meta.values() if g})
    group_color_map = {g: group_colors_list[i % len(group_colors_list)] for i, g in enumerate(groups)}

    nrow = len(scaled)
    ncol = len(scaled.columns)
    base_width = int(style.get("width", 1200))
    base_height = int(style.get("height", 700))
    min_width = min(3200, max(640, ncol * 10 + 280))
    min_height = min(2400, max(520, nrow * 10 + 220))
    width = max(base_width, min_width)
    height = max(base_height, min_height)

    cellwidth = max(6, min(80, (width - 260) / max(ncol, 1)))
    cellheight = max(8, min(30, (height - 180) / max(nrow, 1)))
    show_rownames = bool(params.get("show_rownames", nrow <= max_rows))
    show_colnames = bool(params.get("show_colnames", ncol <= max_cols))

    caption = params.get("caption")
    if not caption:
        caption = f"Top features: {nrow}; scale: {scale}; distance: {metric}; linkage: {method}"

    return {
        "matrix": scaled.where(pd.notna(scaled), np.nan).values.tolist(),
        "samples": samples,
        "features": [str(i) for i in scaled.index],
        "labels_row": labels_row,
        "labels_col": samples,
        "annotations": [{"sample": s, "group": sample_meta.get(s, "unknown")} for s in samples],
        "annotation_row": annotation_row,
        "group_color_map": group_color_map,
        "cluster_rows": cluster_rows,
        "cluster_cols": cluster_cols,
        "metric": metric,
        "method": method,
        "scale": "none",
        "colorscale": style.get("heatmap_colorscale", "RdBu_r"),
        "center_zero": center_zero,
        "title": params.get("title") or "Heatmap",
        "width": int(width),
        "height": int(height),
        "res": int(style.get("r_resolution", 120)),
        "cellwidth": float(cellwidth),
        "cellheight": float(cellheight),
        "show_rownames": show_rownames,
        "show_colnames": show_colnames,
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "font_family": style.get("r_font") or style.get("font_family") or "Liberation Sans",
        "caption": caption,
    }


def _prepare_per_lipid_bars_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from scipy import stats as scipy_stats
    from app.services.plots import _intensity_df, _group_color_map

    stats_data = params.get("stats", [])
    group_a = params.get("group_a", "A")
    group_b = params.get("group_b", "B")
    selected_groups = [g for g in (params.get("groups") or [group_a, group_b]) if g]
    top_n = int(params.get("top_n", 8))
    sample_meta = dict(params.get("sample_metadata", {}))
    feature_metadata = list(params.get("feature_metadata") or [])
    processing_history = list(params.get("processing_history") or [])

    sorted_stats = sorted(
        [s for s in stats_data if s.get("padj") is not None],
        key=lambda s: float(s.get("padj", 1.0)),
    )[:top_n]

    def _meta_for_fid(fid: Any) -> Dict[str, Any]:
        for m in feature_metadata:
            if m.get("feature_id") == fid:
                return m
        return {}

    int_df = _intensity_df(df, processing_history)

    fid_to_idx = {}
    for i, meta in enumerate(feature_metadata):
        fid = meta.get("feature_id")
        if fid:
            fid_to_idx[fid] = i

    plot_data: List[Dict[str, Any]] = []
    for s in sorted_stats:
        fid = s.get("feature_id")
        idx = fid_to_idx.get(fid)
        if idx is None:
            for i, meta in enumerate(feature_metadata):
                if meta.get("feature_id") == fid or str(meta.get("name")) == str(fid):
                    idx = i
                    break
        if idx is None or idx >= len(int_df):
            continue

        values = int_df.iloc[idx].values
        samples = int_df.columns.tolist()
        group_vals: Dict[str, List[float]] = {g: [] for g in selected_groups}
        for c, g in zip(samples, [sample_meta.get(c, "unknown") for c in samples]):
            if g in group_vals:
                val = values[samples.index(c)]
                group_vals[g].append(float(val) if pd.notna(val) else 0.0)

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

        meta = _meta_for_fid(fid)
        raw_name = str(meta.get("name") or meta.get("feature_id") or fid)
        for g in ordered:
            vals = group_vals[g]
            plot_data.append({
                "feature": f"{_shorten_name(fid, 45)}{sig}",
                "feature_raw": _shorten_name(raw_name, 55),
                "group": g,
                "mean": float(np.mean(vals)) if vals else 0.0,
                "sem": float(scipy_stats.sem(vals)) if len(vals) > 1 else 0.0,
                "values": vals,
                "padj": padj,
            })

    n_groups = len(selected_groups)
    longest_group = max((len(str(g)) for g in selected_groups), default=0)
    width = max(360, n_groups * 90 + longest_group * 8 + 180)
    height = max(320, 200 + longest_group * 8 + 80)
    group_color_map = _group_color_map(style, selected_groups)

    return {
        "plots": plot_data,
        "groups": selected_groups,
        "group_color_map": group_color_map,
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "width": int(width),
        "height": int(height),
        "res": int(style.get("r_resolution", 120)),
        "r_theme": style.get("r_theme", "publication"),
        "bar_width": float(style.get("r_bar_width", 0.55)),
        "font_family": style.get("r_font") or style.get("font_family") or "Liberation Sans",
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
        "non_significant_color": ns_color,
        "title": params.get("title") or "Volcano Plot",
        "width": int(style.get("width", 1200)),
        "height": int(style.get("height", 700)),
        "res": int(style.get("r_resolution", 120)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "font_family": style.get("r_font") or style.get("font_family") or "Liberation Sans",
        "r_theme": style.get("r_theme", "publication"),
    }


def _prepare_pca_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from sklearn.decomposition import PCA as PCA_SKL
    from sklearn.preprocessing import StandardScaler
    from app.services.plots import _group_color_map

    plot = params.get("plot", "score")
    if plot != "score":
        raise ValueError("R engine supports PCA score plot only")

    sample_meta = dict(params.get("sample_metadata", {}))
    df = df.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all").fillna(0)
    X = df.T.values
    X = StandardScaler().fit_transform(X)
    pca = PCA_SKL(n_components=min(5, X.shape[0], X.shape[1]))
    scores = pca.fit_transform(X)
    explained = pca.explained_variance_ratio_

    groups = [sample_meta.get(c, "unknown") for c in df.columns]
    unique_groups = sorted(set(groups))
    group_color_map = _group_color_map(style, unique_groups)

    rows = []
    for i, col in enumerate(df.columns):
        rows.append({
            "sample": col,
            "group": groups[i],
            "pc1": float(scores[i, 0]),
            "pc2": float(scores[i, 1]),
        })

    return {
        "points": rows,
        "group_color_map": group_color_map,
        "pc1_label": f"PC1 ({explained[0]*100:.1f}%)",
        "pc2_label": f"PC2 ({explained[1]*100:.1f}%)",
        "title": params.get("title") or "PCA Score Plot",
        "width": int(style.get("width", 900)),
        "height": int(style.get("height", 700)),
        "res": int(style.get("r_resolution", 120)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "font_family": style.get("r_font") or style.get("font_family") or "Liberation Sans",
        "r_theme": style.get("r_theme", "publication"),
    }


def _prepare_lipid_class_data(df: pd.DataFrame, params: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.plots import _extract_lipid_class, _intensity_df, _group_color_map

    sample_meta = dict(params.get("sample_metadata", {}))
    feature_metadata = list(params.get("feature_metadata") or [])
    processing_history = list(params.get("processing_history") or [])
    df = df.apply(pd.to_numeric, errors="coerce")

    int_df = _intensity_df(df, processing_history)

    classes = [_extract_lipid_class(f.get("feature_id", ""), f) for f in feature_metadata]
    if len(classes) != len(int_df):
        classes = classes[: len(int_df)]
    mat = int_df.copy()
    mat["class"] = classes
    totals = mat.groupby("class").sum(numeric_only=True)

    sample_groups = {c: sample_meta.get(c, "unknown") for c in totals.columns}
    unique_groups = sorted(set(sample_groups.values()))
    group_color_map = _group_color_map(style, unique_groups)

    rows = []
    for cls in totals.index.tolist():
        for g in unique_groups:
            cols = [c for c in totals.columns if sample_groups[c] == g]
            vals = [float(totals.loc[cls, c]) for c in cols]
            rows.append({
                "class": cls,
                "group": g,
                "mean": float(np.mean(vals)) if vals else 0.0,
            })

    n_classes = len(totals.index)
    n_groups = len(unique_groups)
    longest_class = max((len(str(c)) for c in totals.index), default=0)
    width = max(600, n_classes * n_groups * 55 + 240)
    height = max(420, 280 + longest_class * 8 + 80)

    return {
        "data": rows,
        "groups": unique_groups,
        "group_color_map": group_color_map,
        "title": params.get("title") or "Total abundance by lipid class × group",
        "width": int(width),
        "height": int(height),
        "res": int(style.get("r_resolution", 120)),
        "title_size": int(style.get("title_size", 16)),
        "axis_label_size": int(style.get("axis_label_size", 12)),
        "tick_size": int(style.get("tick_size", 11)),
        "font_family": style.get("r_font") or style.get("font_family") or "Liberation Sans",
        "r_theme": style.get("r_theme", "publication"),
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
    params["processing_history"] = list(dataset.processing_history or [])

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

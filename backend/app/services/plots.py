import json
import math
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import pdist
from sklearn.decomposition import PCA as PCA_SKL
from sklearn.preprocessing import StandardScaler
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe


def _get_feature_index(dataset, feature_arg):
    if feature_arg is None:
        return 0
    if isinstance(feature_arg, int):
        return feature_arg
    for i, meta in enumerate(dataset.feature_metadata):
        if meta.get("feature_id") == feature_arg or meta.get("name") == feature_arg:
            return i
    return 0


def _reorder_columns(df, sample_meta, group_order):
    if not group_order:
        return df
    order = []
    for g in group_order:
        for col in df.columns:
            if sample_meta.get(col) == g:
                order.append(col)
    order += [c for c in df.columns if c not in order]
    return df[order]


def _safe_float(value, default=0.0):
    try:
        v = float(value)
        if math.isfinite(v):
            return v
        return default
    except (TypeError, ValueError):
        return default


def _place_labels(xs, ys, labels, x_min, x_max, y_min, y_max, plot_width_px=900, plot_height_px=520, font_px=9):
    """Place text labels near volcano points while avoiding overlap and plot edges."""
    placed = []
    x_range = max(x_max - x_min, 1e-9)
    y_range = max(y_max - y_min, 1e-9)
    char_w = x_range * (font_px * 0.6) / plot_width_px
    char_h = y_range * (font_px * 1.6) / plot_height_px
    # Candidate offsets: right, left, top, bottom, corners
    candidates = [
        ("top right", char_w * 0.5, char_h),
        ("top left", -char_w * 0.5, char_h),
        ("bottom right", char_w * 0.5, -char_h),
        ("bottom left", -char_w * 0.5, -char_h),
        ("right", char_w, 0),
        ("left", -char_w, 0),
        ("top center", 0, char_h),
        ("bottom center", 0, -char_h),
    ]
    margin = (x_range * 20 / plot_width_px, y_range * 20 / plot_height_px)

    def rect(x, y, w, h):
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def overlaps(r1, r2):
        return not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1])

    for x, y, text in zip(xs, ys, labels):
        w = max(len(text) * char_w, char_w)
        h = char_h
        best = None
        best_score = None
        for pos, dx, dy in candidates:
            nx = x + dx
            ny = y + dy
            r = rect(nx, ny, w, h)
            # stay within axis bounds with a margin
            if r[0] < x_min - margin[0] or r[2] > x_max + margin[0] or r[1] < y_min - margin[1] or r[3] > y_max + margin[1]:
                continue
            if any(overlaps(r, pr) for pr in placed):
                continue
            # Prefer positions closer to the original point and the first candidate order
            score = (dx ** 2 + dy ** 2) ** 0.5
            if best is None or score < best_score:
                best = (nx, ny, pos)
                best_score = score
        if best is None:
            # Fallback: keep original position, top center; label may overlap but stays visible
            best = (x, y + char_h, "top center")
        placed.append(rect(best[0], best[1], w, h))
        yield best


def generate_plot(dataset: models.Dataset, req: schemas.PlotRequest):
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata
    plot_type = req.plot_type
    params = req.parameters or {}

    if plot_type in ("bar", "box", "violin", "dot"):
        feature = _get_feature_index(dataset, params.get("feature"))
        values = df.iloc[feature].values
        samples = df.columns.tolist()
        groups = [sample_meta.get(c, "unknown") for c in samples]
        group_order = params.get("group_order", [])
        ordered_df = _reorder_columns(df, sample_meta, group_order)
        ordered_samples = ordered_df.columns.tolist()
        ordered_values = ordered_df.iloc[feature].values
        ordered_groups = [sample_meta.get(c, "unknown") for c in ordered_samples]
        title = f"{dataset.feature_metadata[feature].get('feature_id', feature)}"

        if plot_type == "bar":
            fig = px.bar(x=ordered_samples, y=ordered_values, color=ordered_groups,
                         labels={"x": "Sample", "y": "Abundance"},
                         title=f"Abundance: {title}")
        elif plot_type == "box":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g, vals in group_vals.items():
                fig.add_trace(go.Box(y=vals, name=g, boxpoints="all"))
            fig.update_layout(title=f"Box Plot: {title}", xaxis_title="Group", yaxis_title="Abundance")
        elif plot_type == "violin":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g, vals in group_vals.items():
                fig.add_trace(go.Violin(y=vals, name=g, box_visible=True, meanline_visible=True))
            fig.update_layout(title=f"Violin Plot: {title}", yaxis_title="Abundance")
        else:  # dot
            fig = px.scatter(x=ordered_samples, y=ordered_values, color=ordered_groups,
                             labels={"x": "Sample", "y": "Abundance"},
                             title=f"Dot Plot: {title}")

    elif plot_type == "heatmap":
        heatmap_type = params.get("heatmap_type", "abundance")
        cluster = params.get("cluster", "both")
        if heatmap_type == "correlation":
            if cluster in ("row", "both") and len(df.columns) > 2:
                try:
                    dist = pdist(df.T.values)
                    link = linkage(dist, method="average")
                    order = leaves_list(link)
                    df = df.iloc[:, order]
                except Exception:
                    pass
            corr = df.corr().fillna(0)
            fig = px.imshow(corr, text_auto=".2f", aspect="auto", title="Sample Correlation Heatmap",
                           color_continuous_scale="RdBu_r", zmid=0)
        else:
            plot_df = df.copy()
            if cluster in ("row", "both") and len(plot_df) > 2:
                try:
                    dist = pdist(plot_df.values)
                    link = linkage(dist, method="average")
                    order = leaves_list(link)
                    plot_df = plot_df.iloc[order]
                except Exception:
                    pass
            if cluster in ("col", "both") and len(plot_df.columns) > 2:
                try:
                    dist = pdist(plot_df.T.values)
                    link = linkage(dist, method="average")
                    order = leaves_list(link)
                    plot_df = plot_df.iloc[:, order]
                except Exception:
                    pass
            # Use log10(abundance + 1) for visualization if the matrix is non-negative.
            values = np.log10(plot_df.replace(0, np.nan).fillna(0) + 1).values
            fig = px.imshow(values, x=plot_df.columns, y=plot_df.index,
                            aspect="auto", title="Abundance Heatmap",
                            labels={"color": "log10(abundance + 1)"},
                            color_continuous_scale="Viridis")

    elif plot_type == "pca":
        ptype = params.get("plot", "score")
        components = max(2, min(int(params.get("components", 3)), len(df.columns), len(df)))
        do_scale = bool(params.get("scale", True))
        X = df.dropna().T
        if X.empty or X.shape[1] < 2 or X.shape[0] < 2:
            fig = go.Figure()
            fig.update_layout(title="Not enough data for PCA")
            return json.loads(fig.to_json())
        X = X.fillna(X.min().min() / 2)
        Xs = StandardScaler().fit_transform(X) if do_scale else X.values
        pca = PCA_SKL(n_components=components)
        scores = pca.fit_transform(Xs)
        labels = [sample_meta.get(c, c) for c in X.index]

        if ptype == "scree":
            fig = px.bar(x=[f"PC{i+1}" for i in range(len(pca.explained_variance_ratio_))],
                         y=pca.explained_variance_ratio_ * 100,
                         labels={"x": "Principal Component", "y": "Variance Explained (%)"},
                         title="PCA Scree Plot")
        elif ptype == "loading":
            loadings = pca.components_[0]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(dataset.feature_metadata)]
            top_idx = np.argsort(np.abs(loadings))[-50:]
            fig = px.bar(x=[feat_ids[i] for i in top_idx], y=[loadings[i] for i in top_idx],
                         labels={"x": "Feature", "y": "PC1 Loading"},
                         title="PCA Top Loadings (PC1)")
        elif ptype == "biplot":
            fig = px.scatter(x=scores[:, 0], y=scores[:, 1], color=labels,
                             labels={"x": f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                                     "y": f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)"},
                             title="PCA Biplot")
            loadings = pca.components_[:2]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(dataset.feature_metadata)]
            x_scale = max(np.abs(scores[:, 0]).max(), 1e-9)
            y_scale = max(np.abs(scores[:, 1]).max(), 1e-9)
            for i in range(min(20, len(loadings[0]))):
                fig.add_trace(go.Scatter(x=[0, loadings[0, i]*x_scale], y=[0, loadings[1, i]*y_scale],
                                         mode="lines+text", text=["", feat_ids[i]], textposition="top center",
                                         line=dict(color="gray"), showlegend=False))
        else:
            fig = px.scatter(x=scores[:, 0], y=scores[:, 1], color=labels,
                             labels={"x": f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                                     "y": f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)"},
                             title="PCA Score Plot")

    elif plot_type == "volcano":
        stats_data = params.get("stats", [])
        fc_thresh = float(params.get("fc_threshold", 0.5))
        p_thresh = float(params.get("p_threshold", 0.05))
        show_labels = bool(params.get("show_labels", False))
        top_n = max(0, int(params.get("top_n", 10)))

        points = []
        for s in stats_data:
            lfc = s.get("log2fc")
            padj = s.get("padj")
            if lfc is None or padj is None or not math.isfinite(padj) or padj <= 0 or not math.isfinite(lfc):
                continue
            p = -np.log10(padj)
            if not math.isfinite(p):
                continue
            up = lfc > fc_thresh and padj < p_thresh
            down = lfc < -fc_thresh and padj < p_thresh
            color = "Up" if up else ("Down" if down else "Not significant")
            points.append({"lfc": lfc, "neglogp": p, "padj": padj, "name": s.get("feature_id", ""), "color": color})

        fc = [p["lfc"] for p in points]
        neglogp = [p["neglogp"] for p in points]
        names = [p["name"] for p in points]
        colors = [p["color"] for p in points]

        fig = px.scatter(x=fc, y=neglogp, hover_name=names, color=colors,
                         color_discrete_map={"Up": "red", "Down": "blue", "Not significant": "gray"},
                         labels={"x": "log2 Fold Change", "y": "-log10 adjusted p-value"},
                         title="Volcano Plot")
        fig.add_hline(y=-np.log10(p_thresh), line_dash="dash", line_color="black")
        fig.add_vline(x=fc_thresh, line_dash="dash", line_color="black")
        fig.add_vline(x=-fc_thresh, line_dash="dash", line_color="black")

        if show_labels and top_n > 0 and points:
            # Choose top N most significant points that also meet the fold-change threshold.
            candidates = [p for p in points if abs(p["lfc"]) >= fc_thresh]
            candidates.sort(key=lambda p: p["padj"])
            top = candidates[:top_n]
            if top:
                x_vals = [p["lfc"] for p in top]
                y_vals = [p["neglogp"] for p in top]
                labels = [p["name"] for p in top]
                x_min, x_max = min(fc) if fc else -1, max(fc) if fc else 1
                y_min, y_max = min(neglogp) if neglogp else 0, max(neglogp) if neglogp else 1
                positions = list(_place_labels(x_vals, y_vals, labels, x_min, x_max, y_min, y_max))
                fig.add_trace(go.Scatter(
                    x=[x for x, _, _ in positions],
                    y=[y for _, y, _ in positions],
                    mode="text",
                    text=labels,
                    textposition=[pos[2] for pos in positions],
                    textfont=dict(size=9, color="black"),
                    hoverinfo="skip",
                    showlegend=False,
                    cliponaxis=False,
                ))

    elif plot_type == "rt_mz":
        mz = [_safe_float(f.get("mz", 0)) for f in dataset.feature_metadata]
        rt = [_safe_float(f.get("rt", 0)) for f in dataset.feature_metadata]
        grades = [str(f.get("grade", "unknown")) for f in dataset.feature_metadata]
        fig = px.scatter(x=mz, y=rt, color=grades,
                         labels={"x": "m/z", "y": "Retention Time"},
                         title="Retention Time vs m/z")

    else:
        fig = go.Figure()
        fig.update_layout(title="Unsupported plot type")

    return json.loads(fig.to_json())

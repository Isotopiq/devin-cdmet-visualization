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
        cluster = params.get("cluster", "both")
        if cluster in ("row", "both") and len(df.columns) > 2:
            try:
                dist = pdist(df.T.values)
                link = linkage(dist, method="average")
                order = leaves_list(link)
                df = df.iloc[:, order]
            except Exception:
                pass
        corr = df.corr().fillna(0)
        fig = px.imshow(corr, text_auto=".2f", aspect="auto", title="Correlation Heatmap")

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
        fc = []
        neglogp = []
        names = []
        colors = []
        for s in stats_data:
            lfc = s.get("log2fc")
            padj = s.get("padj")
            if lfc is None or padj is None or not math.isfinite(padj) or padj <= 0 or not math.isfinite(lfc):
                continue
            p = -np.log10(padj)
            if not math.isfinite(p):
                continue
            fc.append(lfc)
            neglogp.append(p)
            names.append(s.get("feature_id", ""))
            up = lfc > fc_thresh and padj < p_thresh
            down = lfc < -fc_thresh and padj < p_thresh
            colors.append("Up" if up else ("Down" if down else "Not significant"))
        fig = px.scatter(x=fc, y=neglogp, hover_name=names, color=colors,
                         color_discrete_map={"Up": "red", "Down": "blue", "Not significant": "gray"},
                         labels={"x": "log2 Fold Change", "y": "-log10 adjusted p-value"},
                         title="Volcano Plot")
        fig.add_hline(y=-np.log10(p_thresh), line_dash="dash", line_color="black")
        fig.add_vline(x=fc_thresh, line_dash="dash", line_color="black")
        fig.add_vline(x=-fc_thresh, line_dash="dash", line_color="black")

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

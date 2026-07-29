import json
import math
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import linkage, leaves_list, dendrogram as scipy_dendrogram
from scipy.spatial.distance import pdist, mahalanobis as _mahalanobis
from scipy import stats as scipy_stats
from sklearn.decomposition import PCA as PCA_SKL
from sklearn.preprocessing import StandardScaler
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe
from app.services.lipid_indices import compute_functional_indices, compute_food_profile_indices


STYLE_DEFAULTS = {
    "engine": "plotly",
    "font_family": "Inter, Arial, sans-serif",
    "title_size": 16,
    "axis_label_size": 12,
    "tick_size": 11,
    "marker_size": 10,
    "show_gridlines": True,
    "paper_bgcolor": "#ffffff",
    "plot_bgcolor": "#ffffff",
    "grid_color": "#e2e8f0",
    "up_color": "#c44e52",
    "down_color": "#2e6575",
    "non_significant_color": "#a0aec0",
    "group_colors": ["#2e6575", "#7eb5c9", "#e9a47f", "#f2cc8f", "#81b29a", "#9d8189"],
    "heatmap_colorscale": "RdBu_r",
}


def _merge_style(style: dict | None) -> dict:
    merged = dict(STYLE_DEFAULTS)
    if style:
        merged.update(style)
    return merged


def _group_color_map(style: dict, groups: list) -> dict:
    colors = style.get("group_colors") or STYLE_DEFAULTS["group_colors"]
    uniq = sorted(set(str(g) for g in groups if g))
    return {g: colors[i % len(colors)] for i, g in enumerate(uniq)}


def _apply_base_layout(fig: go.Figure, style: dict, title: str | None = None):
    layout = {
        "font": {"family": style.get("font_family"), "color": "#334155"},
        "paper_bgcolor": style.get("paper_bgcolor"),
        "plot_bgcolor": style.get("plot_bgcolor"),
        "title": {
            "text": title,
            "font": {"size": style.get("title_size"), "color": "#1e293b"},
            "x": 0.5,
            "xanchor": "center",
            "y": 0.99,
            "yanchor": "top",
            "pad": {"b": 20},
        } if title else None,
        "legend": {
            "title": {"font": {"size": style.get("tick_size")}},
            "font": {"size": style.get("tick_size")},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {"l": 70, "r": 50, "t": 100, "b": 70},
        "xaxis": {
            "showgrid": style.get("show_gridlines"),
            "gridcolor": style.get("grid_color"),
            "gridwidth": 1,
            "tickfont": {"size": style.get("tick_size")},
            "title_font": {"size": style.get("axis_label_size")},
            "zerolinecolor": "#cbd5e1",
            "automargin": True,
        },
        "yaxis": {
            "showgrid": style.get("show_gridlines"),
            "gridcolor": style.get("grid_color"),
            "gridwidth": 1,
            "tickfont": {"size": style.get("tick_size")},
            "title_font": {"size": style.get("axis_label_size")},
            "zerolinecolor": "#cbd5e1",
            "automargin": True,
        },
    }
    fig.update_layout(**{k: v for k, v in layout.items() if v is not None})
    if fig.data:
        for trace in fig.data:
            if isinstance(trace, (go.Scatter, go.Scattergl)) and trace.mode and "markers" in trace.mode:
                trace.marker = trace.marker or {}
                trace.marker.size = style.get("marker_size")


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
    placed = []
    x_range = max(x_max - x_min, 1e-9)
    y_range = max(y_max - y_min, 1e-9)
    char_w = x_range * (font_px * 0.75) / plot_width_px
    char_h = y_range * (font_px * 2.0) / plot_height_px
    # Build a radial set of candidate offsets
    candidates = []
    radii = [1.2, 2.0, 2.8, 3.6]
    angles = [0.785, 1.571, 2.356, 3.142, 3.927, 4.712, 5.498, 6.283]
    text_positions = {
        0.785: "top right", 1.571: "top center", 2.356: "top left",
        3.142: "left", 3.927: "bottom left", 4.712: "bottom center",
        5.498: "bottom right", 6.283: "right",
    }
    for r in radii:
        for a in angles:
            dx = math.cos(a) * r * char_w
            dy = math.sin(a) * r * char_h
            candidates.append((text_positions.get(round(a, 3), "top center"), dx, dy))
    margin = (x_range * 30 / plot_width_px, y_range * 30 / plot_height_px)

    def rect(x, y, w, h):
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def overlaps(r1, r2):
        return not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1])

    # Use data points as obstacles so labels don't cover the markers
    for x, y in zip(xs, ys):
        placed.append(rect(x, y, char_w * 0.6, char_h * 0.6))

    for x, y, text in zip(xs, ys, labels):
        w = max(len(text) * char_w, char_w)
        h = char_h
        best = None
        best_score = None
        for pos, dx, dy in candidates:
            nx = x + dx
            ny = y + dy
            r = rect(nx, ny, w, h)
            if r[0] < x_min - margin[0] or r[2] > x_max + margin[0] or r[1] < y_min - margin[1] or r[3] > y_max + margin[1]:
                continue
            if any(overlaps(r, pr) for pr in placed):
                continue
            score = (dx ** 2 + dy ** 2) ** 0.5
            if best is None or score < best_score:
                best = (nx, ny, pos)
                best_score = score
        if best is None:
            best = (x, y + char_h * 1.5, "top center")
        placed.append(rect(best[0], best[1], w, h))
        yield best


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join([c * 2 for c in hex_color])
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _build_volcano_points(stats_data, fc_thresh, p_thresh, up_color, down_color, ns_color):
    points = []
    for s in stats_data:
        lfc = s.get("log2fc")
        padj = s.get("padj")
        if lfc is None or padj is None or not math.isfinite(padj) or padj <= 0 or not math.isfinite(lfc):
            continue
        p = max(0.0, -np.log10(padj))
        if not math.isfinite(p):
            continue
        up = lfc > fc_thresh and padj < p_thresh
        down = lfc < -fc_thresh and padj < p_thresh
        color = up_color if up else (down_color if down else ns_color)
        label = "UP" if up else ("DOWN" if down else "NS")
        points.append({"lfc": lfc, "neglogp": p, "padj": padj, "name": s.get("feature_id", ""), "color": color, "label": label})
    return points


def _volcano_publication(points, fc_thresh, p_thresh, style, params):
    fig = go.Figure()
    xs = [p["lfc"] for p in points]
    ys = [p["neglogp"] for p in points]
    x_min = min(xs) if xs else -1
    x_max = max(xs) if xs else 1
    y_min = min(ys) if ys else 0
    y_max = max(ys) if ys else 1
    x_pad = max((x_max - x_min) * 0.05, 0.1)
    y_pad = max((y_max - y_min) * 0.05, 0.1)
    x_min -= x_pad
    x_max += x_pad
    y_min = 0
    y_max += y_pad

    if -fc_thresh > x_min:
        fig.add_vrect(x0=x_min, x1=-fc_thresh, fillcolor="rgba(214,234,248,0.35)", line_width=0, layer="below")
    if fc_thresh < x_max:
        fig.add_vrect(x0=fc_thresh, x1=x_max, fillcolor="rgba(250,219,216,0.35)", line_width=0, layer="below")

    fig.add_vline(x=-fc_thresh, line_dash="dash", line_color="#7f8c8d", line_width=1)
    fig.add_vline(x=fc_thresh, line_dash="dash", line_color="#7f8c8d", line_width=1)
    fig.add_hline(y=-np.log10(p_thresh), line_dash="dash", line_color="#7f8c8d", line_width=1)

    for label, name in [("DOWN", "DOWN"), ("NS", "nonSIG"), ("UP", "UP")]:
        pts = [p for p in points if p["label"] == label]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p["lfc"] for p in pts],
            y=[p["neglogp"] for p in pts],
            mode="markers",
            name=name,
            marker=dict(color=pts[0]["color"], size=style.get("marker_size"), line=dict(width=0.5, color="white")),
            text=[p["name"] for p in pts],
            hovertemplate="%{text}<br>log2FC: %{x:.3f}<br>-log10 padj: %{y:.3f}<extra></extra>",
        ))

    if bool(params.get("show_labels", False)) and points:
        candidates = [p for p in points if abs(p["lfc"]) >= fc_thresh]
        candidates.sort(key=lambda p: p["padj"])
        top_n = max(0, int(params.get("top_n", 10)))
        top = candidates[:top_n]
        if top:
            x_vals = [p["lfc"] for p in top]
            y_vals = [p["neglogp"] for p in top]
            labels = [p["name"] for p in top]
            positions = list(_place_labels(x_vals, y_vals, labels, x_min, x_max, y_min, y_max))
            fig.add_trace(go.Scatter(
                x=[x for x, _, _ in positions],
                y=[y for _, y, _ in positions],
                mode="text",
                text=labels,
                textposition=[pos[2] for pos in positions],
                textfont=dict(size=9, color="#1e293b"),
                hoverinfo="skip",
                showlegend=False,
                cliponaxis=False,
            ))

    group_a = params.get("group_a", "A")
    group_b = params.get("group_b", "B")
    title_text = params.get("title", "Volcano Plot")
    fig.update_layout(
        title=dict(
            text=f"<b>{title_text}</b><br><sup>{group_b} vs {group_a}</sup>",
            font=dict(size=style.get("title_size"), color="#1e293b"),
            x=0.5,
            xanchor="center",
            y=0.98,
            yanchor="top",
        ),
        xaxis=dict(
            title=dict(text=f"log2 Fold Change ({group_b} / {group_a})", font=dict(size=style.get("axis_label_size"), color="#000")),
            showgrid=True,
            gridcolor="#e5e5e5",
            zeroline=False,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text="-log10 p-value", font=dict(size=style.get("axis_label_size"), color="#000")),
            showgrid=True,
            gridcolor="#e5e5e5",
            zeroline=False,
            tickfont=dict(size=style.get("tick_size")),
        ),
        legend=dict(
            title=dict(text="Regulation", font=dict(size=style.get("tick_size"))),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=style.get("tick_size")),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=70, r=50, t=120, b=70),
        font=dict(family=style.get("font_family"), color="#334155"),
    )
    return fig


def _pca_publication(scores, labels, pca, sample_names, style, params):
    fig = go.Figure()
    color_map = _group_color_map(style, labels)
    for g in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == g]
        pts = scores[idx, :2]
        if len(pts) == 0:
            continue
        if len(pts) >= 3:
            cov = np.cov(pts.T)
            if cov.shape == (2, 2):
                try:
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    order = np.argsort(eigvals)[::-1]
                    eigvals = eigvals[order]
                    eigvecs = eigvecs[:, order]
                    scale = np.sqrt(scipy_stats.chi2.ppf(0.95, df=2))
                    theta = np.linspace(0, 2 * np.pi, 100)
                    r = np.array([scale * np.sqrt(max(eigvals[0], 0)) * np.cos(theta), scale * np.sqrt(max(eigvals[1], 0)) * np.sin(theta)])
                    rot = eigvecs @ r
                    mu = pts.mean(axis=0)
                    x_ell = mu[0] + rot[0]
                    y_ell = mu[1] + rot[1]
                    fig.add_trace(go.Scatter(
                        x=x_ell, y=y_ell, mode="lines",
                        fill="toself",
                        fillcolor=_hex_to_rgba(color_map[g], 0.3),
                        line=dict(color=color_map[g], width=1),
                        name=f"{g} 95% CI",
                        showlegend=False,
                        hoverinfo="skip",
                    ))
                except Exception:
                    pass
        fig.add_trace(go.Scatter(
            x=pts[:, 0], y=pts[:, 1], mode="markers",
            name=g,
            marker_color=color_map[g],
            marker_size=style.get("marker_size"),
            marker_line=dict(width=1, color="black"),
            customdata=np.column_stack([[sample_names[i] for i in idx], [g] * len(idx)]),
            hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
        ))

    positions = list(_place_labels(scores[:, 0].tolist(), scores[:, 1].tolist(), sample_names, scores[:, 0].min(), scores[:, 0].max(), scores[:, 1].min(), scores[:, 1].max()))
    if positions:
        fig.add_trace(go.Scatter(
            x=[p[0] for p in positions],
            y=[p[1] for p in positions],
            mode="text",
            text=sample_names,
            textposition=[p[2] for p in positions],
            textfont=dict(size=9, color="#1e293b"),
            hoverinfo="skip",
            showlegend=False,
            cliponaxis=False,
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="red", line_width=1)
    fig.add_vline(x=0, line_dash="dash", line_color="red", line_width=1)

    exp1 = pca.explained_variance_ratio_[0] * 100
    exp2 = pca.explained_variance_ratio_[1] * 100
    title_text = params.get("title", "Score Plot")
    fig.update_layout(
        title=dict(text=f"<b>{title_text}</b>", font=dict(size=style.get("title_size"), color="#1e293b"), x=0.0, xanchor="left"),
        xaxis=dict(
            title=dict(text=f"PC1 ({exp1:.1f}%)", font=dict(size=style.get("axis_label_size"), color="#000")),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text=f"PC2 ({exp2:.1f}%)", font=dict(size=style.get("axis_label_size"), color="#000")),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False,
            tickfont=dict(size=style.get("tick_size")),
        ),
        legend=dict(
            title=dict(text="group", font=dict(size=style.get("tick_size"))),
            orientation="v",
            font=dict(size=style.get("tick_size")),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=80, r=150, t=80, b=70),
        font=dict(family=style.get("font_family"), color="#334155"),
    )
    return fig


def _outlier_plot(df, sample_meta, style, params):
    X = df.dropna().T
    if X.empty or X.shape[1] < 2 or X.shape[0] < 2:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Not enough data for outlier analysis")
        return fig
    X = X.fillna(X.min().min() / 2)
    Xs = StandardScaler().fit_transform(X)
    n_components = 2
    pca = PCA_SKL(n_components=n_components)
    scores = pca.fit_transform(Xs)

    mean = scores.mean(axis=0)
    cov = np.cov(scores.T)
    try:
        VI = np.linalg.pinv(cov)
    except Exception:
        VI = np.eye(cov.shape[0])
    md2 = []
    for s in scores:
        d = _mahalanobis(s, mean, VI)
        md2.append(d ** 2)

    sample_names = X.index.tolist()
    groups = [sample_meta.get(c, "Unknown") for c in sample_names]
    color_map = _group_color_map(style, sorted(set(groups)))

    data = sorted(zip(sample_names, groups, md2), key=lambda x: x[2], reverse=True)
    if data:
        names, grps, values = zip(*data)
        names = list(names)[::-1]
        grps = list(grps)[::-1]
        values = list(values)[::-1]
    else:
        names, grps, values = [], [], []

    colors = [color_map[g] for g in grps]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors,
        showlegend=False,
        hovertemplate="%{y}<br>Mahalanobis distance²: %{x:.3f}<extra></extra>",
    ))
    for g in sorted(set(groups)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=color_map[g], size=10), name=g, showlegend=True))

    chi2_95 = scipy_stats.chi2.ppf(0.95, df=n_components)
    chi2_99 = scipy_stats.chi2.ppf(0.99, df=n_components)
    fig.add_vline(x=chi2_95, line_dash="dash", line_color="blue", line_width=2)
    fig.add_vline(x=chi2_99, line_dash="dash", line_color="red", line_width=2)
    fig.add_annotation(x=chi2_95, y=1.0, yref="paper", text="95% threshold", showarrow=False, xanchor="left", yanchor="bottom", font=dict(color="blue", size=10))
    fig.add_annotation(x=chi2_99, y=1.0, yref="paper", text="99% threshold", showarrow=False, xanchor="left", yanchor="bottom", font=dict(color="red", size=10))

    title_text = params.get("title", "Outlier Plot")
    fig.update_layout(
        title=dict(text=f"<b>{title_text}</b>", font=dict(size=style.get("title_size"), color="#1e293b"), x=0.0, xanchor="left"),
        xaxis=dict(
            title=dict(text="Mahalanobis distance", font=dict(size=style.get("axis_label_size"), color="#000")),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text="Sample", font=dict(size=style.get("axis_label_size"), color="#000")),
            categoryorder="array", categoryarray=names,
            showgrid=False, tickfont=dict(size=max(7, style.get("tick_size") - 1)),
        ),
        legend=dict(
            title=dict(text="group", font=dict(size=style.get("tick_size"))),
            orientation="v",
            font=dict(size=style.get("tick_size")),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=120, r=150, t=80, b=70),
        font=dict(family=style.get("font_family"), color="#334155"),
        bargap=0.2,
    )
    return fig


def _category_volcano_figure(items, title, style):
    cat_order = sorted({it["category"] for it in items})
    cat_colors = {}
    palette = style.get("group_colors", ["#2e6575", "#e9a47f", "#81b29a", "#9d8189", "#f2cc8f", "#7eb5c9"])
    for i, c in enumerate(cat_order):
        cat_colors[c] = palette[i % len(palette)]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=False,
        vertical_spacing=0.12,
        row_heights=[0.62, 0.38],
        specs=[[{"type": "scatter"}], [{"type": "table"}]],
        subplot_titles=(title, "Interpretation table (top by significance)"),
    )

    plot_width_px = max(style.get("width", 700), 500)
    max_y = max([max(0.0, -np.log10(max(it["padj"], 1e-300))) for it in items] + [-np.log10(0.05)], default=1.0)
    min_x = min([it["log2fc"] for it in items] + [-1.5, 1.5], default=-1.5)
    max_x = max([it["log2fc"] for it in items] + [-1.5, 1.5], default=1.5)
    plot_x_range = max_x - min_x
    for c in cat_order:
        sub = [it for it in items if it["category"] == c]
        sub = sorted(sub, key=lambda it: it["log2fc"])
        xs = [it["log2fc"] for it in sub]
        ys = [max(0.0, -np.log10(max(it["padj"], 1e-300))) for it in sub]
        texts = []
        last_x = None
        for it in sub:
            lbl = it["name"]
            lw_px = max(len(lbl) * 7, 30)
            lw_data = (lw_px / plot_width_px) * plot_x_range
            x = it["log2fc"]
            if last_x is None or abs(x - last_x) > lw_data * 0.85:
                texts.append(lbl)
                last_x = x
            else:
                texts.append("")
        hovertext = [f"{it['name']}<br>log2FC: {it['log2fc']:.2f}<br>-log10(padj): {ys[i]:.2f}" for i, it in enumerate(sub)]
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=texts,
            textposition="top center",
            textfont=dict(size=8, color=cat_colors[c]),
            marker=dict(color=cat_colors[c], size=style.get("marker_size", 10), line=dict(width=0.5, color="#1e293b")),
            name=c,
            hovertemplate="%{hovertext}<extra></extra>",
            hovertext=hovertext,
        ), row=1, col=1)

    fig.add_hline(y=-np.log10(0.05), line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)
    fig.add_vline(x=1, line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)
    fig.add_vline(x=-1, line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)

    top_items = sorted(items, key=lambda it: (it["padj"], -abs(it["log2fc"])))[:max(10, len(items) // 2 + 1)]
    top_items = sorted(top_items, key=lambda it: it["padj"])
    table_colors = [cat_colors[it["category"]] for it in top_items]
    fig.add_trace(go.Table(
        header=dict(values=["Index", "Category", "log2FC", "adj. P", "Interpretation"], fill_color="#f1f5f9", align="left", font=dict(size=11, color="#1e293b")),
        cells=dict(
            values=[
                [it["name"] for it in top_items],
                [it["category"] for it in top_items],
                [f"{it['log2fc']:.2f}" for it in top_items],
                [f"{it['padj']:.3f}" for it in top_items],
                [it["interpretation"] for it in top_items],
            ],
            fill_color=[table_colors, table_colors, "white", "white", "white"],
            align="left",
            font=dict(size=10, color="#334155"),
            height=22,
        ),
    ), row=2, col=1)

    _apply_base_layout(fig, style, title="")
    fig.update_layout(
        xaxis=dict(title=dict(text="log2 fold change", font=dict(size=style.get("axis_label_size", 12))), zeroline=False, showgrid=True, gridcolor="#e5e5e5", range=[min_x, max_x]),
        yaxis=dict(title=dict(text="-log10(adjusted P)", font=dict(size=style.get("axis_label_size", 12))), showgrid=True, gridcolor="#e5e5e5", range=[0, max(1.3, max_y) * 1.1]),
        legend=dict(title=dict(text="Category"), orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=70, r=40, t=80, b=70),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
    )
    return fig


def _functional_volcano(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    indices = compute_functional_indices(df, feature_metadata, sample_meta, group_a, group_b)
    if not indices:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Functional lipid indices")
        return fig
    return _category_volcano_figure(indices, f"Functional lipid indices: {group_b} vs {group_a}", style)


def _food_profile(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    indices = compute_food_profile_indices(df, feature_metadata, sample_meta, group_a, group_b)
    if not indices:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Lipid food profile")
        return fig
    return _category_volcano_figure(indices, f"Lipid food profile: {group_b} vs {group_a}", style)


def _dendrogram_coords(link, n_leaves, orientation="top"):
    if n_leaves < 3 or link is None:
        return [], []
    dend = scipy_dendrogram(link, no_plot=True, color_threshold=0)
    icoord = np.array(dend["icoord"])
    dcoord = np.array(dend["dcoord"])
    min_i = float(icoord.min())
    max_i = float(icoord.max())
    span = max(max_i - min_i, 1e-9)
    scale = (n_leaves - 1) / span
    scaled_i = (icoord - min_i) * scale
    xs = []
    ys = []
    for si, sd in zip(scaled_i, dcoord):
        if orientation == "top":
            xs.extend(si.tolist() + [np.nan])
            ys.extend(sd.tolist() + [np.nan])
        else:  # left
            xs.extend(sd.tolist() + [np.nan])
            ys.extend(si.tolist() + [np.nan])
    return xs, ys


def _heatmap_publication(df, sample_meta, style, params):
    top_n = int(params.get("top_n", 50))
    metric = params.get("metric", "euclidean")
    method = params.get("method", "average")
    scale = params.get("scale", "row_zscore")
    cluster_rows = bool(params.get("cluster_rows", True))
    cluster_cols = bool(params.get("cluster_cols", True))
    colorscale = style.get("heatmap_colorscale", "RdBu_r")

    plot_df = df.copy()
    row_std = plot_df.std(axis=1, numeric_only=True)
    top_idx = row_std.nlargest(min(top_n, len(plot_df))).index
    plot_df = plot_df.loc[top_idx]

    if scale == "log10":
        plot_df = np.log10(plot_df.replace(0, np.nan)).fillna(0)
        zmid = None
        cbar_title = "log10 intensity"
    elif scale == "none":
        zmid = None
        cbar_title = "Intensity"
    else:  # row_zscore
        plot_df = (plot_df.sub(plot_df.mean(axis=1), axis=0).div(plot_df.std(axis=1).replace(0, np.nan), axis=0)).fillna(0)
        zmid = 0
        cbar_title = "Row z-score"

    row_link = None
    col_link = None
    if cluster_rows and len(plot_df) > 2:
        try:
            row_link = linkage(pdist(plot_df.values, metric=metric), method=method)
            row_order = leaves_list(row_link)
            plot_df = plot_df.iloc[row_order]
        except Exception:
            pass
    if cluster_cols and len(plot_df.columns) > 2:
        try:
            col_link = linkage(pdist(plot_df.T.values, metric=metric), method=method)
            col_order = leaves_list(col_link)
            plot_df = plot_df.iloc[:, col_order]
        except Exception:
            pass

    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
    group_order = sorted(set(sample_groups.values()))
    if "Unknown" in group_order:
        group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
    gcolor_map = _group_color_map(style, group_order)
    group_codes = [group_order.index(sample_groups.get(c, "Unknown")) for c in plot_df.columns]
    n_groups = max(len(group_order), 1)
    if n_groups == 1:
        group_colorscale = [[0, gcolor_map[group_order[0]]], [1, gcolor_map[group_order[0]]]]
    else:
        group_colorscale = [[i / (n_groups - 1), gcolor_map[g]] for i, g in enumerate(group_order)]

    m, n = plot_df.shape
    fig = make_subplots(
        rows=3, cols=2,
        specs=[[None, {}], [None, {}], [{}, {}]],
        shared_xaxes=False,
        shared_yaxes=True,
        column_widths=[0.12, 0.88],
        row_heights=[0.12, 0.06, 0.82],
        vertical_spacing=0.02,
        horizontal_spacing=0.02,
    )

    if col_link is not None:
        x_dend, y_dend = _dendrogram_coords(col_link, n, orientation="top")
        if x_dend:
            fig.add_trace(go.Scatter(x=x_dend, y=y_dend, mode="lines", line=dict(color="#7f8c8d", width=1), hoverinfo="skip", showlegend=False), row=1, col=2)

    fig.add_trace(go.Heatmap(
        z=[group_codes],
        x=list(range(n)),
        y=[0],
        colorscale=group_colorscale,
        showscale=False,
        hoverinfo="skip",
    ), row=2, col=2)

    if row_link is not None:
        x_dend, y_dend = _dendrogram_coords(row_link, m, orientation="left")
        if x_dend:
            fig.add_trace(go.Scatter(x=x_dend, y=y_dend, mode="lines", line=dict(color="#7f8c8d", width=1), hoverinfo="skip", showlegend=False), row=3, col=1)

    fig.add_trace(go.Heatmap(
        z=plot_df.values,
        x=list(range(n)),
        y=list(range(m)),
        colorscale=colorscale,
        zmid=zmid,
        colorbar=dict(title={"text": cbar_title, "side": "right"}, x=1.02, len=0.85),
        hovertemplate="Feature: %{y}<br>Sample: %{customdata}<br>Value: %{z:.3f}<extra></extra>",
        customdata=np.array([plot_df.columns.tolist()] * m),
    ), row=3, col=2)

    max_top = max(np.nanmax(np.abs(y_dend)) if (col_link is not None and y_dend) else 1.0, 1.0)
    max_left = max(np.nanmax(np.abs(x_dend)) if (row_link is not None and x_dend) else 1.0, 1.0)

    fig.update_xaxes(range=[-0.5, n - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=1, col=2)
    fig.update_yaxes(range=[0, max_top], showticklabels=False, showgrid=False, zeroline=False, row=1, col=2)

    fig.update_xaxes(range=[-0.5, n - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=2, col=2)
    fig.update_yaxes(range=[-0.5, 0.5], showticklabels=False, showgrid=False, zeroline=False, row=2, col=2)

    fig.update_xaxes(autorange="reversed", range=[0, max_left], showticklabels=False, showgrid=False, zeroline=False, row=3, col=1)
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, row=3, col=1)

    row_tick_size = max(7, min(style.get("tick_size", 11), int(220 / max(m, 1))))
    fig.update_xaxes(
        range=[-0.5, n - 0.5],
        tickmode="array",
        tickvals=list(range(n)),
        ticktext=plot_df.columns,
        tickangle=-45,
        side="bottom",
        tickfont=dict(size=max(7, style.get("tick_size", 11) - 2)),
        showgrid=False,
        zeroline=False,
        row=3, col=2,
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(m)),
        ticktext=plot_df.index,
        tickfont=dict(size=row_tick_size),
        side="right",
        showgrid=False,
        zeroline=False,
        row=3, col=2,
    )

    _apply_base_layout(fig, style, title=f"Top {m} most-variable lipids")
    fig.update_layout(
        margin=dict(l=80, r=140, t=100, b=120),
        paper_bgcolor=style.get("paper_bgcolor"),
        plot_bgcolor="white",
        font=dict(family=style.get("font_family"), color="#334155"),
    )
    return fig


def _extract_lipid_class(feature_id: str, meta: dict) -> str:
    cls = meta.get("top_candidate_class") or meta.get("class") or meta.get("lipid_class")
    if cls:
        return cls
    m = re.match(r"^([A-Za-z]+)", str(feature_id))
    return m.group(1) if m else "Unknown"


def _lipid_class_totals(df: pd.DataFrame, classes: list) -> pd.DataFrame:
    """Return per-sample total intensity per lipid class."""
    mat = df.copy()
    mat["class"] = classes
    return mat.groupby("class").sum(numeric_only=True)


def _group_stats(values_by_group: dict) -> tuple:
    means = []
    sems = []
    for g in sorted(values_by_group.keys()):
        vals = np.array([_safe_float(v) for v in values_by_group[g]])
        means.append(float(np.mean(vals)))
        sems.append(float(scipy_stats.sem(vals)) if len(vals) > 1 else 0.0)
    return means, sems


def generate_plot(dataset: models.Dataset, req: schemas.PlotRequest):
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata
    plot_type = req.plot_type
    params = req.parameters or {}
    style = _merge_style(req.style)

    if plot_type in ("bar", "box", "violin", "dot"):
        feature = _get_feature_index(dataset, params.get("feature"))
        title = f"{dataset.feature_metadata[feature].get('feature_id', feature)}"
        ordered_df = _reorder_columns(df, sample_meta, params.get("group_order", []))
        ordered_samples = ordered_df.columns.tolist()
        ordered_values = ordered_df.iloc[feature].values
        ordered_groups = [sample_meta.get(c, "unknown") for c in ordered_samples]
        color_map = _group_color_map(style, ordered_groups)

        if plot_type == "bar":
            fig = go.Figure()
            for g in sorted(set(ordered_groups)):
                idx = [i for i, gg in enumerate(ordered_groups) if gg == g]
                vals = [float(ordered_values[i]) for i in idx]
                samps = [ordered_samples[i] for i in idx]
                fig.add_trace(go.Bar(x=samps, y=vals, name=g, marker_color=color_map[g]))
            fig.update_layout(barmode="group", xaxis_title="Sample", yaxis_title="Abundance")
        elif plot_type == "box":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g in sorted(group_vals):
                fig.add_trace(go.Box(y=group_vals[g], name=g, boxpoints="all", marker_color=color_map[g]))
            fig.update_layout(xaxis_title="Group", yaxis_title="Abundance")
        elif plot_type == "violin":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g in sorted(group_vals):
                fig.add_trace(go.Violin(y=group_vals[g], name=g, box_visible=True, meanline_visible=True, line_color=color_map[g]))
            fig.update_layout(yaxis_title="Abundance")
        else:  # dot
            fig = go.Figure()
            for g in sorted(set(ordered_groups)):
                idx = [i for i, gg in enumerate(ordered_groups) if gg == g]
                vals = [float(ordered_values[i]) for i in idx]
                samps = [ordered_samples[i] for i in idx]
                fig.add_trace(go.Scatter(x=samps, y=vals, mode="markers", name=g, marker_color=color_map[g], marker_size=style.get("marker_size")))
            fig.update_layout(xaxis_title="Sample", yaxis_title="Abundance")
        _apply_base_layout(fig, style, title=f"{plot_type.title()} Plot: {title}")

    elif plot_type == "heatmap":
        heatmap_type = params.get("heatmap_type", "abundance")
        if heatmap_type != "correlation" and style.get("engine") == "publication":
            fig = _heatmap_publication(df, sample_meta, style, params)
            return json.loads(fig.to_json())
        top_n = int(params.get("top_n", 50))
        metric = params.get("metric", "euclidean")
        method = params.get("method", "average")
        scale = params.get("scale", "row_zscore")
        cluster_rows = bool(params.get("cluster_rows", True))
        cluster_cols = bool(params.get("cluster_cols", True))
        colorscale = style.get("heatmap_colorscale", "RdBu_r")

        if heatmap_type == "correlation":
            if cluster_cols and len(df.columns) > 2:
                try:
                    dist = pdist(df.T.values, metric=metric)
                    link = linkage(dist, method=method)
                    order = leaves_list(link)
                    df = df.iloc[:, order]
                except Exception:
                    pass
            corr = df.corr().fillna(0)
            fig = go.Figure(data=go.Heatmap(
                z=corr.values, x=corr.columns, y=corr.index,
                colorscale=colorscale, zmid=1,
                colorbar=dict(title={"text": "r", "side": "right"})))
            _apply_base_layout(fig, style, title="Sample Correlation Heatmap")
            fig.update_layout(xaxis=dict(side="top", tickangle=-45))
        else:
            plot_df = df.copy()
            row_std = plot_df.std(axis=1, numeric_only=True)
            top_idx = row_std.nlargest(min(top_n, len(plot_df))).index
            plot_df = plot_df.loc[top_idx]

            if scale == "log10":
                plot_df = np.log10(plot_df.replace(0, np.nan)).fillna(0)
                zmid = None
                cbar_title = "log10 intensity"
            elif scale == "none":
                zmid = None
                cbar_title = "Intensity"
            else:  # row_zscore
                plot_df = (plot_df.sub(plot_df.mean(axis=1), axis=0).div(plot_df.std(axis=1).replace(0, np.nan), axis=0)).fillna(0)
                zmid = 0
                cbar_title = "Row z-score"

            if cluster_rows and len(plot_df) > 2:
                try:
                    dist = pdist(plot_df.values, metric=metric)
                    link = linkage(dist, method=method)
                    order = leaves_list(link)
                    plot_df = plot_df.iloc[order]
                except Exception:
                    pass
            if cluster_cols and len(plot_df.columns) > 2:
                try:
                    dist = pdist(plot_df.T.values, metric=metric)
                    link = linkage(dist, method=method)
                    order = leaves_list(link)
                    plot_df = plot_df.iloc[:, order]
                except Exception:
                    pass

            sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
            group_order = sorted(set(sample_groups.values()))
            if "Unknown" in group_order:
                group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
            gcolor_map = _group_color_map(style, group_order)
            group_codes = [group_order.index(sample_groups.get(c, "Unknown")) for c in plot_df.columns]
            n_groups = max(len(group_order), 1)
            if n_groups == 1:
                group_colorscale = [[0, gcolor_map[group_order[0]]], [1, gcolor_map[group_order[0]]]]
            else:
                group_colorscale = [[i / (n_groups - 1), gcolor_map[g]] for i, g in enumerate(group_order)]

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.06, 0.94])
            fig.add_trace(go.Heatmap(
                z=[group_codes],
                x=plot_df.columns,
                y=[""],
                colorscale=group_colorscale,
                showscale=False,
                hoverinfo="skip",
            ), row=1, col=1)
            fig.add_trace(go.Heatmap(
                z=plot_df.values,
                x=plot_df.columns,
                y=plot_df.index,
                colorscale=colorscale,
                zmid=zmid,
                colorbar=dict(title={"text": cbar_title, "side": "right"}, x=1.02, len=0.85),
            ), row=2, col=1)

            fig.update_layout(
                font={"family": style.get("font_family"), "color": "#334155"},
                paper_bgcolor=style.get("paper_bgcolor"),
                plot_bgcolor=style.get("plot_bgcolor"),
                title={
                    "text": f"Top {len(plot_df)} most-variable lipids",
                    "font": {"size": style.get("title_size"), "color": "#1e293b"},
                    "x": 0.5,
                    "xanchor": "center",
                    "y": 0.99,
                    "yanchor": "top",
                    "pad": {"b": 20},
                },
                margin={"l": max(80, 6 * max([len(str(i)) for i in plot_df.index])), "r": 120, "t": 100, "b": 80},
            )
            max_label_len = max([len(str(i)) for i in plot_df.index])
            row_tick_size = max(7, min(style.get("tick_size", 11), int(220 / max(len(plot_df.index), 1))))
            fig.update_xaxes(side="top", tickangle=-45, automargin=True, showticklabels=False, row=1, col=1)
            fig.update_xaxes(side="top", tickangle=-45, automargin=True, tickfont={"size": max(7, style.get("tick_size", 11) - 2)}, row=2, col=1)
            fig.update_yaxes(showticklabels=False, row=1, col=1)
            fig.update_yaxes(tickfont={"size": row_tick_size}, automargin=True, row=2, col=1)

    elif plot_type == "pca":
        ptype = params.get("plot", "score")
        components = max(2, min(int(params.get("components", 3)), len(df.columns), len(df)))
        do_scale = bool(params.get("scale", True))
        X = df.dropna().T
        if X.empty or X.shape[1] < 2 or X.shape[0] < 2:
            fig = go.Figure()
            _apply_base_layout(fig, style, title="Not enough data for PCA")
            return json.loads(fig.to_json())
        X = X.fillna(X.min().min() / 2)
        Xs = StandardScaler().fit_transform(X) if do_scale else X.values
        pca = PCA_SKL(n_components=components)
        scores = pca.fit_transform(Xs)
        labels = [sample_meta.get(c, c) for c in X.index]
        color_map = _group_color_map(style, labels)

        if ptype == "scree":
            fig = px.bar(x=[f"PC{i+1}" for i in range(len(pca.explained_variance_ratio_))],
                         y=pca.explained_variance_ratio_ * 100,
                         labels={"x": "Principal Component", "y": "Variance Explained (%)"})
            _apply_base_layout(fig, style, title="PCA Scree Plot")
        elif ptype == "loading":
            loadings = pca.components_[0]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(dataset.feature_metadata)]
            top_idx = np.argsort(np.abs(loadings))[-50:]
            fig = px.bar(x=[feat_ids[i] for i in top_idx], y=[loadings[i] for i in top_idx],
                         labels={"x": "Feature", "y": "PC1 Loading"})
            _apply_base_layout(fig, style, title="PCA Top Loadings (PC1)")
        elif ptype == "biplot":
            fig = go.Figure()
            for g in sorted(set(labels)):
                idx = [i for i, l in enumerate(labels) if l == g]
                idx_arr = np.array(idx)
                fig.add_trace(go.Scatter(
                    x=scores[idx_arr, 0], y=scores[idx_arr, 1], mode="markers",
                    name=g, marker_color=color_map[g], marker_size=style.get("marker_size"),
                    customdata=np.column_stack([[X.index[i] for i in idx], [g] * len(idx)]),
                    hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
                ))
            loadings = pca.components_[:2]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(dataset.feature_metadata)]
            x_scale = max(np.abs(scores[:, 0]).max(), 1e-9)
            y_scale = max(np.abs(scores[:, 1]).max(), 1e-9)
            for i in range(min(20, len(loadings[0]))):
                fig.add_trace(go.Scatter(x=[0, loadings[0, i]*x_scale], y=[0, loadings[1, i]*y_scale],
                                         mode="lines+text", text=["", feat_ids[i]], textposition="top center",
                                         line=dict(color="gray"), showlegend=False))
            fig.update_layout(xaxis_title=f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                              yaxis_title=f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)")
            _apply_base_layout(fig, style, title="PCA Biplot")
        else:
            if style.get("engine") == "publication":
                fig = _pca_publication(scores, labels, pca, X.index.tolist(), style, params)
                return json.loads(fig.to_json())
            fig = go.Figure()
            for g in sorted(set(labels)):
                idx = [i for i, l in enumerate(labels) if l == g]
                idx_arr = np.array(idx)
                fig.add_trace(go.Scatter(
                    x=scores[idx_arr, 0], y=scores[idx_arr, 1], mode="markers",
                    name=g, marker_color=color_map[g], marker_size=style.get("marker_size"),
                    customdata=np.column_stack([[X.index[i] for i in idx], [g] * len(idx)]),
                    hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
                ))
            fig.update_layout(xaxis_title=f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                              yaxis_title=f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)")
            _apply_base_layout(fig, style, title="PCA Score Plot")

    elif plot_type == "volcano":
        fc_thresh = float(params.get("fc_threshold", 0.5))
        p_thresh = float(params.get("p_threshold", 0.05))
        show_labels = bool(params.get("show_labels", False))
        top_n = max(0, int(params.get("top_n", 10)))
        up_color = style.get("up_color", "#c44e52")
        down_color = style.get("down_color", "#2e6575")
        ns_color = style.get("non_significant_color", "#a0aec0")

        points = _build_volcano_points(params.get("stats", []), fc_thresh, p_thresh, up_color, down_color, ns_color)

        if style.get("engine") == "publication":
            fig = _volcano_publication(points, fc_thresh, p_thresh, style, params)
            return json.loads(fig.to_json())

        fig = go.Figure()
        groups = {}
        for p in points:
            groups.setdefault(p["label"], []).append(p)
        names = {"UP": f"Higher in {params.get('group_b','B')}", "DOWN": f"Lower in {params.get('group_b','B')}", "NS": "Not significant"}
        for label in ["UP", "DOWN", "NS"]:
            if label in groups:
                pts = groups[label]
                fig.add_trace(go.Scatter(
                    x=[p["lfc"] for p in pts],
                    y=[p["neglogp"] for p in pts],
                    mode="markers",
                    name=names.get(label, label),
                    marker=dict(color=pts[0]["color"], size=style.get("marker_size"), line=dict(width=0.5, color="white")),
                    text=[p["name"] for p in pts],
                    hovertemplate="%{text}<br>log2FC: %{x:.3f}<br>-log10 padj: %{y:.3f}<extra></extra>",
                ))

        fig.add_hline(y=-np.log10(p_thresh), line_dash="dash", line_color=ns_color)
        fig.add_vline(x=fc_thresh, line_dash="dash", line_color=ns_color)
        fig.add_vline(x=-fc_thresh, line_dash="dash", line_color=ns_color)
        fig.update_layout(xaxis_title="log2 fold change", yaxis_title="-log10 p-value")
        _apply_base_layout(fig, style, title="Volcano Plot")

        if show_labels and top_n > 0 and points:
            candidates = [p for p in points if abs(p["lfc"]) >= fc_thresh]
            candidates.sort(key=lambda p: p["padj"])
            top = candidates[:top_n]
            if top:
                x_vals = [p["lfc"] for p in top]
                y_vals = [p["neglogp"] for p in top]
                labels = [p["name"] for p in top]
                xs_all = [p["lfc"] for p in points]
                ys_all = [p["neglogp"] for p in points]
                x_min, x_max = min(xs_all) if xs_all else -1, max(xs_all) if xs_all else 1
                y_min, y_max = min(ys_all) if ys_all else 0, max(ys_all) if ys_all else 1
                positions = list(_place_labels(x_vals, y_vals, labels, x_min, x_max, y_min, y_max))
                fig.add_trace(go.Scatter(
                    x=[x for x, _, _ in positions],
                    y=[y for _, y, _ in positions],
                    mode="text",
                    text=labels,
                    textposition=[pos[2] for pos in positions],
                    textfont=dict(size=9, color="#1e293b"),
                    hoverinfo="skip",
                    showlegend=False,
                    cliponaxis=False,
                ))

    elif plot_type == "lipid_class":
        classes = [_extract_lipid_class(f.get("feature_id", ""), f) for f in dataset.feature_metadata]
        totals = _lipid_class_totals(df, classes)
        sample_groups = {c: sample_meta.get(c, "unknown") for c in totals.columns}
        unique_groups = sorted(set(sample_groups.values()))
        fig = go.Figure()
        color_map = _group_color_map(style, unique_groups)
        x = totals.index.tolist()
        for g in unique_groups:
            cols = [c for c in totals.columns if sample_groups[c] == g]
            means = [float(np.mean([_safe_float(totals.loc[cls, col]) for col in cols])) for cls in x]
            fig.add_trace(go.Bar(name=g, x=x, y=means, marker_color=color_map[g]))
        fig.update_layout(barmode="group", xaxis_title="Lipid class", yaxis_title="Total intensity (normalized)")
        _apply_base_layout(fig, style, title="Total abundance by lipid class × group")

    elif plot_type == "per_lipid_bars":
        stats_data = params.get("stats", [])
        group_a = params.get("group_a", "A")
        group_b = params.get("group_b", "B")
        top_n = int(params.get("top_n", 8))
        # sort by p-value ascending
        sorted_stats = sorted([s for s in stats_data if s.get("padj") is not None], key=lambda s: _safe_float(s.get("padj", 1), 1.0))[:top_n]
        figures = []
        for s in sorted_stats:
            fid = s.get("feature_id", "")
            idx = _get_feature_index(dataset, fid)
            samples = df.columns.tolist()
            values = df.iloc[idx].values
            groups = [sample_meta.get(c, "unknown") for c in samples]
            color_map = _group_color_map(style, [group_a, group_b])
            group_vals = {group_a: [], group_b: []}
            for c, g in zip(samples, groups):
                if g == group_a or g == group_b:
                    group_vals.setdefault(g, []).append(_safe_float(df.loc[df.index[idx], c]))
            ordered = [g for g in [group_a, group_b] if group_vals.get(g)]
            means = []
            sems = []
            for g in ordered:
                vals = np.array(group_vals[g])
                means.append(float(np.mean(vals)))
                sems.append(float(scipy_stats.sem(vals)) if len(vals) > 1 else 0.0)
            fig = go.Figure()
            xpos = list(range(len(ordered)))
            fig.add_trace(go.Bar(
                x=xpos,
                y=means,
                marker_color=[color_map[g] for g in ordered],
                error_y=dict(type="data", array=sems, visible=True),
                showlegend=False,
            ))
            # overlay individual points
            np.random.seed(42)
            for i, g in enumerate(ordered):
                vals = group_vals[g]
                jitter = (np.random.rand(len(vals)) - 0.5) * 0.3
                fig.add_trace(go.Scatter(
                    x=[i + j for j in jitter],
                    y=vals,
                    mode="markers",
                    marker=dict(color="#1e293b", size=6, line=dict(width=1, color="white")),
                    showlegend=False,
                    hoverinfo="skip",
                ))
            title = f"{fid}"
            if s.get("padj", 1) < 0.01:
                title += " **"
            elif s.get("padj", 1) < 0.05:
                title += " *"
            fig.update_xaxes(tickmode="array", tickvals=xpos, ticktext=ordered, tickangle=0)
            fig.update_layout(xaxis_title="", yaxis_title="Mean ± SEM")
            _apply_base_layout(fig, style, title=title)
            figures.append(json.loads(fig.to_json()))
        return figures

    elif plot_type == "outlier":
        fig = _outlier_plot(df, sample_meta, style, params)

    elif plot_type == "functional":
        fig = _functional_volcano(df, sample_meta, dataset.feature_metadata, style, params)

    elif plot_type == "food_profile":
        fig = _food_profile(df, sample_meta, dataset.feature_metadata, style, params)

    elif plot_type == "rt_mz":
        mz = [_safe_float(f.get("mz", 0)) for f in dataset.feature_metadata]
        rt = [_safe_float(f.get("rt", 0)) for f in dataset.feature_metadata]
        grades = [str(f.get("grade", "unknown")) for f in dataset.feature_metadata]
        fig = px.scatter(x=mz, y=rt, color=grades,
                         labels={"x": "m/z", "y": "Retention Time"})
        _apply_base_layout(fig, style, title="Retention Time vs m/z")

    else:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Unsupported plot type")

    return json.loads(fig.to_json())

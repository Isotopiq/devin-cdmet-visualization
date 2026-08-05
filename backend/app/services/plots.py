import base64
import io
import json
import math
import re
from typing import Dict, List
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib import cm
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import linkage, leaves_list, dendrogram as scipy_dendrogram
from scipy.spatial.distance import pdist, mahalanobis as _mahalanobis
from scipy import stats as scipy_stats
from sklearn.decomposition import PCA as PCA_SKL
from sklearn.preprocessing import StandardScaler
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe
from app.services.lipid_indices import compute_functional_indices, compute_food_profile_indices
from app.services.lipid_building_blocks import compute_building_blocks
from app.services.multivariate import pls_da_analysis, opls_da_analysis, _prepare_X
from app.services.biomarkers import biomarker_analysis
from app.services.permanova import permanova_analysis


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


def _apply_base_layout(fig: go.Figure, style: dict, title: str | None = None, x_labels: list | None = None, y_labels: list | None = None):
    longest_x = max([len(str(l)) for l in (x_labels or [])] or [0])
    longest_y = max([len(str(l)) for l in (y_labels or [])] or [0])
    n_x = len(x_labels or [])
    n_y = len(y_labels or [])
    rotate_x = (longest_x > 10) or (n_x > 12)
    rotate_y = longest_y > 10
    bottom = max(80, int(longest_x * style.get("tick_size", 11) * 0.6)) if (longest_x > 12 or n_x > 12) else 70
    left = max(80, int(longest_y * style.get("tick_size", 11) * 0.55)) if (longest_y > 10 or n_y > 12) else 70

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
        "margin": {"l": left, "r": 50, "t": 100, "b": bottom},
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
    fig.update_xaxes(automargin=True, tickfont={"size": style.get("tick_size")}, title_font={"size": style.get("axis_label_size")}, title_standoff=18)
    fig.update_yaxes(automargin=True, tickfont={"size": style.get("tick_size")}, title_font={"size": style.get("axis_label_size")}, title_standoff=30)
    if rotate_x:
        fig.update_xaxes(tickangle=-45)
    if rotate_y:
        fig.update_yaxes(tickangle=0)


def _get_feature_index(feature_metadata, feature_arg):
    if feature_arg is None:
        return 0
    if isinstance(feature_arg, int):
        return feature_arg
    for i, meta in enumerate(feature_metadata):
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


def _intensity_from_transformed(values, history: list | None) -> np.ndarray:
    """Return positive intensity-like values from possibly log/scaled data."""
    vals = np.array(values, dtype=float)
    step = (history or [{}])[-1] if history else None
    params = step.get("params", {}) if isinstance(step, dict) else {}
    log_transform = params.get("log_transform", False) if params else False
    if log_transform:
        vals = np.clip(vals, -20, 50)
        vals = 2 ** vals
    else:
        mn = float(np.nanmin(vals))
        if mn < 0:
            vals = vals - mn + 1e-6
    return np.where(np.isfinite(vals), vals, 0.0)


def _intensity_df(df: pd.DataFrame, history: list | None) -> pd.DataFrame:
    """Return a DataFrame of positive intensity-like values."""
    if df.empty:
        return df
    flat = _intensity_from_transformed(df.values.ravel(), history)
    return pd.DataFrame(flat.reshape(df.shape), index=df.index, columns=df.columns)


def _shorten_name(name: str, max_len: int = 24) -> str:
    s = str(name)
    # Compound Discoverer / LipidSearch-style sample column headers often contain
    # prefixes like "Area: " and suffixes like ".raw" and "(F8)". Strip those
    # before plotting so axis labels/ticks show only the sample identifier.
    m = re.search(r"Area:\s*(.+?)(?:\.raw(?:\s*\([^)]*\))?\s*)$", s, flags=re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    else:
        # Remove trailing ".raw (F#)" or ".raw" etc.
        s = re.sub(r"\.raw(?:\s*\([^)]*\))?\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(F\d+(?::\d+)?(?:\s*[^)]*)?\)\s*$", "", s, flags=re.IGNORECASE)
    s = s.strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _clean_lipid_name(name: str) -> str:
    """Return a lipid species string with adducts and non-chain trailing tags removed."""
    s = str(name).strip()
    # Remove common trailing adducts such as [M-H]-, [M+H]+, [M+Na]+, [2M-H]-
    s = re.sub(r"\s*\[[^\]]+\][+-]?\s*$", "", s)
    # Remove trailing parenthetical annotations (isotope labels, duplicates, etc.)
    # but keep parentheses that contain lipid chains (they have a colon or underscore).
    while True:
        m = re.search(r"\s*\(([^)]+)\)\s*$", s)
        if not m:
            break
        inner = m.group(1)
        if re.search(r"[:_]", inner):
            break
        s = s[:m.start()].strip()
    return s


def _tick_text_step(n: int, max_labels: int = 30) -> int:
    if n <= max_labels:
        return 1
    return max(1, int(np.ceil(n / max_labels)))


def _place_labels(xs, ys, labels, x_min, x_max, y_min, y_max, plot_width_px=900, plot_height_px=520, font_px=9):
    """Return label center coordinates, avoiding each other and the original points."""
    placed = []
    x_range = max(x_max - x_min, 1e-9)
    y_range = max(y_max - y_min, 1e-9)
    # approximate pixel-to-data scaling
    px_to_x = x_range / plot_width_px
    px_to_y = y_range / plot_height_px
    # width/height of one character in data units
    char_w = font_px * 0.55 * px_to_x
    char_h = font_px * 1.4 * px_to_y
    margin = (20 * px_to_x, 10 * px_to_y)

    angles = [0.0, 0.524, 1.047, 1.571, 2.094, 2.618, 3.142, 3.665, 4.189, 4.712, 5.236, 5.760]

    def rect(x, y, w, h):
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def overlaps(r1, r2):
        return not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1])

    # Use data points as obstacles so labels don't cover the markers
    for x, y in zip(xs, ys):
        placed.append(rect(x, y, char_w * 1.2, char_h * 1.2))

    for x, y, text in zip(xs, ys, labels):
        w = max(len(text) * char_w + char_w * 0.8, char_w * 2)
        h = char_h * 1.6
        # candidate offsets scale with the label box so labels don't overlap
        best = None
        best_score = None
        for r_factor in [0.9, 1.4, 2.0, 2.7, 3.4, 4.2]:
            for a in angles:
                dx = math.cos(a) * r_factor * (w / 2 + char_w)
                dy = math.sin(a) * r_factor * (h / 2 + char_h)
                nx = x + dx
                ny = y + dy
                r = rect(nx, ny, w, h)
                if r[0] < x_min - margin[0] or r[2] > x_max + margin[0] or r[1] < y_min - margin[1] or r[3] > y_max + margin[1]:
                    continue
                if any(overlaps(r, pr) for pr in placed):
                    continue
                score = (dx ** 2 + dy ** 2) ** 0.5
                if best is None or score < best_score:
                    best = (nx, ny)
                    best_score = score
            if best is not None:
                break
        if best is None:
            # Last resort: place directly above the point
            best = (x, y + char_h * 1.5)
        placed.append(rect(best[0], best[1], w, h))
        yield (best[0], best[1], "middle center")


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


def _volcano_publication(points, fc_thresh, padj_thresh, style, params):
    fig = go.Figure()
    xs = [p["lfc"] for p in points]
    ys = [p["neglogp"] for p in points]
    x_min = min(xs) if xs else -1
    x_max = max(xs) if xs else 1
    y_min = 0
    y_max = max(ys) if ys else 1
    padj_thresh = max(padj_thresh, 1e-300)
    y_thr = -np.log10(padj_thresh)
    x_abs = max(abs(x_min), abs(x_max), fc_thresh)
    x_min, x_max = -x_abs, x_abs
    x_pad = max((x_max - x_min) * 0.08, 0.2)
    y_max = max(y_max, y_thr * 1.25) * 1.45
    x_min -= x_pad
    x_max += x_pad

    if -fc_thresh > x_min:
        fig.add_vrect(x0=x_min, x1=-fc_thresh, fillcolor="rgba(214,234,248,0.35)", line_width=0, layer="below")
    if fc_thresh < x_max:
        fig.add_vrect(x0=fc_thresh, x1=x_max, fillcolor="rgba(250,219,216,0.35)", line_width=0, layer="below")

    line_color = "#475569"
    fig.add_vline(x=-fc_thresh, line_dash="dash", line_color=line_color, line_width=1.5)
    fig.add_vline(x=fc_thresh, line_dash="dash", line_color=line_color, line_width=1.5)
    fig.add_hline(y=y_thr, line_dash="dash", line_color=line_color, line_width=1.5)

    group_a = params.get("group_a", "A")
    group_b = params.get("group_b", "B")
    legend_names = {
        "UP": f"Higher in {group_b}",
        "DOWN": f"Higher in {group_a}",
        "NS": "Not significant",
    }
    for label in ["DOWN", "NS", "UP"]:
        pts = [p for p in points if p["label"] == label]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p["lfc"] for p in pts],
            y=[p["neglogp"] for p in pts],
            mode="markers",
            name=legend_names[label],
            marker=dict(color=pts[0]["color"], size=style.get("marker_size"), line=dict(width=0.5, color="white")),
            text=[_shorten_name(p["name"], 35) for p in pts],
            hovertemplate="%{text}<br>log2FC: %{x:.3f}<br>-log10 padj: %{y:.3f}<extra></extra>",
        ))

    if bool(params.get("show_labels", False)) and points:
        candidates = [p for p in points if abs(p["lfc"]) >= fc_thresh and p["padj"] < padj_thresh]
        candidates.sort(key=lambda p: p["padj"])
        top_n = max(0, int(params.get("top_n", 10)))
        top = candidates[:top_n]
        if top:
            x_vals = [p["lfc"] for p in top]
            y_vals = [p["neglogp"] for p in top]
            labels = [_shorten_name(p["name"], 35) for p in top]
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
            title=dict(text=f"log2 Fold Change ({group_b} / {group_a})", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            range=[x_min, x_max],
            showgrid=True,
            gridcolor="#e5e5e5",
            zeroline=False,
            automargin=True,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text="-log10 p-value", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            range=[0, y_max],
            showgrid=True,
            gridcolor="#e5e5e5",
            zeroline=False,
            automargin=True,
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
        margin=dict(l=80, r=90, t=140, b=70),
        font=dict(family=style.get("font_family"), color="#334155"),
    )
    return fig


def _pca_publication(scores, labels, pca, sample_names, style, params):
    fig = go.Figure()
    display_names = [_shorten_name(n) for n in sample_names]
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
            customdata=np.column_stack([[display_names[i] for i in idx], [g] * len(idx)]),
            hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
        ))

    positions = list(_place_labels(scores[:, 0].tolist(), scores[:, 1].tolist(), display_names, scores[:, 0].min(), scores[:, 0].max(), scores[:, 1].min(), scores[:, 1].max()))
    if positions:
        fig.add_trace(go.Scatter(
            x=[p[0] for p in positions],
            y=[p[1] for p in positions],
            mode="text",
            text=display_names,
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
            title=dict(text=f"PC1 ({exp1:.1f}%)", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False, automargin=True,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text=f"PC2 ({exp2:.1f}%)", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False, automargin=True,
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
    display_names = [_shorten_name(n) for n in sample_names]
    groups = [sample_meta.get(c, "Unknown") for c in sample_names]
    color_map = _group_color_map(style, sorted(set(groups)))

    group_samples_by_group = bool(params.get("group_samples_by_group") or params.get("outlier_group_by_group"))
    if group_samples_by_group:
        group_order_param = params.get("group_order") or params.get("outlier_group_order") or []
        present = set(groups)
        ordered_groups = [g for g in group_order_param if g in present]
        ordered_groups.extend([g for g in sorted(present) if g not in ordered_groups])
        by_group = {}
        for name, g, v in zip(display_names, groups, md2):
            by_group.setdefault(g, []).append((name, g, v))
        for g in by_group:
            by_group[g].sort(key=lambda x: x[2])
        sorted_data = []
        for g in reversed(ordered_groups):
            sorted_data.extend(by_group.get(g, []))
        if sorted_data:
            names, grps, values = zip(*sorted_data)
            names, grps, values = list(names), list(grps), list(values)
        else:
            names, grps, values = [], [], []
    else:
        data = sorted(zip(display_names, groups, md2), key=lambda x: x[2], reverse=True)
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
    longest_name = max([len(str(n)) for n in names] or [0])
    tick_font = max(6, min(10, style.get("tick_size", 11) - 1)) if len(names) > 30 else max(7, style.get("tick_size", 11) - 1)
    left_margin = max(120, int(longest_name * tick_font * 0.85))
    plot_height = max(500, len(names) * 13)
    fig.update_layout(
        title=dict(text=f"<b>{title_text}</b>", font=dict(size=style.get("title_size"), color="#1e293b"), x=0.0, xanchor="left"),
        xaxis=dict(
            title=dict(text="Mahalanobis distance", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            showgrid=True, gridcolor="#e5e5e5", zeroline=False, automargin=True,
            tickfont=dict(size=style.get("tick_size")),
        ),
        yaxis=dict(
            title=dict(text="Sample", font=dict(size=style.get("axis_label_size"), color="#000"), standoff=30),
            categoryorder="array", categoryarray=names,
            tickmode="linear", dtick=1,
            showgrid=False, automargin=True, tickfont=dict(size=tick_font),
        ),
        legend=dict(
            title=dict(text="group", font=dict(size=style.get("tick_size"))),
            orientation="v",
            font=dict(size=style.get("tick_size")),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=left_margin, r=150, t=80, b=70),
        font=dict(family=style.get("font_family"), color="#334155"),
        bargap=0.15,
        height=plot_height,
    )
    return fig


def _category_volcano_figure(items, title, style, params=None):
    params = params or {}
    fc_thresh = float(params.get("fc_threshold", 1.0))
    p_thresh = float(params.get("p_threshold", 0.05))
    cat_order = sorted({it["category"] for it in items})
    cat_colors = {}
    palette = style.get("group_colors", ["#2e6575", "#e9a47f", "#81b29a", "#9d8189", "#f2cc8f", "#7eb5c9"])
    for i, c in enumerate(cat_order):
        cat_colors[c] = palette[i % len(palette)]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=False,
        vertical_spacing=0.18,
        row_heights=[0.62, 0.38],
        specs=[[{"type": "scatter"}], [{"type": "table"}]],
        subplot_titles=(title, "Interpretation table (top by significance)"),
    )

    y_thr = -np.log10(p_thresh)
    plot_width_px = max(style.get("width", 700), 500)
    max_y = max([max(0.0, -np.log10(max(it["padj"], 1e-300))) for it in items] + [y_thr], default=1.0)
    min_x = min([it["log2fc"] for it in items] + [-1.5 * fc_thresh, 1.5 * fc_thresh], default=-1.5 * fc_thresh)
    max_x = max([it["log2fc"] for it in items] + [-1.5 * fc_thresh, 1.5 * fc_thresh], default=1.5 * fc_thresh)
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

    fig.add_hline(y=y_thr, line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)
    fig.add_vline(x=fc_thresh, line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)
    fig.add_vline(x=-fc_thresh, line_dash="dash", line_color="#94a3b8", line_width=1, row=1, col=1)

    top_items = sorted(items, key=lambda it: (it["padj"], -abs(it["log2fc"])))
    top_items = [it for it in top_items if abs(it["log2fc"]) >= fc_thresh and it["padj"] < p_thresh][:max(10, len(top_items) // 2 + 1)]
    top_items = sorted(top_items, key=lambda it: it["padj"])
    table_colors = [cat_colors[it["category"]] for it in top_items]
    n_rows = len(top_items)
    font_colors = ["#FFFFFF"] * n_rows if n_rows else "#334155"
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
            font=dict(size=10, color=[font_colors, font_colors, "#334155", "#334155", "#334155"]),
            height=22,
        ),
    ), row=2, col=1)

    # group legend (only visible in the legend, not on the plot)
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    group_colors = _group_color_map(style, [group_a, group_b])
    for grp in [group_a, group_b]:
        if grp and grp in group_colors:
            fig.add_trace(go.Scatter(
                x=[0], y=[0],
                mode="markers",
                marker=dict(color=group_colors[grp], size=10),
                name=grp,
                visible="legendonly",
                hoverinfo="skip",
                showlegend=True,
            ), row=1, col=1)

    _apply_base_layout(fig, style, title="")
    fig.update_layout(
        xaxis=dict(title=dict(text="log2 fold change", font=dict(size=style.get("axis_label_size", 12)), standoff=18), zeroline=False, showgrid=True, gridcolor="#e5e5e5", automargin=True, range=[min_x, max_x]),
        yaxis=dict(title=dict(text="-log10(adjusted P)", font=dict(size=style.get("axis_label_size", 12)), standoff=30), showgrid=True, gridcolor="#e5e5e5", automargin=True, range=[0, max(1.3, max_y) * 1.1]),
        legend=dict(title=dict(text="Legend"), orientation="v", yanchor="top", y=1, xanchor="left", x=1.02, bgcolor="rgba(255,255,255,0.85)"),
        margin=dict(l=80, r=140, t=80, b=80),
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
    return _category_volcano_figure(indices, f"Functional lipid indices: {group_b} vs {group_a}", style, params)


def _food_profile(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    indices = compute_food_profile_indices(df, feature_metadata, sample_meta, group_a, group_b)
    if not indices:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Lipid food profile")
        return fig
    return _category_volcano_figure(indices, f"Lipid food profile: {group_b} vs {group_a}", style, params)


def _chain_space_figure(df, sample_meta, feature_metadata, style, params, history=None):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    int_df = _intensity_df(df, history)
    result = compute_building_blocks(int_df, feature_metadata, sample_meta, group_a, group_b)
    rows = result.get("rows", [])
    if not rows:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Chain space (no chains parsed)")
        return fig

    xs = [r["carbon"] for r in rows]
    ys = [r["db"] for r in rows]
    log2fc = [r["log2fc"] for r in rows]
    size = [max(5, min(35, np.log10(max(r["mean_a"] + r["mean_b"], 1e-9)) * 4 + 5)) for r in rows]
    text = [f"{r['name']}<br>log2FC: {r['log2fc']:.2f}<br>p-adj: {r['padj']:.3f}" for r in rows]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Chain space (carbon × double bonds)", "Chain type composition", "Chain-length distribution", "Unsaturation distribution"),
        vertical_spacing=0.24,
        horizontal_spacing=0.14,
    )

    for i, ctype in enumerate(["acyl", "alkyl", "plasmalogen"]):
        sub = [r for r in rows if r["chain_type"] == ctype]
        if not sub:
            continue
        showscale = i == 0
        marker = dict(
            color=[r["log2fc"] for r in sub],
            colorscale="RdBu_r",
            size=[max(5, min(35, np.log10(max(r["mean_a"] + r["mean_b"], 1e-9)) * 4 + 5)) for r in sub],
            sizemode="diameter",
            line=dict(width=0.5, color="white"),
            showscale=showscale,
        )
        if showscale:
            marker["colorbar"] = dict(
                title={"text": "log2FC", "side": "right"},
                x=1.04,
                xanchor="left",
                y=0.82,
                yanchor="middle",
                len=0.45,
                thickness=12,
                outlinewidth=0,
            )
        fig.add_trace(go.Scatter(
            x=[r["carbon"] for r in sub],
            y=[r["db"] for r in sub],
            mode="markers",
            name=ctype,
            marker=marker,
            text=[f"{r['name']}<br>log2FC: {r['log2fc']:.2f}<br>p-adj: {r['padj']:.3f}" for r in sub],
            hovertemplate="%{text}<extra></extra>",
        ), row=1, col=1)

    summary = result.get("summary", {})
    group_colors = _group_color_map(style, [group_a, group_b])

    by_type = summary.get("by_type", {})
    types = sorted({k for d in by_type.values() for k in d.keys()})
    for g in [group_a, group_b]:
        vals = [max(by_type.get(g, {}).get(t, 0.0), 0.0) for t in types]
        fig.add_trace(go.Bar(name=g, x=types, y=vals, marker_color=group_colors.get(g)), row=1, col=2)

    by_carbon = summary.get("by_carbon", {})
    carbons = sorted({k for d in by_carbon.values() for k in d.keys()})
    for g in [group_a, group_b]:
        vals = [max(by_carbon.get(g, {}).get(c, 0.0), 0.0) for c in carbons]
        fig.add_trace(go.Bar(name=g, x=[str(c) for c in carbons], y=vals, marker_color=group_colors.get(g), showlegend=False), row=2, col=1)

    by_db = summary.get("by_db", {})
    dbs = sorted({k for d in by_db.values() for k in d.keys()})
    for g in [group_a, group_b]:
        vals = [max(by_db.get(g, {}).get(d, 0.0), 0.0) for d in dbs]
        fig.add_trace(go.Bar(name=g, x=[str(d) for d in dbs], y=vals, marker_color=group_colors.get(g), showlegend=False), row=2, col=2)

    fig.update_xaxes(title_text="Carbon atoms", row=1, col=1)
    fig.update_yaxes(title_text="Double bonds", row=1, col=1)
    fig.update_xaxes(title_text="Chain type", row=1, col=2)
    fig.update_yaxes(title_text="Total intensity", row=1, col=2)
    fig.update_xaxes(title_text="Carbon atoms", row=2, col=1)
    fig.update_yaxes(title_text="Total intensity", row=2, col=1)
    fig.update_xaxes(title_text="Double bonds", row=2, col=2)
    fig.update_yaxes(title_text="Total intensity", row=2, col=2)

    carbon_step = _tick_text_step(len(carbons), max_labels=10)
    db_step = _tick_text_step(len(dbs), max_labels=10)
    fig.update_xaxes(
        tickmode="array",
        tickvals=[str(carbons[i]) for i in range(0, len(carbons), carbon_step)],
        ticktext=[str(carbons[i]) for i in range(0, len(carbons), carbon_step)],
        tickangle=0,
        tickfont={"size": 9},
        row=2, col=1,
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=[str(dbs[i]) for i in range(0, len(dbs), db_step)],
        ticktext=[str(dbs[i]) for i in range(0, len(dbs), db_step)],
        tickangle=0,
        tickfont={"size": 9},
        row=2, col=2,
    )

    all_x_labels = list(map(str, carbons)) + list(types) + list(map(str, dbs))
    _apply_base_layout(fig, style, title=None, x_labels=all_x_labels)
    fig.update_layout(
        title={"text": f"Chain space: {group_b} vs {group_a}", "font": {"size": style.get("title_size"), "color": "#1e293b"}, "x": 0.5, "xanchor": "center"},
        barmode="group",
        legend={"orientation": "h", "y": -0.18},
        margin={"l": 100, "r": 160, "t": 100, "b": 120},
    )
    fig.update_xaxes(tickangle=0, tickfont={"size": 9}, row=1, col=2)
    fig.update_yaxes(title_standoff=45, row=1, col=1)
    fig.update_yaxes(title_standoff=45, row=1, col=2)
    fig.update_yaxes(title_standoff=45, row=2, col=1)
    fig.update_yaxes(title_standoff=45, row=2, col=2)
    fig.update_xaxes(title_standoff=15, row=1, col=1)
    fig.update_xaxes(title_standoff=15, row=1, col=2)
    fig.update_xaxes(title_standoff=15, row=2, col=1)
    fig.update_xaxes(title_standoff=15, row=2, col=2)
    return fig


def _chain_space_figures(df, sample_meta, feature_metadata, style, params, history=None):
    """Generate one chain-space figure per comparison. For more than two groups,
    use group_a as the reference and compare each other selected group to it."""
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    selected_groups = params.get("selected_groups") or [group_a, group_b]
    selected_groups = [g for g in selected_groups if g]
    # Deduplicate while preserving order
    seen = set()
    unique_groups = []
    for g in selected_groups:
        if g and g not in seen:
            seen.add(g)
            unique_groups.append(g)
    reference = group_a or (unique_groups[0] if unique_groups else "")
    if not reference:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Chain space (no reference group)")
        return json.loads(fig.to_json())
    targets = [g for g in unique_groups if g != reference]
    if not targets:
        # Only one group selected; build a single figure comparing it to itself will be empty,
        # so build an overview of that single group.
        targets = [reference]
    if len(unique_groups) <= 2 and group_b and group_b != reference:
        # Backward-compatible single comparison if two explicit groups are provided.
        targets = [group_b]
    figures = []
    for target in targets:
        pair_params = {**params, "group_a": reference, "group_b": target}
        fig = _chain_space_figure(df, sample_meta, feature_metadata, style, pair_params, history=history)
        figures.append(json.loads(fig.to_json()))
    if len(figures) == 1:
        return figures[0]
    return figures


def _pls_da_figure(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    n_components = int(params.get("n_components", 2))
    n_perm = int(params.get("n_perm", 100))
    result = pls_da_analysis(df, sample_meta, group_a, group_b, n_components=n_components, n_perm=n_perm, feature_metadata=feature_metadata)
    if result.get("error"):
        fig = go.Figure()
        _apply_base_layout(fig, style, title=f"PLS-DA: {result['error']}")
        return fig

    all_samples = df.columns.tolist()
    all_groups = [sample_meta.get(s, "Unknown") for s in all_samples]
    display_samples = [_shorten_name(s) for s in all_samples]
    color_map = _group_color_map(style, sorted(set(all_groups)))

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Score plot (LV1 vs LV2)", "Top VIP features", "Model performance", "Permutation test (R²Y)"),
        vertical_spacing=0.28,
        horizontal_spacing=0.14,
    )

    # Score plot: project all selected samples using the A/B fitted model
    pls = result.get("model")
    if pls:
        X_all = _prepare_X(df, all_samples)
        all_scores = np.array(pls.transform(X_all))
    else:
        all_scores = np.array(result["scores"])
    if all_scores.shape[1] >= 2:
        x = all_scores[:, 0]
        yv = all_scores[:, 1]
    else:
        x = all_scores[:, 0]
        yv = np.zeros(len(x))
    for gname in sorted(set(all_groups)):
        idx = [i for i, g in enumerate(all_groups) if g == gname]
        fig.add_trace(go.Scatter(
            x=x[idx], y=yv[idx], mode="markers", name=gname,
            marker=dict(color=color_map.get(gname, "#2e6575"), size=style.get("marker_size")),
            text=[display_samples[i] for i in idx],
            hovertemplate="%{text}<extra></extra>",
        ), row=1, col=1)
    fig.update_xaxes(title_text="LV1", row=1, col=1)
    fig.update_yaxes(title_text="LV2", row=1, col=1)

    # VIP
    vip = result["vip_table"][:8]
    vip_labels = [_shorten_name(v["feature"], 18) for v in vip]
    fig.add_trace(go.Bar(
        x=vip_labels, y=[v["vip"] for v in vip],
        marker_color=[color_map.get(group_b, "#c44e52") if v.get("loading_pc1", 0) > 0 else color_map.get(group_a, "#2e6575") for v in vip],
        customdata=[v["feature"] for v in vip],
        hovertemplate="%{customdata}<br>VIP: %{y:.2f}<extra></extra>",
        showlegend=False,
    ), row=1, col=2)
    fig.update_xaxes(tickangle=-60, row=1, col=2)
    fig.update_yaxes(title_text="VIP score", row=1, col=2)

    # Performance
    perf = result["performance"]
    fig.add_trace(go.Scatter(x=[p["n_components"] for p in perf], y=[p["r2y"] for p in perf], mode="lines+markers", name="R²Y", line=dict(color="#2e6575")), row=2, col=1)
    fig.add_trace(go.Scatter(x=[p["n_components"] for p in perf], y=[p["q2y"] for p in perf], mode="lines+markers", name="Q²Y", line=dict(color="#e9a47f")), row=2, col=1)
    fig.add_trace(go.Scatter(x=[p["n_components"] for p in perf], y=[p["accuracy"] for p in perf], mode="lines+markers", name="Accuracy", line=dict(color="#81b29a")), row=2, col=1)
    fig.update_xaxes(title_text="Components", row=2, col=1)
    fig.update_yaxes(title_text="Value", row=2, col=1)

    # Permutation histogram
    r2s = result["permutation"]["r2y"]
    actual = result["r2y"]
    fig.add_trace(go.Histogram(x=r2s, nbinsx=20, showlegend=False, marker_color="#cbd5e1"), row=2, col=2)
    fig.add_vline(x=actual, line_dash="dash", line_color="#c44e52", row=2, col=2)
    fig.update_xaxes(title_text="R²Y (permuted)", row=2, col=2)
    fig.update_yaxes(title_text="Count", row=2, col=2)

    title = f"PLS-DA: {group_b} vs {group_a} (R²Y={result['r2y']:.2f}, Q²Y={result['q2y']:.2f}, Acc={result['accuracy']:.2f})"
    x_labels = vip_labels + [f["feature"] for f in result.get("feature_importances", [])[:15]]
    _apply_base_layout(fig, style, title=None, x_labels=x_labels)
    fig.update_xaxes(tickmode="linear", dtick=1, tickangle=-45, tickfont=dict(size=9), row=1, col=2)
    fig.update_xaxes(tickangle=0, row=1, col=1)
    fig.update_xaxes(tickangle=0, row=2, col=1)
    fig.update_xaxes(tickangle=0, row=2, col=2)
    fig.update_layout(
        title={"text": title, "font": {"size": style.get("title_size"), "color": "#1e293b"}, "x": 0.5, "xanchor": "center"},
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 80, "r": 80, "t": 100, "b": 110},
    )
    return fig


def _opls_da_figure(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    n_orth = int(params.get("n_orth", 1))
    n_perm = int(params.get("n_perm", 100))
    result = opls_da_analysis(df, sample_meta, group_a, group_b, n_orth=n_orth, n_perm=n_perm, feature_metadata=feature_metadata)
    if result.get("error"):
        fig = go.Figure()
        _apply_base_layout(fig, style, title=f"OPLS-DA: {result['error']}")
        return fig

    all_samples = df.columns.tolist()
    all_groups = [sample_meta.get(s, "Unknown") for s in all_samples]
    display_samples = [_shorten_name(s) for s in all_samples]
    color_map = _group_color_map(style, sorted(set(all_groups)))

    # Project all selected samples using the A/B fitted OPLS model
    w_p = np.array(result.get("w_p", []))
    W_orth = [np.array(w) for w in (result.get("w_orth") or [])]
    P_orth = [np.array(p) for p in (result.get("p_orth") or [])]
    X_all = _prepare_X(df, all_samples)
    X_o = X_all.copy()
    pred_score = X_o @ w_p if w_p.size else np.zeros(len(all_samples))
    orth_scores_list = []
    for w_o, p_o in zip(W_orth, P_orth):
        t_o = X_o @ w_o
        orth_scores_list.append(t_o)
        X_o = X_o - np.outer(t_o, p_o)
    orth1 = orth_scores_list[0] if orth_scores_list else np.zeros(len(all_samples))
    orth_dist = np.sqrt(np.sum(np.stack([t ** 2 for t in orth_scores_list], axis=0), axis=0)) if orth_scores_list else np.zeros(len(all_samples))
    splot = result["splot"]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Score plot (predictive vs orthogonal)", "S-plot", "Top discriminant features", "Observation diagnostics"),
        vertical_spacing=0.28,
        horizontal_spacing=0.14,
    )

    # Score plot
    for gname in sorted(set(all_groups)):
        idx = [i for i, g in enumerate(all_groups) if g == gname]
        fig.add_trace(go.Scatter(
            x=pred_score[idx], y=orth1[idx], mode="markers", name=gname,
            marker=dict(color=color_map.get(gname, "#2e6575"), size=style.get("marker_size")),
            text=[display_samples[i] for i in idx],
            hovertemplate="%{text}<extra></extra>",
        ), row=1, col=1)
    fig.update_xaxes(title_text="Predictive score", row=1, col=1)
    fig.update_yaxes(title_text="Orthogonal score 1", row=1, col=1)

    # S-plot
    fig.add_trace(go.Scatter(
        x=[s["p_pred"] for s in splot], y=[s["p_corr"] for s in splot],
        mode="markers", marker=dict(color="#2e6575", size=style.get("marker_size")),
        text=[s["feature"] for s in splot], hovertemplate="%{text}<extra></extra>", showlegend=False,
    ), row=1, col=2)
    fig.update_xaxes(title_text="Predictive loading (p_pred)", row=1, col=2)
    fig.update_yaxes(title_text="Correlation to score", row=1, col=2)

    # VIP top features by |p_pred|
    top = sorted(splot, key=lambda s: abs(s["p_pred"]), reverse=True)[:8]
    top_labels = [_shorten_name(t["feature"], 18) for t in top]
    fig.add_trace(go.Bar(
        x=top_labels, y=[abs(t["p_pred"]) for t in top],
        marker_color=[color_map.get(group_b, "#c44e52") if t["p_pred"] > 0 else color_map.get(group_a, "#2e6575") for t in top],
        customdata=[t["feature"] for t in top],
        hovertemplate="%{customdata}<br>|p_pred|: %{y:.3f}<extra></extra>",
        showlegend=False,
    ), row=2, col=1)
    fig.update_xaxes(tickangle=-60, row=2, col=1)
    fig.update_yaxes(title_text="|p_pred|", row=2, col=1)

    # Diagnostics
    for gname in sorted(set(all_groups)):
        idx = [i for i, g in enumerate(all_groups) if g == gname]
        fig.add_trace(go.Scatter(
            x=pred_score[idx], y=orth_dist[idx], mode="markers", name=gname,
            marker=dict(color=color_map.get(gname, "#2e6575"), size=style.get("marker_size")),
            text=[display_samples[i] for i in idx],
            hovertemplate="%{text}<extra></extra>", showlegend=False,
        ), row=2, col=2)
    fig.update_xaxes(title_text="Predictive score", row=2, col=2)
    fig.update_yaxes(title_text="Orthogonal distance", row=2, col=2)

    title = f"OPLS-DA: {group_b} vs {group_a} (R²Y={result['r2y']:.2f}, Q²Y={result['q2y']:.2f}, Acc={result['accuracy']:.2f})"
    x_labels = top_labels + [t["feature"] for t in top]
    _apply_base_layout(fig, style, title=None, x_labels=x_labels)
    fig.update_xaxes(tickmode="linear", dtick=1, tickangle=-45, tickfont=dict(size=9), row=2, col=1)
    fig.update_xaxes(tickangle=0, row=1, col=1)
    fig.update_xaxes(tickangle=0, row=1, col=2)
    fig.update_xaxes(tickangle=0, row=2, col=2)
    fig.update_layout(
        title={"text": title, "font": {"size": style.get("title_size"), "color": "#1e293b"}, "x": 0.5, "xanchor": "center"},
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 80, "r": 80, "t": 100, "b": 110},
    )
    return fig


def _biomarker_figure(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    result = biomarker_analysis(df, sample_meta, group_a, group_b, feature_metadata=feature_metadata)
    if result.get("error"):
        fig = go.Figure()
        _apply_base_layout(fig, style, title=f"Biomarkers: {result['error']}")
        return fig

    top = result["top_candidates"][:8]
    mv = result["multivariate"]
    color_map = _group_color_map(style, [group_a, group_b])

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Top candidate AUC", "Random Forest ROC", "Top RF importances", "Top candidate table"),
        vertical_spacing=0.28,
        horizontal_spacing=0.14,
        specs=[[{"type": "xy"}, {"type": "xy"}], [{"type": "xy"}, {"type": "table"}]],
    )

    # AUC bar
    auc_labels = [_shorten_name(t["feature"], 18) for t in top]
    fig.add_trace(go.Bar(
        x=auc_labels, y=[t["auc"] for t in top],
        marker_color=[color_map.get(group_b, "#c44e52") if t["log2fc"] > 0 else color_map.get(group_a, "#2e6575") for t in top],
        customdata=[t["feature"] for t in top],
        hovertemplate="%{customdata}<br>AUC: %{y:.3f}<extra></extra>",
        showlegend=False,
    ), row=1, col=1)
    fig.update_xaxes(tickangle=-60, row=1, col=1)
    fig.update_yaxes(title_text="AUC", row=1, col=1)

    # ROC
    if mv["fpr"] and mv["tpr"]:
        fig.add_trace(go.Scatter(
            x=mv["fpr"], y=mv["tpr"], mode="lines",
            name=f"RF AUC={mv['auc']:.2f}, Acc={mv['accuracy']:.2f}",
            line=dict(color="#2e6575"),
            fill="tozeroy", fillcolor="rgba(46,101,117,0.1)",
        ), row=1, col=2)
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dash", color="#cbd5e1"), showlegend=False), row=1, col=2)
    fig.update_xaxes(title_text="False positive rate", row=1, col=2)
    fig.update_yaxes(title_text="True positive rate", row=1, col=2)

    # RF importance
    fi = result["feature_importances"][:8]
    fi_labels = [_shorten_name(f["feature"], 18) for f in fi]
    fig.add_trace(go.Bar(
        x=fi_labels, y=[f["importance"] for f in fi],
        marker_color="#81b29a", showlegend=False,
        customdata=[f["feature"] for f in fi],
        hovertemplate="%{customdata}<br>Importance: %{y:.3f}<extra></extra>",
    ), row=2, col=1)
    fig.update_xaxes(tickangle=-60, row=2, col=1)
    fig.update_yaxes(title_text="Importance", row=2, col=1)

    # Table
    table = [
        [t["feature"] for t in top],
        [f"{t['auc']:.2f}" for t in top],
        [f"{t['pvalue']:.2e}" for t in top],
        [f"{t['padj']:.2e}" for t in top],
        [f"{t['cohens_d']:.2f}" for t in top],
        [f"{t['power']:.2f}" for t in top],
    ]
    fig.add_trace(go.Table(
        header=dict(values=["Feature", "AUC", "p-value", "adj p", "Cohen's d", "Power"], fill_color="#e2e8f0", align="left", font=dict(color="#1e293b", size=10)),
        cells=dict(values=table, align="left", font=dict(size=9), height=20),
    ), row=2, col=2)

    title = f"Biomarker discovery: {group_b} vs {group_a} (RF AUC={mv['auc']:.2f})"
    x_labels = auc_labels + fi_labels
    _apply_base_layout(fig, style, title=None, x_labels=x_labels)
    fig.update_xaxes(tickmode="linear", dtick=1, tickangle=-45, tickfont=dict(size=9), row=1, col=1)
    fig.update_xaxes(tickmode="linear", dtick=1, tickangle=-45, tickfont=dict(size=9), row=2, col=1)
    fig.update_xaxes(tickangle=0, row=1, col=2)
    fig.update_layout(
        title={"text": title, "font": {"size": style.get("title_size"), "color": "#1e293b"}, "x": 0.5, "xanchor": "center"},
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 80, "r": 80, "t": 100, "b": 110},
    )
    return fig


def _permanova_figure(df, sample_meta, feature_metadata, style, params):
    group_a = params.get("group_a", "")
    group_b = params.get("group_b", "")
    metric = params.get("metric", "braycurtis")
    result = permanova_analysis(df, sample_meta, group_a, group_b, metric=metric, n_perm=999)
    if result.get("error"):
        fig = go.Figure()
        _apply_base_layout(fig, style, title=f"PERMANOVA: {result['error']}")
        return fig

    display_samples = [_shorten_name(s) for s in result["samples"]]
    color_map = _group_color_map(style, [group_a, group_b])

    # Classical MDS / PCoA on Gower-centered distance matrix
    from sklearn.metrics import pairwise_distances
    X = df[result["samples"]].T.values.copy()
    for col in range(X.shape[1]):
        vals = X[:, col]
        pos = vals[np.isfinite(vals) & (vals > 0)]
        fill = float(np.min(pos) / 2) if len(pos) else 1e-6
        vals[~np.isfinite(vals)] = fill
        vals[vals <= 0] = fill
    X = np.log10(X)
    X = StandardScaler().fit_transform(X)
    D = pairwise_distances(X, metric=metric if metric in ("euclidean", "manhattan", "cosine", "braycurtis") else "euclidean")
    n = D.shape[0]
    D2 = D ** 2
    row_mean = D2.mean(axis=1, keepdims=True)
    col_mean = D2.mean(axis=0, keepdims=True)
    grand_mean = D2.mean()
    G = -0.5 * (D2 - row_mean - col_mean + grand_mean)
    try:
        eigvals, eigvecs = np.linalg.eigh(G)
        idx = np.argsort(eigvals)[::-1]
        coords = eigvecs[:, idx] * np.sqrt(np.maximum(eigvals[idx], 0))
    except Exception:
        coords = np.zeros((n, 2))

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("PERMANOVA permutation distribution", f"PCoA ({metric})"),
        horizontal_spacing=0.15,
    )

    perm_f = result["perm_f"]
    actual = result["pseudo_f"]
    fig.add_trace(go.Histogram(x=perm_f, nbinsx=30, showlegend=False, marker_color="#cbd5e1"), row=1, col=1)
    fig.add_vline(x=actual, line_dash="dash", line_color="#c44e52", row=1, col=1)
    fig.update_xaxes(title_text=f"Pseudo-F (p={result['p_value']:.3f})", row=1, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1)

    groups = result["groups"]
    for gname in sorted(set(groups)):
        idx = [i for i, g in enumerate(groups) if g == gname]
        fig.add_trace(go.Scatter(
            x=coords[idx, 0], y=coords[idx, 1], mode="markers", name=gname,
            marker=dict(color=color_map.get(gname, "#2e6575"), size=style.get("marker_size")),
            text=[display_samples[i] for i in idx],
            hovertemplate="%{text}<extra></extra>",
        ), row=1, col=2)
    fig.update_xaxes(title_text="PCoA 1", row=1, col=2)
    fig.update_yaxes(title_text="PCoA 2", row=1, col=2)

    title = f"PERMANOVA: {group_b} vs {group_a} (pseudo-F={actual:.2f}, p={result['p_value']:.3f}, R²={result['r2']:.2f})"
    _apply_base_layout(fig, style, title=None, y_labels=display_samples)
    left_margin = max(getattr(fig.layout.margin, "l", 80), 80)
    bottom_margin = max(getattr(fig.layout.margin, "b", 110), 110)
    fig.update_layout(
        title={"text": title, "font": {"size": style.get("title_size"), "color": "#1e293b"}, "x": 0.5, "xanchor": "center"},
        legend={"orientation": "h", "y": -0.2},
        margin={"l": left_margin, "r": 80, "t": 100, "b": bottom_margin},
    )
    return fig


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


def _heatmap_publication(df, sample_meta, feature_metadata, style, params):
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

    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
    present_groups = sorted(set(sample_groups.values()))
    group_order = params.get("group_order") or present_groups
    if isinstance(group_order, str):
        group_order = [g.strip() for g in group_order.split(",") if g.strip()]
    group_order = [g for g in group_order if g in present_groups]
    group_order += [g for g in present_groups if g not in group_order]
    if "Unknown" in group_order:
        group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
    gcolor_map = _group_color_map(style, group_order)

    # Order columns by group_order and optionally cluster within each group
    group_to_cols = {}
    for c in plot_df.columns:
        g = sample_groups.get(c, "Unknown")
        group_to_cols.setdefault(g, []).append(c)
    ordered_cols = []
    col_link = None
    for g in group_order:
        cols = group_to_cols.get(g, [])
        if cluster_cols and len(cols) > 2:
            try:
                sub_df = plot_df[cols]
                dist = pdist(sub_df.T.values, metric=metric)
                link = linkage(dist, method=method)
                order = leaves_list(link)
                cols = [cols[i] for i in order]
            except Exception:
                pass
        ordered_cols.extend(cols)
    if ordered_cols:
        plot_df = plot_df[ordered_cols]

    row_link = None
    if cluster_rows and len(plot_df) > 2:
        try:
            row_link = linkage(pdist(plot_df.values, metric=metric), method=method)
            row_order = leaves_list(row_link)
            plot_df = plot_df.iloc[row_order]
        except Exception:
            pass

    group_codes = [group_order.index(sample_groups.get(c, "Unknown")) for c in plot_df.columns]
    n_groups = max(len(group_order), 1)
    if n_groups == 1:
        group_colorscale = [[0, gcolor_map[group_order[0]]], [1, gcolor_map[group_order[0]]]]
    else:
        group_colorscale = [[i / (n_groups - 1), gcolor_map[g]] for i, g in enumerate(group_order)]

    m, n = plot_df.shape
    is_lipidone = params.get("heatmap_style") == "lipidone"
    min_height = 800 if is_lipidone else 600
    height = max(min_height, min(2400, m * 16 + 260))
    feature_ids = [feature_metadata[i].get("feature_id", i) if i < len(feature_metadata) else i for i in plot_df.index]
    # Keep the top dendrogram and group color bar at fixed pixel heights so they do not
    # become oversized when the overall figure grows for larger top-N values.
    vertical_spacing = 0.01
    available = 1 - 2 * vertical_spacing
    top_frac = 80 / height
    group_frac = 50 / height
    heatmap_frac = max(0.5, available - top_frac - group_frac)
    row_heights = [top_frac, group_frac, heatmap_frac]
    fig = make_subplots(
        rows=3, cols=2,
        specs=[[None, {}], [None, {}], [{}, {}]],
        shared_xaxes=False,
        shared_yaxes=False,
        column_widths=[0.12, 0.88],
        row_heights=row_heights,
        vertical_spacing=vertical_spacing,
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
        showlegend=False,
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
        showlegend=False,
        colorbar=dict(
            title={"text": cbar_title, "side": "right", "font": {"size": 11}},
            xref="container",
            x=1.0,
            xanchor="right",
            xpad=10,
            len=0.65,
            thickness=12,
            outlinewidth=0,
            tickfont={"size": 9},
        ),
        hovertemplate="Feature: %{customdata[0]}<br>Sample: %{customdata[1]}<br>Value: %{z:.3f}<extra></extra>",
        customdata=np.array([[[_shorten_name(_clean_lipid_name(str(feature_ids[i])), 60), _shorten_name(c, 60)] for c in plot_df.columns] for i in range(m)]),
    ), row=3, col=2)

    max_top = max(np.nanmax(np.abs(y_dend)) if (col_link is not None and y_dend) else 1.0, 1.0)
    max_left = max(np.nanmax(np.abs(x_dend)) if (row_link is not None and x_dend) else 1.0, 1.0)

    fig.update_xaxes(range=[-0.5, n - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=1, col=2)
    fig.update_yaxes(range=[0, max_top], showticklabels=False, showgrid=False, zeroline=False, row=1, col=2)

    fig.update_xaxes(range=[-0.5, n - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=2, col=2)
    fig.update_yaxes(range=[-0.5, 0.5], showticklabels=False, showgrid=False, zeroline=False, row=2, col=2)

    fig.update_xaxes(autorange="reversed", range=[0, max_left], showticklabels=False, showgrid=False, zeroline=False, row=3, col=1)
    fig.update_yaxes(range=[-0.5, m - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=3, col=1)

    short_cols = [_shorten_name(c) for c in plot_df.columns]
    short_rows = [_shorten_name(_clean_lipid_name(str(fid))) for fid in feature_ids]
    max_x_len = max([len(s) for s in short_cols], default=1)
    max_y_len = max([len(s) for s in short_rows], default=1)

    # Decide x-axis label density/rotation from sample name length and count.
    long_x_labels = max_x_len > 12
    x_step = _tick_text_step(n, max_labels=18 if long_x_labels else 25)
    x_tickvals = list(range(0, n, x_step))
    x_ticktext = [short_cols[i] for i in x_tickvals]
    x_tick_size = max(8, min(10 if long_x_labels else 13, int(300 / max(n, 1))))
    y_tick_size = max(7, min(11, int(height * 0.5 / max(m, 1))))
    if is_lipidone or max_x_len > 16 or (long_x_labels and n > 8):
        x_tickangle = -90
    elif long_x_labels or n > 15:
        x_tickangle = -45
    elif n > 25:
        x_tickangle = -60
    else:
        x_tickangle = 0
    # For vertical sample labels, cap the label length so the bottom margin
    # stays reasonable and the footer has room below the names.
    if is_lipidone or x_tickangle == -90:
        x_tick_size = max(8, min(10, int(300 / max(n, 1))))
        max_allowed_x_len = max(8, int((height * 0.45 - 150) / max(x_tick_size, 1)))
        if max_x_len > max_allowed_x_len:
            short_cols = [_shorten_name(c, max_allowed_x_len) for c in plot_df.columns]
            max_x_len = max_allowed_x_len
        long_x_labels = max_x_len > 12
        x_step = _tick_text_step(n, max_labels=18 if long_x_labels else 25)
        x_tickvals = list(range(0, n, x_step))
        x_ticktext = [short_cols[i] for i in x_tickvals]
    # Allow one label per row as long as there is ~14 px of vertical space per label.
    y_step = _tick_text_step(m, max_labels=max(1, int(height / 14)))

    max_group_len = max([len(str(g)) for g in group_order], default=0)
    group_legend_width = max_group_len * 8 + 55
    right_margin = max(260, int(max_y_len * y_tick_size * 0.75) + 150 + group_legend_width)
    if is_lipidone:
        x_label_extra = max_x_len * x_tick_size + 60
        bottom_margin = max(180, x_label_extra + 90)
        footer_y = - (bottom_margin - 40) / height
    else:
        projection = abs(np.sin(np.radians(x_tickangle))) if x_tickangle != 0 else 0
        x_label_extra = int(max_x_len * x_tick_size * projection) + 60 if x_tickangle != 0 else x_tick_size + 30
        bottom_margin = max(120, x_label_extra + 70)
        footer_y = None

    _apply_base_layout(fig, style, title=f"Top {m} most-variable features", x_labels=short_cols, y_labels=short_rows)

    for g in group_order:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=gcolor_map[g]),
            name=str(g), showlegend=True, hoverinfo="skip", visible="legendonly",
        ), row=3, col=2)

    fig.update_xaxes(
        range=[-0.5, n - 0.5],
        tickmode="array",
        tickvals=x_tickvals,
        ticktext=x_ticktext,
        tickangle=x_tickangle,
        side="bottom",
        tickfont=dict(size=x_tick_size),
        automargin=True,
        showgrid=False,
        zeroline=False,
        row=3, col=2,
    )
    fig.update_yaxes(
        range=[-0.5, m - 0.5],
        tickmode="array",
        tickvals=list(range(0, m, y_step)),
        ticktext=short_rows[::y_step],
        tickfont=dict(size=y_tick_size),
        side="right",
        automargin=True,
        showgrid=False,
        zeroline=False,
        row=3, col=2,
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(
            xref="container",
            yref="paper",
            x=1.0,
            y=0.98,
            xanchor="right",
            yanchor="top",
            orientation="v",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e2e8f0",
            borderwidth=1,
            font=dict(size=10),
        ),
        margin=dict(l=80, r=right_margin, t=100, b=bottom_margin),
        height=height,
        paper_bgcolor=style.get("paper_bgcolor"),
        plot_bgcolor="white",
        font=dict(family=style.get("font_family"), color="#334155"),
    )

    if is_lipidone:
        for trace in fig.data:
            if trace.type == "heatmap" and hasattr(trace, "z") and len(trace.z) > 1:
                trace.colorscale = "RdYlBu_r"
                trace.zmid = 0
                if trace.colorbar:
                    trace.colorbar.title = "z-score"
        fig.update_layout(
            title=dict(text=""),
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        # Group label above the group color bar
        fig.add_annotation(
            x=-0.5, y=1.12,
            xref="paper", yref="paper",
            text="Group",
            showarrow=False,
            font=dict(size=11, color="#334155"),
            xanchor="right", yanchor="bottom",
        )
        # Footer summary
        footer = f"Top features: {m}, Ranking: p-value (t-test/ANOVA), Distance: {metric}"
        fig.add_annotation(
            x=0.5, y=footer_y,
            xref="paper", yref="paper",
            text=footer,
            showarrow=False,
            font=dict(size=10, color="#334155"),
            xanchor="center", yanchor="top",
        )

    return fig


def _mpl_figure_to_plotly(fig: plt.Figure, title: str | None = None) -> go.Figure:
    """Save a matplotlib figure to PNG and wrap it in a Plotly image figure."""
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.25)
        buf.seek(0)
        img = Image.open(buf)
        width, height = img.size
        buf.seek(0)
        png_b64 = base64.b64encode(buf.read()).decode("ascii")
    finally:
        plt.close(fig)
    layout = {
        "autosize": True,
        "height": height,
        "images": [{
            "source": f"data:image/png;base64,{png_b64}",
            "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5,
            "sizex": 1, "sizey": 1,
            "xanchor": "center", "yanchor": "middle",
            "sizing": "contain",
            "layer": "below",
        }],
        "xaxis": {"visible": False, "range": [0, 1], "fixedrange": True},
        "yaxis": {"visible": False, "range": [0, 1], "fixedrange": True},
        "margin": {"l": 0, "r": 0, "t": 40 if title else 0, "b": 0},
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
    }
    if title:
        layout["title"] = {"text": title, "x": 0.5, "xanchor": "center", "font": {"size": 14, "color": "#1e293b"}}
    return go.Figure(data=[go.Scatter(x=[0, 1], y=[0, 1], mode="markers", marker={"opacity": 0}, showlegend=False, hoverinfo="skip")], layout=layout)


def _heatmap_seaborn(df, sample_meta, feature_metadata, style, params):
    """Render a clustered heatmap with seaborn and return as a Plotly image figure."""
    top_n = int(params.get("top_n", 50))
    metric = params.get("metric", "euclidean")
    method = params.get("method", "average")
    scale = params.get("scale", "row_zscore")
    cluster_rows = bool(params.get("cluster_rows", True))
    cluster_cols = bool(params.get("cluster_cols", True))
    linkage_color = params.get("linkage_color", "#2ca02c")
    cmap = style.get("heatmap_colorscale", "RdBu_r")

    plot_df = df.copy()
    if scale == "log10":
        plot_df = np.log10(plot_df.replace(0, np.nan)).fillna(0)
    row_std = plot_df.std(axis=1, numeric_only=True)
    top_idx = row_std.nlargest(min(top_n, len(plot_df))).index
    plot_df = plot_df.loc[top_idx]

    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
    present_groups = sorted(set(sample_groups.values()))
    group_order = params.get("group_order") or present_groups
    if isinstance(group_order, str):
        group_order = [g.strip() for g in group_order.split(",") if g.strip()]
    group_order = [g for g in group_order if g in present_groups]
    group_order += [g for g in present_groups if g not in group_order]
    if "Unknown" in group_order:
        group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
    gcolor_map = _group_color_map(style, group_order)

    # order columns by group order
    ordered_cols = [c for g in group_order for c in plot_df.columns if sample_groups[c] == g]
    ordered_cols += [c for c in plot_df.columns if c not in ordered_cols]
    plot_df = plot_df[ordered_cols]
    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}

    # rename labels
    plot_df.index = [_shorten_name(_clean_lipid_name(feature_metadata[idx].get("feature_id", idx) if isinstance(idx, int) and idx < len(feature_metadata) else idx), 35) for idx in plot_df.index]
    plot_df.columns = [_shorten_name(c, 30) for c in plot_df.columns]

    m, n = plot_df.shape
    mask = plot_df.isna()

    # pre-compute linkages on imputed data so NaNs do not break clustermap
    plot_df_imp = plot_df.fillna(0)
    row_link = None
    col_link = None
    try:
        if cluster_rows and m > 2:
            row_link = linkage(pdist(plot_df_imp, metric=metric), method=method)
        if cluster_cols and n > 2:
            col_link = linkage(pdist(plot_df_imp.T, metric=metric), method=method)
    except Exception:
        pass

    # group color bar as a pandas Series so it stays aligned after clustering
    col_color_series = pd.Series(
        [gcolor_map.get(sample_groups.get(c, "Unknown"), "#94a3b8") for c in plot_df.columns],
        index=plot_df.columns,
    )

    # seaborn clustermap settings
    z_score = 0 if scale == "row_zscore" else None
    center = 0 if scale == "row_zscore" else None
    standard_scale = None

    fig_width = max(8, min(40, n * 0.35 + 2))
    fig_height = max(6, min(40, m * 0.25 + 3))
    y_font = max(5, min(10, int(fig_height * 36 / max(m, 1))))
    x_font = max(5, min(10, int(fig_width * 36 / max(n, 1))))

    tree_kws = {"colors": linkage_color, "linewidths": 1.0}
    try:
        cg = sns.clustermap(
            plot_df,
            method=method,
            metric=metric,
            row_cluster=cluster_rows and m > 2 and row_link is not None,
            col_cluster=cluster_cols and n > 2 and col_link is not None,
            row_linkage=row_link,
            col_linkage=col_link,
            z_score=z_score,
            standard_scale=standard_scale,
            center=center,
            cmap=cmap,
            col_colors=col_color_series,
            mask=mask,
            figsize=(fig_width, fig_height),
            dendrogram_ratio=0.15,
            cbar_pos=(0.02, 0.78, 0.03, 0.15),
            xticklabels=True,
            yticklabels=True,
            tree_kws=tree_kws,
        )
        if cg.ax_heatmap.get_xticklabels():
            cg.ax_heatmap.set_xticklabels(cg.ax_heatmap.get_xticklabels(), rotation=90, ha="center", fontsize=x_font)
        if cg.ax_heatmap.get_yticklabels():
            cg.ax_heatmap.set_yticklabels(cg.ax_heatmap.get_yticklabels(), fontsize=y_font)
        title = params.get("title") or f"Top {m} most-variable features"
        cg.fig.suptitle(title, fontsize=12, color="#1e293b", y=0.99)
        # group color legend below the heatmap
        try:
            legend_handles = [mpatches.Patch(color=gcolor_map.get(g, "#94a3b8"), label=g) for g in group_order]
            ncol = min(4, max(1, len(legend_handles)))
            cg.ax_heatmap.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.22), title="Group", fontsize=7, frameon=True, ncol=ncol)
        except Exception:
            pass
        return _mpl_figure_to_plotly(cg.fig, title=None)
    except Exception:
        # fallback: simple seaborn heatmap with a manual group color bar
        if row_link is not None:
            row_order = leaves_list(row_link).tolist()
        else:
            row_order = list(range(m))
        if col_link is not None:
            col_order = leaves_list(col_link).tolist()
        else:
            col_order = list(range(n))
        plot_df = plot_df.iloc[row_order, col_order]
        mask = mask.iloc[row_order, col_order]
        fig = plt.figure(figsize=(fig_width, fig_height))
        gs = fig.add_gridspec(2, 1, height_ratios=[0.06, 1], hspace=0.05)
        ax_group = fig.add_subplot(gs[0, 0])
        ax_heatmap = fig.add_subplot(gs[1, 0])
        group_codes = {g: i for i, g in enumerate(group_order)}
        group_cmap = ListedColormap([gcolor_map.get(g, "#94a3b8") for g in group_order])
        group_color_matrix = np.array([[group_codes.get(sample_groups.get(c, "Unknown"), 0) for c in plot_df.columns]])
        ax_group.imshow(group_color_matrix, aspect="auto", cmap=group_cmap, interpolation="nearest")
        ax_group.set_xticks([])
        ax_group.set_yticks([])
        ax_group.set_frame_on(False)
        sns.heatmap(plot_df, cmap=cmap, center=center, ax=ax_heatmap, mask=mask, cbar=True, xticklabels=True, yticklabels=True)
        ax_heatmap.set_xticklabels(ax_heatmap.get_xticklabels(), rotation=90, ha="center", fontsize=x_font)
        ax_heatmap.set_yticklabels(ax_heatmap.get_yticklabels(), fontsize=y_font)
        legend_handles = [mpatches.Patch(color=gcolor_map.get(g, "#94a3b8"), label=g) for g in group_order]
        ncol = min(4, max(1, len(legend_handles)))
        ax_heatmap.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.18), title="Group", fontsize=7, frameon=True, ncol=ncol)
        title = params.get("title") or f"Top {m} most-variable features"
        fig.suptitle(title, fontsize=12, color="#1e293b", y=0.99)
        return _mpl_figure_to_plotly(fig, params.get("title"))


def _heatmap_matplotlib(df, sample_meta, feature_metadata, style, params):
    """Render a clustered heatmap with matplotlib and return as a Plotly image figure."""
    top_n = int(params.get("top_n", 50))
    metric = params.get("metric", "euclidean")
    method = params.get("method", "average")
    scale = params.get("scale", "row_zscore")
    cluster_rows = bool(params.get("cluster_rows", True))
    cluster_cols = bool(params.get("cluster_cols", True))
    linkage_color = params.get("linkage_color", "#2ca02c")
    cmap = style.get("heatmap_colorscale", "RdBu_r")

    plot_df = df.copy()
    if scale == "log10":
        plot_df = np.log10(plot_df.replace(0, np.nan)).fillna(0)
    row_std = plot_df.std(axis=1, numeric_only=True)
    top_idx = row_std.nlargest(min(top_n, len(plot_df))).index
    plot_df = plot_df.loc[top_idx]

    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
    present_groups = sorted(set(sample_groups.values()))
    group_order = params.get("group_order") or present_groups
    if isinstance(group_order, str):
        group_order = [g.strip() for g in group_order.split(",") if g.strip()]
    group_order = [g for g in group_order if g in present_groups]
    group_order += [g for g in present_groups if g not in group_order]
    if "Unknown" in group_order:
        group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
    gcolor_map = _group_color_map(style, group_order)

    ordered_cols = [c for g in group_order for c in plot_df.columns if sample_groups[c] == g]
    ordered_cols += [c for c in plot_df.columns if c not in ordered_cols]
    plot_df = plot_df[ordered_cols]
    sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
    group_codes = {g: i for i, g in enumerate(group_order)}
    group_color_matrix = np.array([[group_codes.get(sample_groups[c], 0) for c in plot_df.columns]])
    group_cmap = ListedColormap([gcolor_map.get(g, "#94a3b8") for g in group_order])

    # scaling
    if scale == "row_zscore":
        z = (plot_df.sub(plot_df.mean(axis=1), axis=0).div(plot_df.std(axis=1).replace(0, np.nan), axis=0)).fillna(0).values
        vmin, vmax = -max(1.0, np.nanmax(np.abs(z))), max(1.0, np.nanmax(np.abs(z)))
    else:
        z = plot_df.values
        vmin, vmax = np.nanmin(z), np.nanmax(z)

    m, n = z.shape
    row_order = list(range(m))
    col_order = list(range(n))
    row_link = None
    col_link = None
    try:
        if cluster_rows and m > 2:
            row_link = linkage(pdist(z, metric=metric), method=method)
            row_order = leaves_list(row_link).tolist()
        if cluster_cols and n > 2:
            col_link = linkage(pdist(z.T, metric=metric), method=method)
            col_order = leaves_list(col_link).tolist()
    except Exception:
        pass
    z = z[row_order][:, col_order]
    y_labels = [_shorten_name(_clean_lipid_name(feature_metadata[idx].get("feature_id", idx) if isinstance(idx, int) and idx < len(feature_metadata) else idx), 40) for idx in plot_df.index[row_order]]
    x_labels = [_shorten_name(plot_df.columns[i], 35) for i in col_order]
    max_y_len = max([len(s) for s in y_labels], default=1)

    fig_width = max(10, min(40, n * 0.45 + 4))
    fig_height = max(6, min(40, m * 0.25 + 3))
    y_font = max(5, min(10, int(fig_height * 36 / max(m, 1))))
    x_font = max(5, min(10, int(fig_width * 36 / max(n, 1))))

    # Reserve a left gutter wide enough for the row labels so they never overlap the dendrogram.
    label_width_inches = max_y_len * y_font * 0.85 / 72 + 0.25
    desired_gutter = label_width_inches * 1.5
    row_dendro_ratio = 0.8 if cluster_rows else 0.001
    heatmap_ratio = 6
    cbar_ratio = 0.6
    legend_ratio = 1.2
    other_width = row_dendro_ratio + heatmap_ratio + cbar_ratio + legend_ratio
    gutter_ratio = max(0.001, desired_gutter * other_width / max(0.1, fig_width - desired_gutter))
    col_dendro_ratio = 0.6 if cluster_cols else 0.001

    fig = plt.figure(figsize=(fig_width, fig_height))
    gs = fig.add_gridspec(
        3, 5,
        width_ratios=[row_dendro_ratio, gutter_ratio, heatmap_ratio, cbar_ratio, legend_ratio],
        height_ratios=[col_dendro_ratio, 0.25, 6],
        wspace=0.12,
        hspace=0.12,
    )

    ax_col = fig.add_subplot(gs[0, 2])
    ax_group = fig.add_subplot(gs[1, 2])
    ax_row = fig.add_subplot(gs[2, 0])
    ax_heatmap = fig.add_subplot(gs[2, 2])
    ax_cbar = fig.add_subplot(gs[2, 3])
    ax_legend = fig.add_subplot(gs[2, 4])

    try:
        if cluster_cols and n > 2 and col_link is not None:
            scipy_dendrogram(col_link, orientation="top", no_labels=True, show_leaf_counts=False, ax=ax_col, color_threshold=0, above_threshold_color=linkage_color)
        if cluster_rows and m > 2 and row_link is not None:
            scipy_dendrogram(row_link, orientation="left", no_labels=True, show_leaf_counts=False, ax=ax_row, color_threshold=0, above_threshold_color=linkage_color)
    except Exception:
        pass
    ax_col.axis("off")
    ax_row.axis("off")
    for txt in getattr(ax_col, "texts", []):
        txt.set_visible(False)
    for txt in getattr(ax_row, "texts", []):
        txt.set_visible(False)

    ax_group.imshow(group_color_matrix[:, col_order], aspect="auto", cmap=group_cmap, interpolation="nearest")
    ax_group.set_xticks([])
    ax_group.set_yticks([0])
    ax_group.set_yticklabels(["Group"], fontsize=8)
    ax_group.set_frame_on(False)

    im = ax_heatmap.imshow(z, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax_heatmap.set_xticks(range(n))
    ax_heatmap.set_xticklabels(x_labels, rotation=90, ha="center", fontsize=x_font)
    ax_heatmap.set_yticks(range(m))
    ax_heatmap.set_yticklabels(y_labels, fontsize=y_font)
    # Keep row labels on the left but close to the heatmap so they sit in the gutter, not the dendrogram.
    ax_heatmap.yaxis.tick_left()
    ax_heatmap.tick_params(axis="y", labelleft=True, labelright=False, pad=3)
    ax_heatmap.set_xlabel("")
    ax_heatmap.set_ylabel("")

    fig.colorbar(im, cax=ax_cbar)
    ax_cbar.tick_params(labelsize=8)

    # group color legend in its own axes
    try:
        legend_handles = [mpatches.Patch(color=gcolor_map.get(g, "#94a3b8"), label=g) for g in group_order]
        ax_legend.legend(handles=legend_handles, loc="upper left", title="Group", fontsize=8, frameon=True)
    except Exception:
        pass
    ax_legend.axis("off")

    title = params.get("title") or f"Top {m} most-variable features"
    fig.suptitle(title, fontsize=12, color="#1e293b", y=0.99)
    return _mpl_figure_to_plotly(fig, title=None)


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
    feature_metadata = dataset.feature_metadata or []

    # When isobaric resolution is set to report combined / keep one representative,
    # drop the non-representative component rows from plots so combined species are shown once.
    if feature_metadata:
        keep_rows = [not bool(m.get("isobaric_substitution_rollup_exclude")) for m in feature_metadata]
        if not all(keep_rows):
            df = df[keep_rows].reset_index(drop=True)
            feature_metadata = [m for m, ok in zip(feature_metadata, keep_rows) if ok]

    plot_type = req.plot_type
    params = req.parameters or {}
    style = _merge_style(req.style)

    excluded_groups = set(params.get("excluded_groups") or [])
    if excluded_groups:
        keep_cols = [c for c in df.columns if sample_meta.get(c) not in excluded_groups]
        df = df[keep_cols]
        sample_meta = {c: g for c, g in sample_meta.items() if c in keep_cols}
    if df.shape[1] == 0:
        fig = go.Figure()
        fig.update_layout(title="No samples remain after excluding groups")
        _apply_base_layout(fig, style)
        return json.loads(fig.to_json())

    if plot_type in ("bar", "box", "violin", "dot"):
        feature = _get_feature_index(feature_metadata, params.get("feature"))
        title = f"{feature_metadata[feature].get('feature_id', feature)}"
        ordered_df = _reorder_columns(df, sample_meta, params.get("group_order", []))
        ordered_samples = ordered_df.columns.tolist()
        display_samples = [_shorten_name(s) for s in ordered_samples]
        ordered_values = _intensity_from_transformed(ordered_df.iloc[feature].values, dataset.processing_history)
        ordered_groups = [sample_meta.get(c, "unknown") for c in ordered_samples]
        color_map = _group_color_map(style, ordered_groups)

        if plot_type == "bar":
            fig = go.Figure()
            for g in sorted(set(ordered_groups)):
                idx = [i for i, gg in enumerate(ordered_groups) if gg == g]
                vals = [float(ordered_values[i]) for i in idx]
                samps = [display_samples[i] for i in idx]
                fig.add_trace(go.Bar(x=samps, y=vals, name=g, marker_color=color_map[g]))
            fig.update_layout(barmode="group", xaxis_title="Sample", yaxis_title="Intensity")
        elif plot_type == "box":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g in sorted(group_vals):
                fig.add_trace(go.Box(y=group_vals[g], name=g, boxpoints="all", marker_color=color_map[g]))
            fig.update_layout(xaxis_title="Group", yaxis_title="Intensity")
        elif plot_type == "violin":
            fig = go.Figure()
            group_vals = {}
            for s, g in zip(ordered_samples, ordered_groups):
                group_vals.setdefault(g, []).append(_safe_float(ordered_values[ordered_samples.index(s)]))
            for g in sorted(group_vals):
                fig.add_trace(go.Violin(y=group_vals[g], name=g, box_visible=True, meanline_visible=True, line_color=color_map[g]))
            fig.update_layout(yaxis_title="Intensity")
        else:  # dot
            fig = go.Figure()
            for g in sorted(set(ordered_groups)):
                idx = [i for i, gg in enumerate(ordered_groups) if gg == g]
                vals = [float(ordered_values[i]) for i in idx]
                samps = [display_samples[i] for i in idx]
                fig.add_trace(go.Scatter(x=samps, y=vals, mode="markers", name=g, marker_color=color_map[g], marker_size=style.get("marker_size")))
            fig.update_layout(xaxis_title="Sample", yaxis_title="Intensity")

        # Choose the x-axis label set used by the actual traces.
        if plot_type in ("box", "violin"):
            x_labels_for_layout = sorted(set(ordered_groups))
        else:
            x_labels_for_layout = display_samples
        _apply_base_layout(fig, style, title=f"{plot_type.title()} Plot: {title}", x_labels=x_labels_for_layout)

        n_x = len(x_labels_for_layout)
        longest_x = max([len(str(l)) for l in x_labels_for_layout], default=0)
        if longest_x > 18 or n_x > 15:
            tick_font = max(6, style.get("tick_size", 11) - 2)
        elif n_x > 25:
            tick_font = max(6, style.get("tick_size", 11) - 3)
        else:
            tick_font = max(7, style.get("tick_size", 11) - 1)
        if n_x > 40:
            x_tickangle = -90
        elif longest_x > 12 or n_x > 12:
            x_tickangle = -45
        else:
            x_tickangle = 0
        if n_x <= 40:
            fig.update_xaxes(tickmode="linear", dtick=1, tickangle=x_tickangle, tickfont=dict(size=tick_font), automargin=True)
        else:
            fig.update_xaxes(tickmode="auto", tickangle=x_tickangle, tickfont=dict(size=tick_font), automargin=True)

    elif plot_type == "heatmap":
        heatmap_type = params.get("heatmap_type", "abundance")
        hstyle = params.get("heatmap_style") or style.get("engine")
        if heatmap_type != "correlation" and hstyle in ("lipidone", "publication"):
            fig = _heatmap_publication(df, sample_meta, feature_metadata, style, params)
            return json.loads(fig.to_json())
        if heatmap_type != "correlation" and hstyle == "seaborn":
            fig = _heatmap_seaborn(df, sample_meta, feature_metadata, style, params)
            return json.loads(fig.to_json())
        if heatmap_type != "correlation" and hstyle == "matplotlib":
            fig = _heatmap_matplotlib(df, sample_meta, feature_metadata, style, params)
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
            short_cols = [_shorten_name(c) for c in corr.columns]
            fig = go.Figure(data=go.Heatmap(
                z=corr.values, x=short_cols, y=short_cols,
                colorscale=colorscale, zmid=1,
                colorbar=dict(title={"text": "r", "side": "right"})))
            _apply_base_layout(fig, style, title="Sample Correlation Heatmap", x_labels=short_cols)
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

            sample_groups = {c: sample_meta.get(c, "Unknown") for c in plot_df.columns}
            present_groups = sorted(set(sample_groups.values()))
            group_order = params.get("group_order") or present_groups
            if isinstance(group_order, str):
                group_order = [g.strip() for g in group_order.split(",") if g.strip()]
            group_order = [g for g in group_order if g in present_groups]
            group_order += [g for g in present_groups if g not in group_order]
            if "Unknown" in group_order:
                group_order = [g for g in group_order if g != "Unknown"] + ["Unknown"]
            gcolor_map = _group_color_map(style, group_order)

            # Order columns by group_order and optionally cluster within each group
            group_to_cols = {}
            for c in plot_df.columns:
                g = sample_groups.get(c, "Unknown")
                group_to_cols.setdefault(g, []).append(c)
            ordered_cols = []
            for g in group_order:
                cols = group_to_cols.get(g, [])
                if cluster_cols and len(cols) > 2:
                    try:
                        sub_df = plot_df[cols]
                        dist = pdist(sub_df.T.values, metric=metric)
                        link = linkage(dist, method=method)
                        order = leaves_list(link)
                        cols = [cols[i] for i in order]
                    except Exception:
                        pass
                ordered_cols.extend(cols)
            if ordered_cols:
                plot_df = plot_df[ordered_cols]

            if cluster_rows and len(plot_df) > 2:
                try:
                    dist = pdist(plot_df.values, metric=metric)
                    link = linkage(dist, method=method)
                    order = leaves_list(link)
                    plot_df = plot_df.iloc[order]
                except Exception:
                    pass

            group_codes = [group_order.index(sample_groups.get(c, "Unknown")) for c in plot_df.columns]
            n_groups = max(len(group_order), 1)
            if n_groups == 1:
                group_colorscale = [[0, gcolor_map[group_order[0]]], [1, gcolor_map[group_order[0]]]]
            else:
                group_colorscale = [[i / (n_groups - 1), gcolor_map[g]] for i, g in enumerate(group_order)]

            m, n = plot_df.shape
            height = max(600, min(1600, m * 16 + 260))
            feature_ids = [feature_metadata[i].get("feature_id", i) if i < len(feature_metadata) else i for i in plot_df.index]
            short_cols = [_shorten_name(c) for c in plot_df.columns]
            short_rows = [_shorten_name(_clean_lipid_name(str(fid))) for fid in feature_ids]
            max_x_len = max([len(s) for s in short_cols], default=1)
            max_y_len = max([len(s) for s in short_rows], default=1)

            # Decide x-axis label density/rotation from sample name length and count.
            long_x_labels = max_x_len > 12
            x_step = _tick_text_step(n, max_labels=18 if long_x_labels else 25)
            x_tickvals = list(range(0, n, x_step))
            x_ticktext = [short_cols[i] for i in x_tickvals]
            x_tick_size = max(8, min(10 if long_x_labels else 13, int(300 / max(n, 1))))
            y_tick_size = max(7, min(11, int(height * 0.5 / max(m, 1))))
            if max_x_len > 16 or (long_x_labels and n > 8):
                x_tickangle = -90
            elif long_x_labels or n > 15:
                x_tickangle = -45
            elif n > 25:
                x_tickangle = -60
            else:
                x_tickangle = 0
            # Allow one label per row as long as there is ~14 px of vertical space per label.
            y_step = _tick_text_step(m, max_labels=max(1, int(height / 14)))
            y_tickvals = feature_ids[::y_step]
            y_ticktext = short_rows[::y_step]

            max_group_len = max([len(str(g)) for g in group_order], default=0)
            group_legend_width = max_group_len * 8 + 55
            right_margin = max(260, int(max_y_len * y_tick_size * 0.75) + 150 + group_legend_width)
            projection = abs(np.sin(np.radians(x_tickangle))) if x_tickangle != 0 else 0
            x_label_extra = int(max_x_len * x_tick_size * projection) + 60 if x_tickangle != 0 else x_tick_size + 30
            bottom_margin = max(110, x_label_extra + 70)

            group_frac = 50 / height
            heatmap_frac = max(0.5, 0.98 - group_frac)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.02, row_heights=[group_frac, heatmap_frac])
            fig.add_trace(go.Heatmap(
                z=[group_codes],
                x=list(range(n)),
                y=[""],
                colorscale=group_colorscale,
                showscale=False,
                showlegend=False,
                hoverinfo="skip",
            ), row=1, col=1)
            fig.add_trace(go.Heatmap(
                z=plot_df.values,
                x=list(range(n)),
                y=list(range(m)),
                colorscale=colorscale,
                zmid=zmid,
                showlegend=False,
                colorbar=dict(
                    title={"text": cbar_title, "side": "right", "font": {"size": 11}},
                    xref="container",
                    x=1.0,
                    xanchor="right",
                    xpad=10,
                    len=0.65,
                    thickness=12,
                    outlinewidth=0,
                    tickfont={"size": 9},
                ),
                hovertemplate="Feature: %{customdata[0]}<br>Sample: %{customdata[1]}<br>Value: %{z:.3f}<extra></extra>",
                customdata=np.array([[[_shorten_name(_clean_lipid_name(str(feature_ids[i])), 60), _shorten_name(c, 60)] for c in plot_df.columns] for i in range(m)]),
            ), row=2, col=1)

            for g in group_order:
                fig.add_trace(go.Scatter(
                    x=[None], y=[None], mode="markers",
                    marker=dict(size=10, color=gcolor_map[g]),
                    name=str(g), showlegend=True, hoverinfo="skip", visible="legendonly",
                ), row=2, col=1)

            fig.update_layout(
                showlegend=True,
                legend=dict(
                    xref="container",
                    yref="paper",
                    x=1.0,
                    y=0.98,
                    xanchor="right",
                    yanchor="top",
                    orientation="v",
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="#e2e8f0",
                    borderwidth=1,
                    font=dict(size=10),
                ),
                font={"family": style.get("font_family"), "color": "#334155"},
                paper_bgcolor=style.get("paper_bgcolor"),
                plot_bgcolor=style.get("plot_bgcolor"),
                title={
                    "text": f"Top {m} most-variable features",
                    "font": {"size": style.get("title_size"), "color": "#1e293b"},
                    "x": 0.5,
                    "xanchor": "center",
                    "y": 0.99,
                    "yanchor": "top",
                    "pad": {"b": 20},
                },
                margin={"l": 80, "r": right_margin, "t": 100, "b": bottom_margin},
                height=height,
            )
            fig.update_xaxes(range=[-0.5, n - 0.5], showticklabels=False, showgrid=False, zeroline=False, row=1, col=1)
            fig.update_xaxes(
                range=[-0.5, n - 0.5],
                tickmode="array",
                tickvals=x_tickvals,
                ticktext=x_ticktext,
                tickangle=x_tickangle,
                side="bottom",
                tickfont={"size": x_tick_size},
                automargin=True,
                showgrid=False,
                zeroline=False,
                row=2, col=1,
            )
            fig.update_yaxes(showticklabels=False, row=1, col=1)
            fig.update_yaxes(
                tickmode="array",
                tickvals=list(range(0, m, y_step)),
                ticktext=short_rows[::y_step],
                tickfont={"size": y_tick_size},
                side="right",
                automargin=True,
                showgrid=False,
                zeroline=False,
                row=2, col=1,
            )

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
        display_names = [_shorten_name(c) for c in X.index]
        color_map = _group_color_map(style, labels)

        if ptype == "scree":
            fig = px.bar(x=[f"PC{i+1}" for i in range(len(pca.explained_variance_ratio_))],
                         y=pca.explained_variance_ratio_ * 100,
                         labels={"x": "Principal Component", "y": "Variance Explained (%)"})
            _apply_base_layout(fig, style, title="PCA Scree Plot")
        elif ptype == "loading":
            loadings = pca.components_[0]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(feature_metadata)]
            top_idx = np.argsort(np.abs(loadings))[-50:]
            x_labels = [feat_ids[i] for i in top_idx]
            fig = px.bar(x=x_labels, y=[loadings[i] for i in top_idx],
                         labels={"x": "Feature", "y": "PC1 Loading"})
            _apply_base_layout(fig, style, title="PCA Top Loadings (PC1)", x_labels=x_labels)
            n_x = len(x_labels)
            longest_x = max([len(str(l)) for l in x_labels], default=0)
            if n_x > 25 or longest_x > 18:
                tick_font = max(6, style.get("tick_size", 11) - 3)
                x_tickangle = -90
            elif n_x > 12 or longest_x > 10:
                tick_font = max(7, style.get("tick_size", 11) - 2)
                x_tickangle = -45
            else:
                tick_font = max(7, style.get("tick_size", 11) - 1)
                x_tickangle = -45
            fig.update_xaxes(tickmode="linear", dtick=1, tickangle=x_tickangle, tickfont=dict(size=tick_font), automargin=True)
        elif ptype == "biplot":
            fig = go.Figure()
            for g in sorted(set(labels)):
                idx = [i for i, l in enumerate(labels) if l == g]
                idx_arr = np.array(idx)
                fig.add_trace(go.Scatter(
                    x=scores[idx_arr, 0], y=scores[idx_arr, 1], mode="markers",
                    name=g, marker_color=color_map[g], marker_size=style.get("marker_size"),
                    customdata=np.column_stack([[display_names[i] for i in idx], [g] * len(idx)]),
                    hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
                ))
            loadings = pca.components_[:2]
            feat_ids = [m.get("feature_id", i) for i, m in enumerate(feature_metadata)]
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
                fig = _pca_publication(scores, labels, pca, display_names, style, params)
                return json.loads(fig.to_json())
            fig = go.Figure()
            for g in sorted(set(labels)):
                idx = [i for i, l in enumerate(labels) if l == g]
                idx_arr = np.array(idx)
                fig.add_trace(go.Scatter(
                    x=scores[idx_arr, 0], y=scores[idx_arr, 1], mode="markers",
                    name=g, marker_color=color_map[g], marker_size=style.get("marker_size"),
                    customdata=np.column_stack([[display_names[i] for i in idx], [g] * len(idx)]),
                    hovertemplate="%{customdata[0]}<br>Group: %{customdata[1]}<extra></extra>",
                ))
            fig.update_layout(xaxis_title=f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                              yaxis_title=f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)")
            _apply_base_layout(fig, style, title="PCA Score Plot")

    elif plot_type == "volcano":
        fc_thresh = float(params.get("fc_threshold")) if params.get("fc_threshold") is not None else 0.5
        padj_thresh = float(params.get("padj_threshold")) if params.get("padj_threshold") is not None else float(params.get("p_threshold", 0.05))
        padj_thresh = max(padj_thresh, 1e-300)
        show_labels = bool(params.get("show_labels", False))
        top_n = max(0, int(params.get("top_n", 10)))
        up_color = style.get("up_color", "#c44e52")
        down_color = style.get("down_color", "#2e6575")
        ns_color = style.get("non_significant_color", "#a0aec0")

        points = _build_volcano_points(params.get("stats", []), fc_thresh, padj_thresh, up_color, down_color, ns_color)

        if style.get("engine") == "publication":
            fig = _volcano_publication(points, fc_thresh, padj_thresh, style, params)
            return json.loads(fig.to_json())

        fig = go.Figure()
        groups = {}
        for p in points:
            groups.setdefault(p["label"], []).append(p)
        group_a = params.get("group_a", "A")
        group_b = params.get("group_b", "B")
        names = {"UP": f"Higher in {group_b}", "DOWN": f"Higher in {group_a}", "NS": "Not significant"}
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

        y_thr = -np.log10(padj_thresh)
        x_abs = max(abs(min([p["lfc"] for p in points] or [-1], default=-1)), abs(max([p["lfc"] for p in points] or [1], default=1)), fc_thresh)
        x_pad = max(x_abs * 0.08, 0.2)
        y_max = max(max([p["neglogp"] for p in points] or [0], default=0), y_thr * 1.25) * 1.45
        line_color = "#475569"
        fig.add_hline(y=y_thr, line_dash="dash", line_color=line_color, line_width=1.5)
        fig.add_vline(x=fc_thresh, line_dash="dash", line_color=line_color, line_width=1.5)
        fig.add_vline(x=-fc_thresh, line_dash="dash", line_color=line_color, line_width=1.5)
        fig.update_layout(
            xaxis_title=f"log2 Fold Change ({group_b} / {group_a})",
            yaxis_title="-log10 p-value",
        )
        _apply_base_layout(fig, style, title="Volcano Plot")
        fig.update_layout(margin=dict(l=80, r=90, t=140, b=70))
        fig.update_xaxes(range=[-x_abs - x_pad, x_abs + x_pad])
        fig.update_yaxes(range=[0, y_max])

        if show_labels and top_n > 0 and points:
            candidates = [p for p in points if abs(p["lfc"]) >= fc_thresh and p["padj"] < padj_thresh]
            candidates.sort(key=lambda p: p["padj"])
            top = candidates[:top_n]
            if top:
                x_vals = [p["lfc"] for p in top]
                y_vals = [p["neglogp"] for p in top]
                labels = [_shorten_name(p["name"], 35) for p in top]
                x_min, x_max = -x_abs - x_pad, x_abs + x_pad
                y_min, y_max = 0, y_max
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
        classes = [_extract_lipid_class(f.get("feature_id", ""), f) for f in feature_metadata]
        if len(classes) != len(df):
            classes = classes[: len(df)]
        # Exclude rows marked as non-representative isobaric substitutions from class rollups.
        exclude_mask = [bool(f.get("isobaric_substitution_rollup_exclude")) for f in feature_metadata]
        if len(exclude_mask) != len(df):
            exclude_mask = exclude_mask[: len(df)]
        keep = [not e for e in exclude_mask]
        int_df = _intensity_df(df[keep], dataset.processing_history)
        classes = [c for c, ok in zip(classes, keep) if ok]
        totals = _lipid_class_totals(int_df, classes)
        sample_groups = {c: sample_meta.get(c, "unknown") for c in totals.columns}
        unique_groups = sorted(set(sample_groups.values()))
        fig = go.Figure()
        color_map = _group_color_map(style, unique_groups)
        x = totals.index.tolist()
        y_max = 0
        for g in unique_groups:
            cols = [c for c in totals.columns if sample_groups[c] == g]
            means = []
            for cls in x:
                vals = [_safe_float(totals.loc[cls, col]) for col in cols]
                means.append(float(np.mean(vals)) if vals else 0.0)
                y_max = max(y_max, max(means) if means else 0)
            fig.add_trace(go.Bar(name=g, x=x, y=means, marker_color=color_map[g]))
        fig.update_layout(barmode="group", xaxis_title="Lipid class", yaxis_title="Total intensity")
        _apply_base_layout(fig, style, title="Total abundance by lipid class × group", x_labels=x)
        fig.update_xaxes(tickmode="linear", dtick=1, automargin=True)
        fig.update_yaxes(range=[0, y_max * 1.15])

    elif plot_type == "per_lipid_bars":
        stats_data = params.get("stats", [])
        group_a = params.get("group_a", "A")
        group_b = params.get("group_b", "B")
        selected_groups = params.get("groups") or [group_a, group_b]
        selected_groups = [g for g in selected_groups if g]
        top_n = int(params.get("top_n", 8))
        int_df = _intensity_df(df, dataset.processing_history)
        sorted_stats = sorted([s for s in stats_data if s.get("padj") is not None], key=lambda s: _safe_float(s.get("padj", 1), 1.0))[:top_n]
        figures = []
        color_map = _group_color_map(style, selected_groups)
        for s in sorted_stats:
            fid = s.get("feature_id", "")
            idx = _get_feature_index(feature_metadata, fid)
            if idx < 0 or idx >= len(int_df) or feature_metadata[idx].get('feature_id') != fid:
                continue
            samples = int_df.columns.tolist()
            values = int_df.iloc[idx].values
            sample_groups = [sample_meta.get(c, "unknown") for c in samples]
            group_vals: Dict[str, List[float]] = {g: [] for g in selected_groups}
            for c, g in zip(samples, sample_groups):
                if g in group_vals:
                    group_vals[g].append(_safe_float(values[samples.index(c)]))
            ordered = [g for g in selected_groups if group_vals.get(g)]
            if not ordered:
                continue
            means = []
            sems_up = []
            sems_down = []
            y_max = 0
            for g in ordered:
                vals = np.array(group_vals[g])
                mean = float(np.mean(vals))
                sem = float(scipy_stats.sem(vals)) if len(vals) > 1 else 0.0
                means.append(mean)
                sems_up.append(sem)
                sems_down.append(min(sem, mean))
                y_max = max(y_max, mean + sem, max(vals) if len(vals) else 0)
            xpos = list(range(len(ordered)))
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=xpos,
                y=means,
                marker_color=[color_map[g] for g in ordered],
                error_y=dict(type="data", array=sems_up, arrayminus=sems_down, visible=True, symmetric=False),
                showlegend=False,
            ))
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
            title = f"{_shorten_name(fid, 45)}"
            padj = _safe_float(s.get("padj"), 1.0)
            if padj < 0.001:
                title += " ***"
            elif padj < 0.01:
                title += " **"
            elif padj < 0.05:
                title += " *"
            test_label = s.get("test", params.get("test", "t-test"))
            subtitle = f"p={padj:.3g} ({test_label})"
            fig.update_xaxes(tickmode="array", tickvals=xpos, ticktext=ordered)
            fig.update_layout(xaxis_title="", yaxis_title="Mean intensity")
            _apply_base_layout(fig, style, title=title, x_labels=ordered)
            n_groups = len(ordered)
            if n_groups > 8:
                fig.update_xaxes(tickangle=-90, tickfont=dict(size=max(7, style.get("tick_size", 11) - 2)), automargin=True)
                fig.update_layout(margin={"l": 60, "r": 50, "t": 100, "b": max(120, min(200, n_groups * 12))})
            else:
                fig.update_xaxes(automargin=True)
            fig.add_annotation(
                text=subtitle,
                xref="paper", yref="paper",
                x=0.99, y=0.99,
                showarrow=False,
                font=dict(size=10, color="#64748b"),
                xanchor="right", yanchor="top",
            )
            fig.update_yaxes(range=[0, y_max * 1.15])
            figures.append(json.loads(fig.to_json()))
        return figures

    elif plot_type == "outlier":
        fig = _outlier_plot(df, sample_meta, style, params)

    elif plot_type == "functional":
        fig = _functional_volcano(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "food_profile":
        fig = _food_profile(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "chain_space":
        fig = _chain_space_figures(df, sample_meta, feature_metadata, style, params, history=dataset.processing_history)
        return fig

    elif plot_type == "pls_da":
        fig = _pls_da_figure(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "opls_da":
        fig = _opls_da_figure(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "biomarker":
        fig = _biomarker_figure(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "permanova":
        fig = _permanova_figure(df, sample_meta, feature_metadata, style, params)

    elif plot_type == "rt_mz":
        mz = [_safe_float(f.get("mz", 0)) for f in feature_metadata]
        rt = [_safe_float(f.get("rt", 0)) for f in feature_metadata]
        grades = [str(f.get("grade", "unknown")) for f in feature_metadata]
        fig = px.scatter(x=mz, y=rt, color=grades,
                         labels={"x": "m/z", "y": "Retention Time"})
        _apply_base_layout(fig, style, title="Retention Time vs m/z")

    else:
        fig = go.Figure()
        _apply_base_layout(fig, style, title="Unsupported plot type")

    return json.loads(fig.to_json())

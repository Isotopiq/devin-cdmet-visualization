import math
import json
import numpy as np
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe


# Simplified central carbon metabolism edges used for the example flux map.
FLUX_EDGES = [
    ("Glucose-6-phosphate", "Fructose-6-phosphate"),
    ("Fructose-6-phosphate", "3-Phosphoglycerate"),
    ("Glucose-6-phosphate", "3-Phosphoglycerate"),
    ("3-Phosphoglycerate", "Phosphoenolpyruvate"),
    ("Phosphoenolpyruvate", "Pyruvate"),
    ("Pyruvate", "Acetyl-CoA"),
    ("Pyruvate", "Lactate"),
    ("Pyruvate", "Alanine"),
    ("Acetyl-CoA", "Citrate"),
    ("Citrate", "alpha-Ketoglutarate"),
    ("alpha-Ketoglutarate", "Succinate"),
    ("Succinate", "Malate"),
    ("Malate", "Citrate"),
    ("Malate", "Aspartate"),
]


def _sanitize_series(s):
    if isinstance(s, (pd.Series, pd.DataFrame)):
        return _to_json_safe(s.replace([np.inf, -np.inf], np.nan).fillna(0).to_dict())
    return _to_json_safe(s)


def _feature_lookup(dataset: models.Dataset, df: pd.DataFrame):
    """Return a list of feature_id values aligned with df rows."""
    meta = dataset.feature_metadata or []
    lookup = []
    for idx in df.index:
        i = int(idx) if isinstance(idx, (int, np.integer, float, np.floating)) else None
        if i is not None and 0 <= i < len(meta):
            lookup.append(str(meta[i].get("feature_id", i)))
        else:
            lookup.append(str(idx))
    return lookup


def _series_by_feature(series: pd.Series, feature_ids) -> dict:
    out = {}
    for i, fid in enumerate(feature_ids):
        if i < len(series):
            out[fid] = _to_json_safe(series.iloc[i])
        else:
            out[fid] = None
    return out


def _flux_map(
    feature_ids,
    mean_labeled_atoms: pd.Series,
    total_intensity: pd.Series,
    title: str = "Flux map",
):
    """Build a Plotly network graph from isotope labeling data."""
    mean_map = {fid: float(mean_labeled_atoms.iloc[i]) if i < len(mean_labeled_atoms) else 0.0 for i, fid in enumerate(feature_ids)}
    total_map = {fid: float(total_intensity.iloc[i]) if i < len(total_intensity) else 0.0 for i, fid in enumerate(feature_ids)}

    G = nx.DiGraph()
    nodes = set()
    for src, tgt in FLUX_EDGES:
        if src in mean_map and tgt in mean_map:
            G.add_edge(src, tgt)
            nodes.add(src)
            nodes.add(tgt)

    if len(nodes) == 0:
        return None

    pos = nx.spring_layout(G, seed=42, k=4, iterations=300)

    max_mean = max((v for v in mean_map.values() if math.isfinite(v)), default=1) or 1
    max_total = max((v for v in total_map.values() if math.isfinite(v)), default=1) or 1

    node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
    for n in nodes:
        x, y = pos[n]
        node_x.append(x)
        node_y.append(y)
        node_text.append(n)
        node_color.append(mean_map.get(n, 0))
        node_size.append(15 + 25 * (total_map.get(n, 0) / max_total))

    edge_traces = []
    annotations = []
    for src, tgt in G.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        mean_src = mean_map.get(src, 0)
        mean_tgt = mean_map.get(tgt, 0)
        gradient = mean_tgt - mean_src
        flux_value = max(abs(gradient), 0)
        width = 1 + 5 * min(flux_value / max(1, max_mean), 1.0)
        color = "#10b981" if gradient >= 0 else "#64748b"

        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="text",
                text=f"{src} → {tgt}<br>Δ mean labels: {gradient:.3f}",
                showlegend=False,
            )
        )

        annotations.append(
            dict(
                x=x0 + 0.9 * (x1 - x0),
                y=y0 + 0.9 * (y1 - y0),
                ax=x0 + 0.1 * (x1 - x0),
                ay=y0 + 0.1 * (y1 - y0),
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=max(1, width / 2),
                arrowcolor=color,
            )
        )

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color="#334155"),
        marker=dict(
            showscale=True,
            colorscale="Viridis",
            color=node_color,
            size=node_size,
            colorbar=dict(title="Mean<br>labeled<br>atoms", thickness=12, x=1.04),
            line=dict(width=1, color="DarkSlateGrey"),
        ),
        hovertemplate="%{text}<br>Mean labeled atoms: %{marker.color:.3f}<extra></extra>",
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title=dict(text=title, x=0.5),
        showlegend=False,
        autosize=True,
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="y"),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=60, r=120, t=60, b=60),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=annotations,
    )
    return json.loads(fig.to_json())


def run_isotope_analysis(dataset: models.Dataset, req: schemas.IsotopeRequest):
    df = to_dataframe(dataset)
    feature_ids = _feature_lookup(dataset, df)
    tracer = req.tracer
    max_label = max(0, int(req.max_label))

    isotopologue_cols = [c for c in df.columns if "M+" in str(c) or tracer in str(c)]
    if not isotopologue_cols:
        return {"error": "No isotopologue columns found. Columns must include M+0, M+1, etc."}

    # Keep only M+0..M+max_label to avoid mis-aligned columns beyond the tracer range
    ordered_cols = []
    for i in range(max_label + 1):
        col = f"M+{i}"
        if col in isotopologue_cols:
            ordered_cols.append(col)
    if not ordered_cols:
        ordered_cols = isotopologue_cols

    # Ensure non-negative values before computing fractions
    df_iso = df[ordered_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    df_iso = df_iso.clip(lower=0)

    row_sums = df_iso.sum(axis=1).replace(0, np.nan)
    fractions = df_iso.div(row_sums, axis=0).fillna(0)

    total_labeled = 1 - fractions.get("M+0", pd.Series(0, index=fractions.index))

    if req.circulating_enrichment:
        circ = float(req.circulating_enrichment)
        if circ > 0:
            fractional_enrichment = total_labeled / circ
        else:
            fractional_enrichment = total_labeled
    else:
        fractional_enrichment = total_labeled

    mean_labeled_atoms = sum(
        i * fractions.get(f"M+{i}", pd.Series(0, index=fractions.index))
        for i in range(max_label + 1)
    )
    pooled_labeling = mean_labeled_atoms / max_label if max_label > 0 else pd.Series(0, index=fractions.index)

    fractions_by_feature = {}
    for i, fid in enumerate(feature_ids):
        if i < len(fractions):
            row = fractions.iloc[i]
            fractions_by_feature[fid] = {col: _to_json_safe(row[col]) for col in ordered_cols}
        else:
            fractions_by_feature[fid] = {}

    results = {
        "tracer": tracer,
        "max_label": max_label,
        "fractions": fractions_by_feature,
        "total_labeled_fraction": _series_by_feature(total_labeled, feature_ids),
        "fractional_enrichment": _series_by_feature(fractional_enrichment, feature_ids),
        "mean_labeled_atoms": _series_by_feature(mean_labeled_atoms, feature_ids),
        "pooled_labeling": _series_by_feature(pooled_labeling, feature_ids),
        "flux_map": _flux_map(feature_ids, mean_labeled_atoms, row_sums.fillna(0)),
    }
    return results

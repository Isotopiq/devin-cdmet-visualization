import json
import plotly.graph_objects as go
from app import models, schemas
from app.services.stats import run_statistical_test
from app.services.plots import _merge_style
from app.services.pathway_apis import kegg_enrichment, reactome_enrichment, go_enrichment, enrichment_bar_figure, enrichment_table_figure


def _build_custom_figure(nodes, edges, value_type):
    fig = go.Figure()
    for edge in edges:
        x0 = next((n["x"] for n in nodes if n["id"] == edge["source"]), 0)
        y0 = next((n["y"] for n in nodes if n["id"] == edge["source"]), 0)
        x1 = next((n["x"] for n in nodes if n["id"] == edge["target"]), 0)
        y1 = next((n["y"] for n in nodes if n["id"] == edge["target"]), 0)
        fig.add_trace(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=2, color="#888"),
            hoverinfo="text",
            text=edge.get("label", ""),
            showlegend=False,
        ))

    node_text = [f"{n['label']}<br>{value_type}: {n.get('value', 'measured')}" for n in nodes]
    fig.add_trace(go.Scatter(
        x=[n["x"] for n in nodes],
        y=[n["y"] for n in nodes],
        mode="markers+text",
        marker=dict(size=30, color="lightblue"),
        text=[n["label"] for n in nodes],
        textposition="top center",
        hovertext=node_text,
        showlegend=False,
    ))

    fig.update_layout(
        title=f"Pathway Map ({value_type})",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
    )
    return json.loads(fig.to_json())


async def build_pathway(dataset: models.Dataset, req: schemas.PathwayRequest):
    source = req.pathway_source
    style = _merge_style({})

    if req.custom_nodes and req.custom_edges and source == "custom":
        return _build_custom_figure(req.custom_nodes, req.custom_edges, req.value_type)

    # Determine feature list / significant feature list
    feature_names = [m.get("feature_id") or m.get("name") or f"feature_{i}" for i, m in enumerate(dataset.feature_metadata)]

    significant_names = []
    if req.group_a and req.group_b:
        stats_req = schemas.StatsRequest(
            test=req.test or "t_test",
            group_a=req.group_a,
            group_b=req.group_b,
            paired=False,
            multiple_testing=req.multiple_testing or "fdr_bh",
            alpha=req.p_threshold or 0.05,
        )
        stats = run_statistical_test(dataset, stats_req)
        fc_thresh = req.fc_threshold or 1.0
        p_thresh = req.p_threshold or 0.05
        for r in stats.get("results", []):
            lfc = r.get("log2fc")
            padj = r.get("padj")
            if lfc is None or padj is None:
                continue
            if abs(lfc) >= fc_thresh and padj < p_thresh:
                significant_names.append(r.get("feature_id", ""))
    if not significant_names:
        significant_names = req.features or feature_names

    if source == "kegg":
        data = await kegg_enrichment(feature_names, significant_names, organism=req.organism or "hsa", top_n=req.top_n or 20)
        if "error" in data:
            fig = go.Figure()
            fig.add_annotation(text=data["error"], showarrow=False, font=dict(size=14, color="red"))
            return fig.to_dict()
        fig_bar = enrichment_bar_figure(data["pathways"], "KEGG pathway enrichment", style)
        fig_table = enrichment_table_figure(data["pathways"], "KEGG pathway results", style)
        return {"bar": fig_bar, "table": fig_table, "pathways": data["pathways"], "source": "kegg"}

    if source == "reactome":
        data = await reactome_enrichment(significant_names, top_n=req.top_n or 20)
        if "error" in data:
            fig = go.Figure()
            fig.add_annotation(text=data["error"], showarrow=False, font=dict(size=14, color="red"))
            return fig.to_dict()
        fig_bar = enrichment_bar_figure(data["pathways"], "Reactome pathway enrichment", style)
        fig_table = enrichment_table_figure(data["pathways"], "Reactome pathway results", style)
        return {"bar": fig_bar, "table": fig_table, "pathways": data["pathways"], "source": "reactome"}

    if source == "go":
        data = await go_enrichment(significant_names, organism=req.organism or "hsapiens", top_n=req.top_n or 20)
        if "error" in data:
            fig = go.Figure()
            fig.add_annotation(text=data["error"], showarrow=False, font=dict(size=14, color="red"))
            return fig.to_dict()
        fig_bar = enrichment_bar_figure(data["pathways"], "GO enrichment", style)
        fig_table = enrichment_table_figure(data["pathways"], "GO term results", style)
        return {"bar": fig_bar, "table": fig_table, "pathways": data["pathways"], "source": "go"}

    # Default / static fallback
    nodes = [
        {"id": "Glucose", "label": "Glucose", "x": 0, "y": 0},
        {"id": "G6P", "label": "Glucose-6-P", "x": 1, "y": 0},
        {"id": "F6P", "label": "Fructose-6-P", "x": 2, "y": 0},
        {"id": "PYR", "label": "Pyruvate", "x": 3, "y": 0},
    ]
    edges = [
        {"source": "Glucose", "target": "G6P", "label": "HK"},
        {"source": "G6P", "target": "F6P", "label": "PGI"},
        {"source": "F6P", "target": "PYR", "label": "glycolysis"},
    ]
    return _build_custom_figure(nodes, edges, req.value_type)

import json
import plotly.graph_objects as go
from app import models, schemas


def build_pathway(dataset: models.Dataset, req: schemas.PathwayRequest):
    value_type = req.value_type
    source = req.pathway_source

    if req.custom_nodes and req.custom_edges:
        nodes = req.custom_nodes
        edges = req.custom_edges
    else:
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

    node_x = [n["x"] for n in nodes]
    node_y = [n["y"] for n in nodes]
    node_text = [f"{n['label']}<br>{value_type}: {n.get('value', 'measured')}" for n in nodes]

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

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(size=30, color="lightblue"),
        text=[n["label"] for n in nodes],
        textposition="top center",
        hovertext=node_text,
        showlegend=False,
    ))

    fig.update_layout(
        title=f"Pathway Map ({source}) - {value_type}",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
    )
    return json.loads(fig.to_json())

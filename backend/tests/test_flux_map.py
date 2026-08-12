import math

import networkx as nx
import pytest

from app.services.flux_map import (
    _build_lipid_graph,
    _compute_positions,
    _graphml_for_network,
    _make_plotly_figure,
    _name_score,
    _normalize,
    _parse_lipid,
    FLUX_STYLES,
)


def test_normalize_preserves_lipid_class_prefixes():
    assert _normalize("LPC(14:0)") == "lpc 14 0"
    assert _normalize("PC(34:1)") == "pc 34 1"
    assert _normalize("PG(14:0)") == "pg 14 0"


def test_normalize_strips_stereochemistry_only_at_start():
    assert _normalize("D-Glucose") == "glucose"
    assert _normalize("L-Alanine") == "alanine"
    assert _normalize("alpha-ketoglutarate") == "2-oxoglutarate"
    assert _normalize("g6p") == "glucose 6 phosphate"
    assert _normalize("g 6 p") == "glucose 6 phosphate"


def test_name_score_ignores_pure_numeric_matches():
    # PC(40:6) should not match Glucose-6-phosphate just because both contain "6".
    assert _name_score("PC(40:6)", "Glucose-6-phosphate", "glucose_6_phosphate", None, None) == 0.0
    assert _name_score("PC(38:3)", "3-Phosphoglycerate", "3pg_c", None, None) == 0.0


def test_name_score_matches_common_abbreviations():
    assert _name_score("PEP", "Phosphoenolpyruvate", "pep_c", None, None) == 1.0
    assert _name_score("3PG", "3-Phosphoglycerate", "3pg_c", None, None) == 1.0


def test_parse_lipid_parses_varied_notations():
    p = _parse_lipid("PC(34:1)")
    assert p["class"] == "PC"
    assert p["total_c"] == 34
    assert p["total_u"] == 1
    assert p["superclass"] == "Glycerophospholipid"

    p = _parse_lipid("SM(d18:1/16:0)")
    assert p["class"] == "SM"
    assert p["total_c"] == 34
    assert p["total_u"] == 1
    assert p["superclass"] == "Sphingolipid"

    p = _parse_lipid("TG(16:0/18:1/18:2)")
    assert p["class"] == "TG"
    assert p["total_c"] == 52
    assert p["total_u"] == 3
    assert p["superclass"] == "Neutral lipid"


def test_build_lipid_graph_creates_class_and_acyl_edges():
    features = ["LPC(14:0)", "LPC(16:0)", "LPC(16:1)", "PC(34:1)", "PE(34:1)", "SM(d18:1/16:0)"]
    G = _build_lipid_graph(features, features, [""] * len(features))
    assert len(G.nodes()) == 6
    # PC(34:1) and PE(34:1) share composition -> class transition edge.
    assert G.has_edge("PC(34:1)", "PE(34:1)") or G.has_edge("PE(34:1)", "PC(34:1)")
    # LPC(14:0) and LPC(16:0) differ by +2C -> acyl edit edge.
    assert G.has_edge("LPC(14:0)", "LPC(16:0)")
    assert G.nodes["PC(34:1)"]["pathway"] == "Glycerophospholipid"
    assert G.nodes["SM(d18:1/16:0)"]["pathway"] == "Sphingolipid"


def test_compute_positions_returns_valid_coordinates():
    G = nx.DiGraph()
    G.add_edge("a", "b")
    pos = _compute_positions(G, "spring")
    assert set(pos.keys()) == {"a", "b"}
    assert all(math.isfinite(v[0]) and math.isfinite(v[1]) for v in pos.values())


def test_make_plotly_figure_returns_figure_with_hover_info():
    G = nx.DiGraph()
    G.add_node("A", name="A", formula="C6H12O6", pathway="Carbohydrate Metabolism")
    G.add_node("B", name="B", formula="C3H6O3", pathway="Carbohydrate Metabolism")
    G.add_edge("A", "B", reaction="A → B")
    pos = {"A": (0.0, 0.0), "B": (1.0, 0.0)}
    mean_map = {"A": 0.2, "B": 0.8}
    total_map = {"A": 100.0, "B": 200.0}
    fig = _make_plotly_figure(
        G, pos, mean_map, total_map, {"A": "A", "B": "B"}, {"A": "A", "B": "B"},
        "full", "label_gradient", "Flux map", style="classic", show_labels=True,
    )
    assert "data" in fig
    assert "layout" in fig
    assert any("Mean labeled atoms" in str(trace.get("hovertemplate", "")) for trace in fig["data"])


def test_graphml_export_contains_nodes_and_edges():
    G = nx.DiGraph()
    G.add_node("A", name="A", formula="C6H12O6", pathway="Carbohydrate Metabolism")
    G.add_node("B", name="B", formula="C3H6O3", pathway="Carbohydrate Metabolism")
    G.add_edge("A", "B", reaction="A → B")
    pos = {"A": (0.0, 0.0), "B": (1.0, 0.0)}
    xml = _graphml_for_network(G, pos, {"A": 0.2, "B": 0.8}, {"A": 100.0, "B": 200.0}, title="Test")
    assert "<graphml" in xml
    assert 'node id="A"' in xml
    assert 'edge source="A" target="B"' in xml
    assert "mean_labeled_atoms" in xml
    assert "total_intensity" in xml


def test_fluxer_style_is_available():
    assert "fluxer" in FLUX_STYLES

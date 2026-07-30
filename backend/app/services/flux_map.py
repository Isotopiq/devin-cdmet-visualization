import asyncio
import json
import math
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import httpx
import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yaml

from app.services.preprocessing import _to_json_safe


BIGG_BASE = "http://bigg.ucsd.edu/api/v2"
GITHUB_RAW = "https://raw.githubusercontent.com"


# Manual central-carbon edges used when no external model is selected.
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


# Curated node positions (x, y, pathway) for the example central-carbon map.
PATHWAY_LAYOUT = {
    "Glucose-6-phosphate": (0.20, 0.40, "Carbohydrate Metabolism"),
    "Fructose-6-phosphate": (0.05, 0.32, "Carbohydrate Metabolism"),
    "3-Phosphoglycerate": (-0.25, 0.30, "Carbohydrate Metabolism"),
    "Phosphoenolpyruvate": (-0.35, 0.15, "Carbohydrate Metabolism"),
    "Pyruvate": (-0.40, 0.00, "Carbohydrate Metabolism"),
    "Acetyl-CoA": (-0.25, -0.15, "Cellular Respiration"),
    "Citrate": (0.00, -0.20, "Citric Acid Cycle"),
    "alpha-Ketoglutarate": (0.18, -0.28, "Citric Acid Cycle"),
    "Succinate": (0.30, -0.38, "Citric Acid Cycle"),
    "Malate": (0.15, -0.48, "Citric Acid Cycle"),
    "Aspartate": (0.42, -0.25, "Amino Acid Metabolism"),
    "Alanine": (-0.48, 0.12, "Amino Acid Metabolism"),
    "Lactate": (-0.45, -0.12, "Carbohydrate Metabolism"),
}


PATHWAY_COLORS = {
    "Carbohydrate Metabolism": "#f97316",
    "Pentose Phosphate Pathway": "#f59e0b",
    "Cellular Respiration": "#3b82f6",
    "Citric Acid Cycle": "#ef4444",
    "Amino Acid Metabolism": "#0ea5e9",
    "Urea Cycle": "#06b6d4",
    "Nucleotide & Protein Metabolism": "#8b5cf6",
    "Fatty Acid Synthesis": "#22c55e",
    "Lipid Metabolism": "#84cc16",
    "Steroid Metabolism": "#ec4899",
    "Vitamin & Cofactor Metabolism": "#64748b",
    "Other": "#94a3b8",
}


FLUX_STYLES = {
    "classic": {
        "node_line_width": 2,
        "edge_positive": "#10b981",
        "edge_negative": "#64748b",
        "edge_width_factor": 5.0,
        "colorscale": "Viridis",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "text_color": "#334155",
        "legend_font_color": "#334155",
        "legend_bgcolor": "rgba(255,255,255,0.7)",
        "marker_line": True,
        "annotations": True,
        "grid_color": None,
    },
    "dark_modern": {
        "node_line_width": 1,
        "edge_positive": "#22d3ee",
        "edge_negative": "#f472b6",
        "edge_width_factor": 4.0,
        "colorscale": "Plasma",
        "paper_bgcolor": "#0f172a",
        "plot_bgcolor": "#0f172a",
        "text_color": "#e2e8f0",
        "legend_font_color": "#e2e8f0",
        "legend_bgcolor": "rgba(15,23,42,0.7)",
        "marker_line": False,
        "annotations": True,
        "grid_color": "#1e293b",
    },
    "minimal": {
        "node_line_width": 0,
        "edge_positive": "#94a3b8",
        "edge_negative": "#cbd5e1",
        "edge_width_factor": 3.0,
        "colorscale": "Blues",
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "text_color": "#475569",
        "legend_font_color": "#475569",
        "legend_bgcolor": "rgba(255,255,255,0.9)",
        "marker_line": False,
        "annotations": False,
        "grid_color": None,
    },
    "subway": {
        "node_line_width": 2,
        "edge_positive": "#f59e0b",
        "edge_negative": "#3b82f6",
        "edge_width_factor": 5.0,
        "colorscale": "Turbo",
        "paper_bgcolor": "#f8fafc",
        "plot_bgcolor": "#f8fafc",
        "text_color": "#1e293b",
        "legend_font_color": "#1e293b",
        "legend_bgcolor": "rgba(248,250,252,0.9)",
        "marker_line": True,
        "annotations": True,
        "grid_color": None,
    },
}


# Static list of GEMs from the Metabolic Atlas / SysBioChalmers repository.
GEM_MODELS = [
    {"id": "Human-GEM", "repo": "SysBioChalmers/Human-GEM", "path": "model/Human-GEM.yml", "organism": "Homo sapiens"},
    {"id": "Mouse-GEM", "repo": "SysBioChalmers/Mouse-GEM", "path": "model/Mouse-GEM.yml", "organism": "Mus musculus"},
    {"id": "Rat-GEM", "repo": "SysBioChalmers/Rat-GEM", "path": "model/Rat-GEM.yml", "organism": "Rattus norvegicus"},
    {"id": "Zebrafish-GEM", "repo": "SysBioChalmers/Zebrafish-GEM", "path": "model/Zebrafish-GEM.yml", "organism": "Danio rerio"},
    {"id": "Fruitfly-GEM", "repo": "SysBioChalmers/Fruitfly-GEM", "path": "model/Fruitfly-GEM.yml", "organism": "Drosophila melanogaster"},
    {"id": "Yeast-GEM", "repo": "SysBioChalmers/yeast-gem", "path": "model/yeast-GEM.yml", "organism": "Saccharomyces cerevisiae"},
    {"id": "Worm-GEM", "repo": "SysBioChalmers/Worm-GEM", "path": "model/Worm-GEM.yml", "organism": "Caenorhabditis elegans"},
    {"id": "Human-maps", "repo": "SysBioChalmers/Human-maps", "path": "svg", "organism": "Homo sapiens (maps)"},
]


SYNONYMS = {
    "alpha ketoglutarate": "2-oxoglutarate",
    "a ketoglutarate": "2-oxoglutarate",
    "ketoglutarate": "2-oxoglutarate",
    "g 6 p": "glucose 6 phosphate",
    "f 6 p": "fructose 6 phosphate",
    "g6p": "glucose 6 phosphate",
    "f6p": "fructose 6 phosphate",
    "3 pg": "3 phosphoglycerate",
    "3pg": "3 phosphoglycerate",
    "pep": "phosphoenolpyruvate",
    "pyr": "pyruvate",
    "lac": "lactate",
    "ala": "alanine",
    "asp": "aspartate",
    "cit": "citrate",
    "succ": "succinate",
    "mal": "malate",
    "accoa": "acetyl coa",
    "acetyl coenzyme a": "acetyl coa",
    "g 3 p": "glyceraldehyde 3 phosphate",
}


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    s = str(text).lower()
    s = re.sub(r"[-_./,;:'\"()\[\]]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for prefix in ("d ", "l ", "alpha ", "beta ", "gamma ", "dl ", "n ", "c "):
        s = s.replace(prefix, "")
    # apply common synonyms
    for k, v in SYNONYMS.items():
        s = s.replace(k, v)
    return s


def _name_score(query: str, candidate_name: str, candidate_id: str, candidate_formula: Optional[str] = None, query_formula: Optional[str] = None) -> float:
    q = _normalize(query)
    if not q:
        return 0.0
    c_name = _normalize(candidate_name)
    c_id = _normalize(candidate_id)

    if q == c_name or q == c_id:
        return 1.0
    if q in c_name or q in c_id:
        return 0.9

    q_words = set(q.split())
    if q_words.issubset(set(c_name.split())):
        return 0.8
    if q_words.issubset(set(c_id.split())):
        return 0.75

    if query_formula and candidate_formula and _normalize(query_formula) == _normalize(candidate_formula):
        return 0.85

    name_match = len(q_words & set(c_name.split()))
    id_match = len(q_words & set(c_id.split()))
    best = max(name_match, id_match)
    if best:
        return min(0.7, best / max(len(q_words), 1))
    return 0.0


def _feature_names(dataset: Any, feature_ids: List[str]) -> List[str]:
    meta = (dataset.feature_metadata or []) if hasattr(dataset, "feature_metadata") else []
    names = []
    for fid in feature_ids:
        name = fid
        for m in meta:
            if m.get("feature_id") == fid and (m.get("Name") or m.get("name")):
                name = m.get("Name") or m.get("name")
                break
        names.append(name)
    return names


def _feature_formulas(feature_ids: List[str], dataset: Any) -> List[Optional[str]]:
    if not dataset or not hasattr(dataset, "feature_metadata") or not dataset.feature_metadata:
        return [None] * len(feature_ids)
    meta = dataset.feature_metadata
    fid_to_formula = {}
    for i, m in enumerate(meta):
        fid = m.get("feature_id")
        if fid:
            fid_to_formula[fid] = m.get("formula") or m.get("Formula")
    return [fid_to_formula.get(fid) for fid in feature_ids]


def _match_features_to_nodes(feature_ids: List[str], feature_names: List[str], G: nx.DiGraph, dataset: Any = None) -> Dict[str, str]:
    """Map feature_id -> graph node id using name matching."""
    mapping = {}
    nodes = list(G.nodes(data=True))
    formulas = _feature_formulas(feature_ids, dataset)
    for fid, fname, fformula in zip(feature_ids, feature_names, formulas):
        q = str(fname) if fname else str(fid)
        best = None
        best_score = 0.35
        for nid, attrs in nodes:
            score = _name_score(
                q,
                attrs.get("name", ""),
                nid,
                attrs.get("formula"),
                fformula,
            )
            if score > best_score:
                best_score = score
                best = nid
        if best:
            mapping[fid] = best
    return mapping


def _build_manual_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    for src, tgt in FLUX_EDGES:
        G.add_edge(src, tgt)
    for n in G.nodes():
        G.nodes[n]["name"] = n
        G.nodes[n]["formula"] = ""
        G.nodes[n]["compartment"] = ""
    return G


# ---------------------------------------------------------------------------
# BiGG model client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=20)
def _get_bigg_model_sync(bigg_id: str) -> dict:
    with httpx.Client(timeout=120.0) as client:
        r = client.get(f"{BIGG_BASE}/models/{bigg_id}/download")
        r.raise_for_status()
        return r.json()


async def get_bigg_model(bigg_id: str) -> dict:
    return await asyncio.to_thread(_get_bigg_model_sync, bigg_id)


async def list_bigg_models(query: Optional[str] = None, limit: int = 20) -> List[dict]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{BIGG_BASE}/models")
        r.raise_for_status()
        data = r.json()
    models = data.get("results", [])
    if query:
        q = query.lower()
        models = [m for m in models if q in m.get("bigg_id", "").lower() or q in m.get("organism", "").lower()]
    return models[:limit]


def _model_metabolites_bigg(model_json: dict) -> Dict[str, dict]:
    return {m["id"]: m for m in model_json.get("metabolites", [])}


def _model_reactions_bigg(model_json: dict) -> List[dict]:
    return model_json.get("reactions", [])


def build_bigg_network(model_json: dict, measured_nodes: Optional[set] = None) -> nx.DiGraph:
    G = nx.DiGraph()
    mets = _model_metabolites_bigg(model_json)
    for nid, met in mets.items():
        if measured_nodes and nid not in measured_nodes:
            continue
        G.add_node(nid, name=met.get("name", ""), compartment=met.get("compartment", ""), formula=met.get("formula", ""))
    for rxn in _model_reactions_bigg(model_json):
        mets = rxn.get("metabolites", {})
        subs = [m for m, st in mets.items() if st < 0]
        prods = [m for m, st in mets.items() if st > 0]
        for s in subs:
            if measured_nodes and s not in measured_nodes:
                continue
            for t in prods:
                if measured_nodes and t not in measured_nodes:
                    continue
                G.add_edge(
                    s,
                    t,
                    reaction_id=rxn.get("id", ""),
                    name=rxn.get("name", ""),
                    subsystem=rxn.get("subsystem", ""),
                    stoich=max(1.0, abs(mets[s]) * abs(mets[t])),
                )
    return G


# ---------------------------------------------------------------------------
# Metabolic Atlas / SysBioChalmers GEM client
# ---------------------------------------------------------------------------

def _gem_yaml_loader():
    try:
        return yaml.CSafeLoader
    except Exception:
        return yaml.SafeLoader


@lru_cache(maxsize=10)
def _get_gem_model_sync(model_id: str) -> dict:
    model = next((m for m in GEM_MODELS if m["id"] == model_id), None)
    if not model:
        raise ValueError(f"GEM model {model_id} not found")
    url = f"{GITHUB_RAW}/{model['repo']}/main/{model['path']}"
    with httpx.Client(timeout=180.0) as client:
        r = client.get(url)
        r.raise_for_status()
        text = r.text
    data = yaml.load(text, Loader=_gem_yaml_loader())
    if isinstance(data, list):
        data = dict(data)
    return data


async def get_gem_model(model_id: str) -> dict:
    return await asyncio.to_thread(_get_gem_model_sync, model_id)


def list_gem_models(query: Optional[str] = None, limit: int = 20) -> List[dict]:
    models = GEM_MODELS
    if query:
        q = query.lower()
        models = [m for m in models if q in m["id"].lower() or q in m.get("organism", "").lower()]
    return models[:limit]


def _model_metabolites_gem(model_dict: dict) -> Dict[str, dict]:
    mets = model_dict.get("metabolites", [])
    if mets and isinstance(mets[0], (list, tuple)):
        mets = [dict(item) for item in mets]
    return {m["id"]: m for m in mets if m.get("id")}


def _model_reactions_gem(model_dict: dict) -> List[dict]:
    rxns = model_dict.get("reactions", [])
    if rxns and isinstance(rxns[0], (list, tuple)):
        rxns = [dict(item) for item in rxns]
    return rxns


def build_gem_network(model_dict: dict, measured_nodes: Optional[set] = None) -> nx.DiGraph:
    G = nx.DiGraph()
    mets = _model_metabolites_gem(model_dict)
    for nid, met in mets.items():
        if measured_nodes and nid not in measured_nodes:
            continue
        G.add_node(nid, name=met.get("name", ""), compartment=met.get("compartment", ""), formula=met.get("formula", ""))

    for rxn in _model_reactions_gem(model_dict):
        met_pairs = rxn.get("metabolites", [])
        if met_pairs and isinstance(met_pairs[0], (list, tuple)):
            met_dict = dict(met_pairs)
        else:
            met_dict = met_pairs
        subs = [m for m, st in met_dict.items() if st < 0]
        prods = [m for m, st in met_dict.items() if st > 0]
        subsystems = rxn.get("subsystem", [])
        if isinstance(subsystems, str):
            subsystems = [subsystems]
        subsystem = subsystems[0] if subsystems else ""
        for s in subs:
            if measured_nodes and s not in measured_nodes:
                continue
            for t in prods:
                if measured_nodes and t not in measured_nodes:
                    continue
                G.add_edge(
                    s,
                    t,
                    reaction_id=rxn.get("id", ""),
                    name=rxn.get("name", ""),
                    subsystem=subsystem,
                    stoich=max(1.0, abs(met_dict.get(s, 1)) * abs(met_dict.get(t, 1))),
                )
    return G


# ---------------------------------------------------------------------------
# Model loading dispatcher
# ---------------------------------------------------------------------------

async def load_network_for_isotope(
    map_source: Optional[str],
    map_id: Optional[str],
    feature_ids: List[str],
    feature_names: List[str],
    dataset: Any = None,
) -> Tuple[nx.DiGraph, Dict[str, str]]:
    """Return a graph of metabolites relevant to the measured features and a feature->node map."""
    if map_source == "bigg" and map_id:
        model = await get_bigg_model(map_id)
        mets = _model_metabolites_bigg(model)
    elif map_source == "gem" and map_id:
        model = await get_gem_model(map_id)
        mets = _model_metabolites_gem(model)
    else:
        mets = {}

    if mets:
        G_meta = nx.DiGraph()
        for nid, attrs in mets.items():
            G_meta.add_node(nid, **attrs)
        mapping = _match_features_to_nodes(feature_ids, feature_names, G_meta, dataset=dataset)
        measured = set(mapping.values())
        if map_source == "bigg":
            G = build_bigg_network(model, measured_nodes=measured)
        else:
            G = build_gem_network(model, measured_nodes=measured)
        return G, mapping

    G_full = _build_manual_graph()
    mapping = _match_features_to_nodes(feature_ids, feature_names, G_full, dataset=dataset)
    measured = set(mapping.values())
    G = G_full.subgraph(measured).copy() if measured else G_full.copy()
    return G, mapping


# ---------------------------------------------------------------------------
# Model summary / preview for the load endpoint
# ---------------------------------------------------------------------------

def _count_edges_bigg(model_json: dict) -> int:
    total = 0
    for rxn in _model_reactions_bigg(model_json):
        mets = rxn.get("metabolites", {})
        subs = [m for m, st in mets.items() if st < 0]
        prods = [m for m, st in mets.items() if st > 0]
        total += len(subs) * len(prods)
    return total


def _count_edges_gem(model_dict: dict) -> int:
    total = 0
    for rxn in _model_reactions_gem(model_dict):
        met_pairs = rxn.get("metabolites", [])
        if met_pairs and isinstance(met_pairs[0], (list, tuple)):
            met_dict = dict(met_pairs)
        else:
            met_dict = met_pairs
        subs = [m for m, st in met_dict.items() if st < 0]
        prods = [m for m, st in met_dict.items() if st > 0]
        total += len(subs) * len(prods)
    return total


def _sample_nodes(mets: Dict[str, dict], limit: int = 50) -> List[dict]:
    return [
        {"id": nid, "name": attrs.get("name", ""), "compartment": attrs.get("compartment", ""), "formula": attrs.get("formula", "")}
        for nid, attrs in list(mets.items())[:limit]
    ]


async def get_model_summary(source: str, model_id: str) -> Dict[str, Any]:
    if source == "bigg":
        model = await get_bigg_model(model_id)
        mets = _model_metabolites_bigg(model)
        edge_count = _count_edges_bigg(model)
        sample = _sample_nodes(mets)
    elif source == "gem":
        model = await get_gem_model(model_id)
        mets = _model_metabolites_gem(model)
        edge_count = _count_edges_gem(model)
        sample = _sample_nodes(mets)
    else:
        raise ValueError("source must be 'bigg' or 'gem'")
    return {
        "source": source,
        "model_id": model_id,
        "node_count": len(mets),
        "edge_count": edge_count,
        "sample_nodes": sample,
    }


# ---------------------------------------------------------------------------
# Graph modes and layout
# ---------------------------------------------------------------------------

def _assign_edge_weights(G: nx.DiGraph, mean_map: Dict[str, float], total_map: Dict[str, float], edge_weight: str) -> str:
    """Populate edge 'weight' attribute. Returns the name of the weight attribute ('weight')."""
    max_mean = max((v for v in mean_map.values() if math.isfinite(v)), default=1.0) or 1.0
    max_total = max((v for v in total_map.values() if math.isfinite(v)), default=1.0) or 1.0

    for u, v, data in G.edges(data=True):
        mean_u = mean_map.get(u, 0.0)
        mean_v = mean_map.get(v, 0.0)
        total_u = total_map.get(u, 0.0)
        total_v = total_map.get(v, 0.0)
        gradient = abs(mean_v - mean_u)
        avg_total = (total_u + total_v) / 2.0

        if edge_weight == "intensity":
            w = avg_total / max_total
        elif edge_weight == "flux":
            w = (gradient / max_mean) * (avg_total / max_total)
        elif edge_weight == "label_gradient":
            w = gradient / max_mean
        else:
            w = 1.0

        if not math.isfinite(w) or w <= 0:
            w = 0.01
        data["weight"] = w
    return "weight"


def _apply_graph_mode(
    G: nx.DiGraph,
    graph_mode: str,
    weight_attr: str,
    source: Optional[str],
    target: Optional[str],
    k: int,
) -> nx.DiGraph:
    """Filter/transform graph according to the selected Fluxer-style mode."""
    if graph_mode == "spanning_tree":
        if G.number_of_nodes() == 0:
            return G
        UG = G.to_undirected()
        for u, v, d in UG.edges(data=True):
            d["weight"] = d.get("weight", 1.0)
        try:
            T = nx.maximum_spanning_tree(UG, weight="weight")
        except Exception:
            T = nx.minimum_spanning_tree(UG, weight="weight")
        return nx.DiGraph(T)

    if graph_mode == "k_shortest_paths":
        nodes = list(G.nodes())
        if source and source in G and target and target in G:
            src, tgt = source, target
        elif nodes:
            src = nodes[0]
            tgt = nodes[-1] if len(nodes) > 1 else nodes[0]
        else:
            return G
        try:
            paths = list(nx.shortest_simple_paths(G, src, tgt, weight=weight_attr))
            k = max(1, min(k, len(paths)))
            selected = paths[:k]
            H = nx.DiGraph()
            H.add_nodes_from([(n, G.nodes[n]) for n in G.nodes() if any(n in p for p in selected)])
            colors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6"]
            for i, path in enumerate(selected):
                for j in range(len(path) - 1):
                    u, v = path[j], path[j + 1]
                    if H.has_edge(u, v):
                        existing = H[u][v].get("path_indices", [])
                        H[u][v]["path_indices"] = existing + [i]
                        H[u][v]["color"] = colors[existing[0] % len(colors)] if existing else colors[i % len(colors)]
                    else:
                        H.add_edge(u, v, **G[u][v])
                        H[u][v]["path_indices"] = [i]
                        H[u][v]["color"] = colors[i % len(colors)]
            return H
        except Exception:
            return G

    if graph_mode == "bipartite":
        return _bipartite_reaction_graph(G)

    # "full" / "complete" (complete reaction network)
    return G


def _bipartite_reaction_graph(G: nx.DiGraph) -> nx.DiGraph:
    """Convert a metabolite-only reaction graph into a bipartite metabolite-reaction graph."""
    B = nx.DiGraph()
    for n, attrs in G.nodes(data=True):
        B.add_node(n, **attrs, bipartite=0, node_type="metabolite")
    # create reaction nodes from edge attributes
    seen = {}
    for u, v, data in G.edges(data=True):
        rxn_id = data.get("reaction_id") or f"{u}_{v}"
        rxn_name = data.get("name") or rxn_id
        if rxn_id not in seen:
            seen[rxn_id] = f"rxn_{rxn_id}"
            B.add_node(seen[rxn_id], name=rxn_name, bipartite=1, node_type="reaction", subsystem=data.get("subsystem", ""))
        B.add_edge(u, seen[rxn_id], **data)
        B.add_edge(seen[rxn_id], v, **data)
    return B


def _node_pathway(n: str, attrs: dict) -> str:
    if attrs.get("name") in PATHWAY_LAYOUT:
        return PATHWAY_LAYOUT[attrs["name"]][2]
    if attrs.get("name") in PATHWAY_LAYOUT:
        return PATHWAY_LAYOUT[attrs["name"]][2]
    sub = attrs.get("subsystem", "")
    if isinstance(sub, list) and sub:
        sub = sub[0]
    if sub:
        return sub
    return "Other"


def _compute_positions(G: nx.DiGraph, layout: str) -> Dict[str, Tuple[float, float]]:
    if layout == "curated":
        return _curated_layout(G)
    if layout == "circular":
        return nx.circular_layout(G)
    if layout == "kamada_kawai":
        return nx.kamada_kawai_layout(G)
    if layout == "spring":
        return nx.spring_layout(G, seed=42, k=2.0, iterations=300)
    if layout == "shell":
        return nx.shell_layout(G)
    # default spring
    return nx.spring_layout(G, seed=42, k=2.0, iterations=300)


def _curated_layout(G: nx.DiGraph) -> Dict[str, Tuple[float, float]]:
    """Cluster nodes by pathway and place clusters on a circle, with preset positions for central-carbon metabolites."""
    groups: Dict[str, List[str]] = {}
    pos: Dict[str, Tuple[float, float]] = {}
    presets = {n: (x, y) for n, (x, y, _) in PATHWAY_LAYOUT.items()}

    for n, attrs in G.nodes(data=True):
        name = attrs.get("name", n)
        if name in presets:
            pos[n] = presets[name]
        pway = _node_pathway(n, attrs)
        groups.setdefault(pway, []).append(n)

    if not groups:
        return pos

    # Assign cluster centers around a circle.
    pathways = sorted(groups.keys())
    radius = 1.6
    centers = {}
    for i, p in enumerate(pathways):
        angle = 2 * math.pi * i / len(pathways) - math.pi / 2
        centers[p] = (math.cos(angle) * radius, math.sin(angle) * radius)

    for p, nodes in groups.items():
        cx, cy = centers[p]
        sub = G.subgraph(nodes)
        local_pos = nx.spring_layout(sub, seed=42, k=0.6, iterations=80)
        xs = [v[0] for v in local_pos.values()]
        ys = [v[1] for v in local_pos.values()]
        minx, maxx = (min(xs), max(xs)) if xs else (0, 1)
        miny, maxy = (min(ys), max(ys)) if ys else (0, 1)
        sx = maxx - minx if maxx > minx else 1.0
        sy = maxy - miny if maxy > miny else 1.0
        for n, (x, y) in local_pos.items():
            if n not in pos:
                pos[n] = (cx + 0.45 * ((x - minx) / sx - 0.5), cy + 0.45 * ((y - miny) / sy - 0.5))
    return pos


# ---------------------------------------------------------------------------
# Plotly figure builder
# ---------------------------------------------------------------------------

def _make_plotly_figure(
    G: nx.DiGraph,
    pos: Dict[str, Tuple[float, float]],
    mean_map: Dict[str, float],
    total_map: Dict[str, float],
    feature_to_node: Dict[str, str],
    node_to_feature: Dict[str, str],
    graph_mode: str,
    edge_weight: str,
    title: str,
    style: str = "classic",
) -> dict:
    style_cfg = FLUX_STYLES.get(style, FLUX_STYLES["classic"])
    max_mean = max((v for v in mean_map.values() if math.isfinite(v)), default=1.0) or 1.0
    max_total = max((v for v in total_map.values() if math.isfinite(v)), default=1.0) or 1.0

    node_x, node_y, node_text, node_color, node_size, node_line_color = [], [], [], [], [], []
    for n in G.nodes():
        x, y = pos.get(n, (0, 0))
        node_x.append(x)
        node_y.append(y)
        name = G.nodes[n].get("name", n)
        feature = node_to_feature.get(n, "")
        label = name if name != n else n
        if feature and feature != label:
            label = f"{label} ({feature})"
        node_text.append(label)
        node_color.append(mean_map.get(n, 0.0))
        node_size.append(12 + 28 * (total_map.get(n, 0.0) / max_total))
        pway = _node_pathway(n, G.nodes[n])
        node_line_color.append(PATHWAY_COLORS.get(pway, PATHWAY_COLORS["Other"]))

    edge_traces = []
    annotations = []
    for src, tgt, data in G.edges(data=True):
        x0, y0 = pos.get(src, (0, 0))
        x1, y1 = pos.get(tgt, (0, 0))
        if x0 is None or y0 is None or x1 is None or y1 is None:
            continue

        mean_src = mean_map.get(src, 0.0)
        mean_tgt = mean_map.get(tgt, 0.0)
        gradient = mean_tgt - mean_src

        if graph_mode == "k_shortest_paths" and "color" in data:
            color = data["color"]
        else:
            color = style_cfg["edge_positive"] if gradient >= 0 else style_cfg["edge_negative"]

        w = data.get("weight", 1.0)
        if edge_weight == "uniform":
            width = 1.5
        else:
            width = 1.0 + style_cfg["edge_width_factor"] * min(w, 1.0)

        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="text",
                text=f"{src} → {tgt}<br>Δ mean labels: {gradient:.3f}<br>weight: {w:.3f}",
                showlegend=False,
            )
        )

        if style_cfg["annotations"]:
            annotations.append(
                dict(
                    x=x0 + 0.88 * (x1 - x0),
                    y=y0 + 0.88 * (y1 - y0),
                    ax=x0 + 0.12 * (x1 - x0),
                    ay=y0 + 0.12 * (y1 - y0),
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

    marker_line = (
        dict(width=style_cfg["node_line_width"], color=node_line_color)
        if style_cfg["marker_line"]
        else dict(width=0)
    )

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color=style_cfg["text_color"]),
        marker=dict(
            showscale=True,
            colorscale=style_cfg["colorscale"],
            color=node_color,
            size=node_size,
            colorbar=dict(
                title=dict(text="Mean<br>labeled<br>atoms", font=dict(color=style_cfg["text_color"])),
                thickness=12,
                x=1.06,
                tickfont=dict(color=style_cfg["text_color"]),
            ),
            line=marker_line,
        ),
        hovertemplate="%{text}<br>Mean labeled atoms: %{marker.color:.3f}<extra></extra>",
        showlegend=False,
    )

    # Build a custom legend for pathways by adding invisible traces.
    legend_traces = []
    for pway, color in sorted(PATHWAY_COLORS.items()):
        if any(_node_pathway(n, G.nodes[n]) == pway for n in G.nodes()):
            legend_traces.append(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(size=10, color=color, symbol="circle", line=dict(width=0)),
                    name=pway,
                    showlegend=True,
                )
            )

    xaxis = dict(
        showgrid=style_cfg["grid_color"] is not None,
        gridcolor=style_cfg["grid_color"],
        zeroline=False,
        showticklabels=False,
        scaleanchor="y",
    )
    yaxis = dict(
        showgrid=style_cfg["grid_color"] is not None,
        gridcolor=style_cfg["grid_color"],
        zeroline=False,
        showticklabels=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace] + legend_traces)
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(color=style_cfg["text_color"])),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor=style_cfg["legend_bgcolor"],
            font=dict(size=9, color=style_cfg["legend_font_color"]),
        ),
        autosize=True,
        hovermode="closest",
        xaxis=xaxis,
        yaxis=yaxis,
        margin=dict(l=60, r=120, t=100, b=60),
        plot_bgcolor=style_cfg["plot_bgcolor"],
        paper_bgcolor=style_cfg["paper_bgcolor"],
        annotations=annotations,
        font=dict(color=style_cfg["text_color"]),
    )
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

async def build_flux_map(
    dataset: Any,
    feature_ids: List[str],
    mean_labeled_atoms: pd.Series,
    total_intensity: pd.Series,
    options: Optional[Dict[str, Any]] = None,
) -> Optional[dict]:
    options = options or {}
    layout = options.get("layout", "spring")
    graph_mode = options.get("graph_mode", "full")
    edge_weight = options.get("edge_weight", "label_gradient")
    k = int(options.get("k", 3))
    source_feature = options.get("source_node")
    target_feature = options.get("target_node")
    map_source = options.get("map_source")
    map_id = options.get("map_id")
    title = options.get("title", "Flux map")
    style = options.get("style", "classic")

    feature_names = _feature_names(dataset, feature_ids)

    G, feature_to_node = await load_network_for_isotope(map_source, map_id, feature_ids, feature_names, dataset=dataset)
    if G.number_of_nodes() == 0:
        return None

    # Build value maps keyed by graph node id.
    node_to_feature = {v: k for k, v in feature_to_node.items()}
    mean_map = {}
    total_map = {}
    for i, fid in enumerate(feature_ids):
        nid = feature_to_node.get(fid)
        if not nid:
            continue
        mean_map[nid] = float(mean_labeled_atoms.iloc[i]) if i < len(mean_labeled_atoms) else 0.0
        total_map[nid] = float(total_intensity.iloc[i]) if i < len(total_intensity) else 0.0

    # For unmapped nodes (model neighbors not measured) use zero.
    for n in G.nodes():
        mean_map.setdefault(n, 0.0)
        total_map.setdefault(n, 0.0)

    weight_attr = _assign_edge_weights(G, mean_map, total_map, edge_weight)

    source_node = feature_to_node.get(source_feature) if source_feature else None
    target_node = feature_to_node.get(target_feature) if target_feature else None
    G = _apply_graph_mode(G, graph_mode, weight_attr, source_node, target_node, k)

    if G.number_of_nodes() == 0:
        return None

    pos = _compute_positions(G, layout)
    return _make_plotly_figure(
        G,
        pos,
        mean_map,
        total_map,
        feature_to_node,
        node_to_feature,
        graph_mode,
        edge_weight,
        title,
        style,
    )

import asyncio
import io
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
import logging

logger = logging.getLogger(__name__)


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
    "Glycerophospholipid": "#3b82f6",
    "Sphingolipid": "#a855f7",
    "Neutral lipid": "#f59e0b",
    "Sterol lipid": "#ec4899",
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
        "edge_positive": "#38bdf8",
        "edge_negative": "#f472b6",
        "edge_width_factor": 3.0,
        "colorscale": "Cividis",
        "paper_bgcolor": "#1e293b",
        "plot_bgcolor": "#1e293b",
        "text_color": "#f8fafc",
        "legend_font_color": "#f8fafc",
        "legend_bgcolor": "rgba(30,41,59,0.7)",
        "marker_line": False,
        "annotations": True,
        "grid_color": "#334155",
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
    "fluxer": {
        "node_line_width": 1,
        "edge_positive": "#0ea5e9",
        "edge_negative": "#f97316",
        "edge_width_factor": 4.0,
        "colorscale": "YlOrRd",
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "text_color": "#1e293b",
        "legend_font_color": "#334155",
        "legend_bgcolor": "rgba(255,255,255,0.9)",
        "marker_line": False,
        "annotations": True,
        "grid_color": "#e2e8f0",
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
    # Keep plus signs in labels (M+1) and slashes in lipid names, but remove other punctuation.
    s = re.sub(r"[-_.,;:'\"()\[\]]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Apply whole-word synonyms (e.g. g6p -> glucose 6 phosphate).
    for k, v in SYNONYMS.items():
        pattern = r"\b" + re.escape(k) + r"\b"
        s = re.sub(pattern, v, s)
    # Remove stereochemistry / anomer prefixes only when they appear at the start of the string.
    for prefix in ("d ", "l ", "alpha ", "beta ", "gamma ", "dl ", "n "):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
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
    # Ignore pure-numeric tokens (e.g. 34:1 -> "34" "1") so lipid carbon counts do not match central-carbon metabolites.
    q_alpha = {w for w in q_words if any(c.isalpha() for c in w)}
    if not q_alpha:
        return 0.0

    c_name_words = set(c_name.split())
    c_id_words = set(c_id.split())
    if q_alpha.issubset(c_name_words):
        return 0.8
    if q_alpha.issubset(c_id_words):
        return 0.75

    if query_formula and candidate_formula and _normalize(query_formula) == _normalize(candidate_formula):
        return 0.85

    name_match = len(q_alpha & c_name_words)
    id_match = len(q_alpha & c_id_words)
    best = max(name_match, id_match)
    if best:
        return min(0.7, best / max(len(q_alpha), 1))
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
# Lipid graph builder
# ---------------------------------------------------------------------------

LIPID_CLASS_NAMES = {
    "LPC", "LPE", "LPG", "LPS", "LPI", "LPA",
    "PC", "PE", "PG", "PS", "PI", "PA",
    "SM", "Cer", "HexCer", "LacCer",
    "DAG", "DG", "TAG", "TG", "MG", "MAG",
    "CE", "CL", "BMP",
}

LIPID_SUPERCLASS = {
    "LPC": "Glycerophospholipid", "LPE": "Glycerophospholipid", "LPG": "Glycerophospholipid",
    "LPS": "Glycerophospholipid", "LPI": "Glycerophospholipid", "LPA": "Glycerophospholipid",
    "PC": "Glycerophospholipid", "PE": "Glycerophospholipid", "PG": "Glycerophospholipid",
    "PS": "Glycerophospholipid", "PI": "Glycerophospholipid", "PA": "Glycerophospholipid",
    "BMP": "Glycerophospholipid", "CL": "Glycerophospholipid",
    "SM": "Sphingolipid", "Cer": "Sphingolipid", "HexCer": "Sphingolipid", "LacCer": "Sphingolipid",
    "DAG": "Neutral lipid", "DG": "Neutral lipid", "TAG": "Neutral lipid", "TG": "Neutral lipid",
    "MG": "Neutral lipid", "MAG": "Neutral lipid", "CE": "Sterol lipid",
}

LIPID_CLASS_TRANSITIONS = {
    "PA": ["DAG", "PC", "PE", "PI", "PS", "PG"],
    "DAG": ["PC", "PE", "PA", "TAG", "MG"],
    "PC": ["LPC", "PE", "PS", "SM"],
    "PE": ["PC", "PS", "LPE", "DAG"],
    "PS": ["PE", "PC"],
    "PI": ["PA", "DAG"],
    "PG": ["LPG", "CL", "PA"],
    "CL": ["PG"],
    "LPC": ["PC"],
    "LPE": ["PE"],
    "LPG": ["PG"],
    "LPS": ["PS"],
    "LPI": ["PI"],
    "LPA": ["PA"],
    "MG": ["DAG"],
    "MAG": ["DAG"],
    "TAG": ["DAG"],
    "TG": ["DAG"],
    "SM": ["Cer", "PC"],
    "Cer": ["SM", "HexCer"],
    "HexCer": ["LacCer"],
    "CE": [],
}

_LIPID_NAME_RE = re.compile(r"^(?P<class>[A-Za-z]+)\(?\s*(?P<chains>[^)]*)\)?$")
_LIPID_CHAIN_RE = re.compile(r"(?:[dOP]-?)?(?P<c>\d+):(?P<u>\d+)")


def _parse_lipid(name: str) -> Optional[dict]:
    m = _LIPID_NAME_RE.match(str(name).strip())
    if not m:
        return None
    cls = m.group("class")
    if cls not in LIPID_CLASS_NAMES:
        return None
    chains = []
    total_c = 0
    total_u = 0
    for cm in _LIPID_CHAIN_RE.finditer(m.group("chains")):
        c = int(cm.group("c"))
        u = int(cm.group("u"))
        chains.append((c, u))
        total_c += c
        total_u += u
    return {
        "class": cls,
        "chains": chains,
        "total_c": total_c,
        "total_u": total_u,
        "superclass": LIPID_SUPERCLASS.get(cls, "Other"),
    }


def _looks_like_lipid(name: str) -> bool:
    return _parse_lipid(name) is not None


def _detect_lipid_dataset(feature_names: List[str], threshold: float = 0.5) -> bool:
    if not feature_names:
        return False
    n_lipids = sum(1 for n in feature_names if _looks_like_lipid(n))
    return n_lipids / len(feature_names) >= threshold


def _build_lipid_graph(feature_ids: List[str], feature_names: List[str], formulas: List[Optional[str]]) -> nx.DiGraph:
    """Build a directed graph of measured lipids using curated class transitions and acyl-chain edits."""
    G = nx.DiGraph()
    parsed: Dict[str, dict] = {}
    key_to_fid: Dict[str, str] = {}

    for fid, name, formula in zip(feature_ids, feature_names, formulas):
        p = _parse_lipid(name)
        if not p:
            continue
        key = str(name)
        parsed[key] = p
        key_to_fid[key] = fid
        G.add_node(
            key,
            name=key,
            formula=formula or "",
            compartment="",
            lipid_class=p["class"],
            pathway=p["superclass"],
            total_c=p["total_c"],
            total_u=p["total_u"],
        )

    # Class transitions that preserve total acyl composition.
    composition_index: Dict[Tuple[str, int, int], List[str]] = {}
    for key, p in parsed.items():
        composition_index.setdefault((p["class"], p["total_c"], p["total_u"]), []).append(key)

    for (cls, c, u), nodes in composition_index.items():
        for target_cls in LIPID_CLASS_TRANSITIONS.get(cls, []):
            targets = composition_index.get((target_cls, c, u), [])
            for src in nodes:
                for tgt in targets:
                    if src == tgt:
                        continue
                    G.add_edge(src, tgt, reaction=f"{cls} → {target_cls}", subsystem="Lipid metabolism")

    # Acyl-chain modification edges within the same class (elongation/desaturation).
    ACYL_EDITS = [(2, 0), (0, 1), (2, 1), (-2, 0), (0, -1), (-2, -1)]
    for key, p in parsed.items():
        cls = p["class"]
        for dc, du in ACYL_EDITS:
            tgt_c = p["total_c"] + dc
            tgt_u = p["total_u"] + du
            if tgt_c < 2 or tgt_u < 0:
                continue
            targets = composition_index.get((cls, tgt_c, tgt_u), [])
            for tgt in targets:
                if key == tgt:
                    continue
                label = f"{dc:+d}C,{du:+d}U"
                if not G.has_edge(key, tgt):
                    G.add_edge(key, tgt, reaction=f"Acyl edit ({label})", subsystem="Fatty acid metabolism")

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
    except Exception as _exc:
        logger.exception("Unexpected error")
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
    # Detect lipid datasets early so we can build a lipid-specific graph instead of forcing
    # lipid names (e.g. PC(34:1)) onto the generic central-carbon manual graph.
    is_lipid_dataset = (
        getattr(dataset, "feature_type", None) == "lipid"
        or _detect_lipid_dataset(feature_names)
    )

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
        if not measured and is_lipid_dataset:
            # If the model does not contain the measured lipids, fall back to the lipid graph.
            formulas = _feature_formulas(feature_ids, dataset)
            G = _build_lipid_graph(feature_ids, feature_names, formulas)
            mapping = {fid: key for fid, key in zip(feature_ids, feature_names) if key in G}
            return G, mapping
        if map_source == "bigg":
            G = build_bigg_network(model, measured_nodes=measured)
        else:
            G = build_gem_network(model, measured_nodes=measured)
        return G, mapping

    if is_lipid_dataset:
        formulas = _feature_formulas(feature_ids, dataset)
        G = _build_lipid_graph(feature_ids, feature_names, formulas)
        mapping = {fid: key for fid, key in zip(feature_ids, feature_names) if key in G}
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
        except Exception as _exc:
            logger.exception("Unexpected error")
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
        except Exception as _exc:
            logger.exception("Unexpected error")
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
    # If an explicit pathway / superclass has been assigned (e.g. lipid graph), use it.
    pway = attrs.get("pathway") or attrs.get("lipid_superclass")
    if pway:
        return pway
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
        try:
            return nx.kamada_kawai_layout(G)
        except Exception:
            return nx.spring_layout(G, seed=42, k=2.0, iterations=300)
    if layout == "spring":
        return nx.spring_layout(G, seed=42, k=2.0, iterations=300)
    if layout == "fruchterman_reingold":
        try:
            return nx.fruchterman_reingold_layout(G, seed=42, iterations=300)
        except Exception:
            return nx.spring_layout(G, seed=42, k=2.0, iterations=300)
    if layout == "shell":
        try:
            return nx.shell_layout(G)
        except Exception:
            return nx.spring_layout(G, seed=42, k=2.0, iterations=300)
    if layout == "grid":
        return _grid_layout(G)
    # default spring
    return nx.spring_layout(G, seed=42, k=2.0, iterations=300)


def _grid_layout(G: nx.DiGraph) -> Dict[str, Tuple[float, float]]:
    """Place nodes on a square grid ordered by pathway and name for a predictable layout."""
    nodes = sorted(G.nodes(), key=lambda n: (_node_pathway(n, G.nodes[n]), str(n)))
    cols = max(1, math.ceil(math.sqrt(len(nodes))))
    pos = {}
    for i, n in enumerate(nodes):
        x = (i % cols) / max(cols - 1, 1)
        y = 1.0 - (i // cols) / max(math.ceil(len(nodes) / cols) - 1, 1)
        pos[n] = (x, y)
    return pos


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
# Escher map builder
# ---------------------------------------------------------------------------


# Mapping from common human-readable metabolite names to cytosolic BiGG IDs.
_ESCHER_NAME_TO_BIGG: Dict[str, str] = {
    "glucose 6 phosphate": "g6p_c",
    "glucose-6-phosphate": "g6p_c",
    "g6p": "g6p_c",
    "fructose 6 phosphate": "f6p_c",
    "fructose-6-phosphate": "f6p_c",
    "f6p": "f6p_c",
    "3 phosphoglycerate": "3pg_c",
    "3-phosphoglycerate": "3pg_c",
    "3pg": "3pg_c",
    "phosphoglycerate": "3pg_c",
    "phosphoenolpyruvate": "pep_c",
    "pep": "pep_c",
    "pyruvate": "pyr_c",
    "pyr": "pyr_c",
    "acetyl coa": "accoa_c",
    "acetyl-coa": "accoa_c",
    "acetyl coenzyme a": "accoa_c",
    "citrate": "cit_c",
    "cit": "cit_c",
    "alpha ketoglutarate": "akg_c",
    "a ketoglutarate": "akg_c",
    "ketoglutarate": "akg_c",
    "akg": "akg_c",
    "2 oxoglutarate": "akg_c",
    "succinate": "succ_c",
    "succ": "succ_c",
    "malate": "mal__L_c",
    "mal": "mal__L_c",
    "l malate": "mal__L_c",
    "aspartate": "asp__L_c",
    "asp": "asp__L_c",
    "l aspartate": "asp__L_c",
    "alanine": "ala__L_c",
    "ala": "ala__L_c",
    "l alanine": "ala__L_c",
    "lactate": "lac__L_c",
    "lac": "lac__L_c",
    "l lactate": "lac__L_c",
}

_BIGG_ID_RE = re.compile(r"^[a-z][a-z0-9_]*_[a-z]$")


def _normalize_met_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().replace("-", " ").replace("_", " ")).strip()


def _node_to_bigg(name: str) -> Optional[str]:
    """Convert a feature/node name to a cytosolic BiGG ID when possible."""
    if _BIGG_ID_RE.match(name):
        return name
    norm = _normalize_met_name(name)
    return _ESCHER_NAME_TO_BIGG.get(norm)


def _bigg_base(bigg_id: str) -> str:
    """Return the metabolite base name without the one-letter compartment suffix."""
    if not bigg_id:
        return ""
    return bigg_id.rsplit("_", 1)[0] if "_" in bigg_id else bigg_id


def _node_to_bigg_candidates(name: str, map_bigg_ids: set) -> List[str]:
    """Return all BiGG IDs in the map that match this feature (any compartment)."""
    if _BIGG_ID_RE.match(name) and name in map_bigg_ids:
        return [name]
    canonical = _node_to_bigg(name)
    if not canonical:
        return []
    base = _bigg_base(canonical)
    return [b for b in map_bigg_ids if _bigg_base(b).lower() == base.lower()]


def _pick_escher_map(mean_map: Dict[str, float], options: Dict[str, Any]) -> Optional[str]:
    """Choose a curated Escher map based on the selected model/organism or the data."""
    explicit = options.get("map_name")
    if explicit:
        return explicit
    map_id = options.get("map_id")
    organism = (options.get("map_organism") or "").lower()
    if map_id:
        if map_id == "e_coli_core":
            return "e_coli_core.Core metabolism"
        if map_id in ("iJO1366",):
            return "iJO1366.Central metabolism"
    if "sapiens" in organism or "homo" in organism:
        return "RECON1.Glycolysis TCA PPP"
    if "coli" in organism or "escherich" in organism:
        return "e_coli_core.Core metabolism"
    if "cerevisiae" in organism or "yeast" in organism or "saccharomyces" in organism:
        return "iMM904.Central carbon metabolism"
    # Fallback: if the measured nodes look like central carbon, use the human map.
    bigg_ids = {_node_to_bigg(n) for n in mean_map.keys()}
    if "g6p_c" in bigg_ids or "pyr_c" in bigg_ids or "cit_c" in bigg_ids:
        return "RECON1.Glycolysis TCA PPP"
    return None


def _escher_css_injection(html: str) -> str:
    css = """
    <style>
      html,body{height:100%;margin:0;background:#ffffff;}
      .map-menu,.menu-bar,.dropdown,.dropdownButton,.map-tools-container,.search-menu-container,.search-menu-container-inline,.button-panel,.full-screen-button,.notification-container,#status,.logo-container{display:none !important;}
      .escher-container .scale-legend{right:10px !important;bottom:10px !important;background:rgba(255,255,255,0.9) !important;border:1px solid #e2e8f0 !important;border-radius:0.5rem !important;padding:6px !important;}
      .metabolite-node circle{stroke:#475569;stroke-width:1.5px;}
      .reaction{stroke-linecap:round;}
      .label{fill:#1e293b !important;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif !important;}
    </style>
    """
    return html.replace("</head>", f"{css}</head>")


def _build_escher_html(builder: Any, title: str) -> dict:
    """Save an Escher Builder to a temporary HTML file and inject custom CSS."""
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        builder.save_html(path)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    html = _escher_css_injection(html)
    return {
        "type": "escher",
        "html": html,
        "data": [],
        "layout": {"title": {"text": title, "x": 0.5}},
    }


def _build_curated_escher_map(mean_map: Dict[str, float], title: str, map_name: str, show_labels: bool = False) -> Optional[dict]:
    """Render the measured data on a curated Escher map with a modern color scale."""
    try:
        import escher
        import escher.plots
    except Exception as _exc:
        logger.exception("Unexpected error")
        return None

    try:
        map_json = escher.plots.map_json_for_name(map_name)
    except Exception as _exc:
        logger.exception("Unexpected error")
        return None

    try:
        data = json.loads(map_json)
        if not isinstance(data, list) or len(data) < 2:
            return None
        escher_map = data[1]
    except Exception as _exc:
        logger.exception("Unexpected error")
        return None

    nodes = escher_map.get("nodes", {})
    reactions = escher_map.get("reactions", {})
    map_bigg_ids = {
        str(attrs.get("bigg_id"))
        for attrs in nodes.values()
        if attrs.get("node_type") == "metabolite" and attrs.get("bigg_id")
    }

    metabolite_data: Dict[str, float] = {}
    for nid, value in mean_map.items():
        for bigg in _node_to_bigg_candidates(nid, map_bigg_ids):
            metabolite_data[bigg] = float(value)

    if not metabolite_data:
        return None

    reaction_data: Dict[str, float] = {}
    for rxn_id, rxn in reactions.items():
        mets = rxn.get("metabolites", [])
        values = [metabolite_data.get(str(m.get("bigg_id"))) for m in mets if m.get("bigg_id") in metabolite_data]
        values = [v for v in values if v is not None and math.isfinite(v)]
        if values:
            reaction_value = max(values) - min(values)
            key = rxn.get("bigg_id") or rxn_id
            reaction_data[str(key)] = float(reaction_value)

    builder = escher.Builder(
        map_json=map_json,
        metabolite_data=metabolite_data,
        reaction_data=reaction_data,
        metabolite_scale_preset="WhYlRd",
        reaction_scale_preset="WhYlRd",
        metabolite_no_data_color="#94a3b8",
        metabolite_no_data_size=9,
        reaction_no_data_color="#94a3b8",
        hide_all_labels=not show_labels,
        identifiers_on_map="name" if show_labels else "bigg_id",
        enable_editing=False,
        enable_keys=False,
        enable_tooltips=False,
        scroll_behavior="none",
        height=600,
    )

    return _build_escher_html(builder, title)


def _build_manual_escher_map(
    G: nx.DiGraph,
    pos: Dict[str, Tuple[float, float]],
    mean_map: Dict[str, float],
    total_map: Dict[str, float],
    title: str,
    show_labels: bool = False,
) -> Optional[dict]:
    """Fallback: build a custom Escher map from the computed graph layout."""
    try:
        import escher
    except Exception as _exc:
        logger.exception("Unexpected error")
        return None

    import os
    import tempfile

    scale = 600
    offset = 2.0
    node_to_id: Dict[str, str] = {}
    nodes: Dict[str, Any] = {}
    for i, n in enumerate(G.nodes(), start=1):
        nid = str(i)
        node_to_id[n] = nid
        x, y = pos.get(n, (0, 0))
        nodes[nid] = {
            "x": int((x + offset) * scale),
            "y": int((y + offset) * scale),
            "node_type": "metabolite",
            "name": str(n),
            "bigg_id": str(n),
            "node_is_primary": True,
            "label_x": int((x + offset) * scale),
            "label_y": int((y + offset) * scale) - 25,
        }

    metabolite_data: Dict[str, float] = {str(n): float(mean_map.get(n, 0.0)) for n in G.nodes()}
    reaction_data: Dict[str, float] = {}
    reactions: Dict[str, Any] = {}

    counter = len(nodes) + 100
    for src, tgt, data in G.edges(data=True):
        weight = float(data.get("weight", 1.0))
        reaction_id = f"{src}_to_{tgt}"
        reaction_data[reaction_id] = weight

        mid_id = str(counter)
        counter += 1
        nodes[mid_id] = {
            "x": int(((pos.get(src, (0, 0))[0] + pos.get(tgt, (0, 0))[0]) / 2 + offset) * scale),
            "y": int(((pos.get(src, (0, 0))[1] + pos.get(tgt, (0, 0))[1]) / 2 + offset) * scale),
            "node_type": "midmarker",
        }

        seg1 = str(counter)
        counter += 1
        seg2 = str(counter)
        counter += 1
        reactions[str(counter)] = {
            "name": f"{src} → {tgt}",
            "bigg_id": reaction_id,
            "metabolites": [
                {"coefficient": -1.0, "bigg_id": str(src)},
                {"coefficient": 1.0, "bigg_id": str(tgt)},
            ],
            "segments": {
                seg1: {"from_node_id": node_to_id[src], "to_node_id": mid_id, "b1": None, "b2": None},
                seg2: {"from_node_id": mid_id, "to_node_id": node_to_id[tgt], "b1": None, "b2": None},
            },
            "reversibility": False,
        }
        counter += 1

    xs = [n["x"] for n in nodes.values()]
    ys = [n["y"] for n in nodes.values()]
    min_x, max_x = min(xs) - 100, max(xs) + 100
    min_y, max_y = min(ys) - 100, max(ys) + 100
    header = {
        "map_name": title,
        "map_id": "isotope_flux_map",
        "map_description": "Isotope flux map from measured metabolites",
        "homepage": "",
        "schema": "https://escher.github.io/escher/jsonschema/1-0-0#",
    }
    escher_map = [header, {
        "nodes": nodes,
        "reactions": reactions,
        "canvas": {"x": min_x, "y": min_y, "height": max_y - min_y, "width": max_x - min_x},
        "text_labels": {},
    }]

    builder = escher.Builder(
        map_json=json.dumps(escher_map),
        metabolite_data=metabolite_data,
        reaction_data=reaction_data,
        metabolite_scale_preset="WhYlRd",
        reaction_scale_preset="WhYlRd",
        metabolite_no_data_color="#94a3b8",
        metabolite_no_data_size=9,
        reaction_no_data_color="#94a3b8",
        hide_all_labels=not show_labels,
        enable_editing=False,
        enable_keys=False,
        enable_tooltips=False,
        scroll_behavior="none",
        height=600,
    )

    return _build_escher_html(builder, title)


def _build_escher_map(
    G: nx.DiGraph,
    pos: Dict[str, Tuple[float, float]],
    mean_map: Dict[str, float],
    total_map: Dict[str, float],
    options: Dict[str, Any],
) -> Optional[dict]:
    """Build an Escher flux map, preferring a curated BiGG map when available."""
    title = options.get("title", "Flux map")
    show_labels = options.get("show_labels", False)
    map_name = _pick_escher_map(mean_map, options)
    if map_name:
        curated = _build_curated_escher_map(mean_map, title, map_name, show_labels=show_labels)
        if curated:
            return curated
    return _build_manual_escher_map(G, pos, mean_map, total_map, title, show_labels=show_labels)


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
    show_labels: bool = True,
) -> dict:
    style_cfg = FLUX_STYLES.get(style, FLUX_STYLES["classic"])
    max_mean = max((v for v in mean_map.values() if math.isfinite(v)), default=1.0) or 1.0
    max_total = max((v for v in total_map.values() if math.isfinite(v)), default=1.0) or 1.0

    node_x, node_y, node_text, node_color, node_size, node_line_color, node_custom = [], [], [], [], [], [], []
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
        # Scale node area by total intensity (sqrt) so large values do not dominate.
        size = 12 + 32 * math.sqrt(total_map.get(n, 0.0) / max_total) if max_total > 0 else 12
        node_size.append(size)
        pway = _node_pathway(n, G.nodes[n])
        node_line_color.append(PATHWAY_COLORS.get(pway, PATHWAY_COLORS["Other"]))
        formula = G.nodes[n].get("formula", "") or ""
        node_custom.append((name, formula, pway, total_map.get(n, 0.0)))

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

        reaction = data.get("reaction", f"{src} → {tgt}")
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="text",
                text=f"{src} → {tgt}<br>Reaction: {reaction}<br>Δ mean labels: {gradient:.3f}<br>weight: {w:.3f}",
                showlegend=False,
            )
        )

        if style_cfg["annotations"]:
            annotations.append(
                dict(
                    x=x1,
                    y=y1,
                    ax=x0,
                    ay=y0,
                    xref="x",
                    yref="y",
                    axref="x",
                    ayref="y",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1.2,
                    arrowwidth=max(1, width * 0.7),
                    arrowcolor=color,
                    standoff=0,
                    startstandoff=0,
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
        mode="markers+text" if show_labels else "markers",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color=style_cfg["text_color"]),
        customdata=node_custom,
        marker=dict(
            showscale=True,
            colorscale=style_cfg["colorscale"],
            color=node_color,
            size=node_size,
            sizemode="diameter",
            colorbar=dict(
                title=dict(text="Mean<br>labeled<br>atoms", font=dict(color=style_cfg["text_color"])),
                thickness=12,
                x=1.05,
                tickfont=dict(color=style_cfg["text_color"]),
            ),
            line=marker_line,
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Pathway: %{customdata[2]}<br>"
            "Formula: %{customdata[1]}<br>"
            "Total intensity: %{customdata[3]:.3e}<br>"
            "Mean labeled atoms: %{marker.color:.3f}<extra></extra>"
        ),
        showlegend=False,
    )

    # Build a custom legend for pathways by adding invisible traces.
    legend_traces = []
    present_pathways = {_node_pathway(n, G.nodes[n]) for n in G.nodes()}
    for pway in sorted(present_pathways):
        color = PATHWAY_COLORS.get(pway, PATHWAY_COLORS["Other"])
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
            y=1.08,
            xanchor="left",
            x=0,
            bgcolor=style_cfg["legend_bgcolor"],
            font=dict(size=9, color=style_cfg["legend_font_color"]),
        ),
        autosize=True,
        hovermode="closest",
        xaxis=xaxis,
        yaxis=yaxis,
        margin=dict(l=60, r=120, t=110, b=60),
        plot_bgcolor=style_cfg["plot_bgcolor"],
        paper_bgcolor=style_cfg["paper_bgcolor"],
        annotations=annotations,
        font=dict(color=style_cfg["text_color"]),
    )
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# GraphML export for Fluxer / external tools
# ---------------------------------------------------------------------------


def _sanitize_graphml_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return str(value)


def _graphml_for_network(
    G: nx.DiGraph,
    pos: Dict[str, Tuple[float, float]],
    mean_map: Dict[str, float],
    total_map: Dict[str, float],
    title: str = "Flux map",
) -> str:
    """Serialize the flux graph as GraphML so it can be opened in Fluxer, Cytoscape, etc."""
    H = nx.DiGraph()
    H.graph["name"] = title
    for n, attrs in G.nodes(data=True):
        node_attrs = {k: _sanitize_graphml_value(v) for k, v in attrs.items()}
        node_attrs["mean_labeled_atoms"] = _sanitize_graphml_value(mean_map.get(n, 0.0))
        node_attrs["total_intensity"] = _sanitize_graphml_value(total_map.get(n, 0.0))
        x, y = pos.get(n, (0.0, 0.0))
        node_attrs["x"] = float(x)
        node_attrs["y"] = float(y)
        H.add_node(str(n), **node_attrs)
    for u, v, attrs in G.edges(data=True):
        edge_attrs = {k: _sanitize_graphml_value(v) for k, v in attrs.items()}
        H.add_edge(str(u), str(v), **edge_attrs)
    buf = io.BytesIO()
    nx.write_graphml(H, buf)
    return buf.getvalue().decode("utf-8")


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

    # Default labels: off for Escher or very dense networks, on otherwise.
    show_labels = options.get("show_labels")
    if show_labels is None:
        show_labels = False if layout == "escher" or G.number_of_nodes() > 25 else True

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

    pos_layout = "curated" if layout == "escher" else layout
    pos = _compute_positions(G, pos_layout)

    graphml = _graphml_for_network(G, pos, mean_map, total_map, title=title)

    if layout == "escher":
        escher_options = {**options, "title": title, "show_labels": show_labels}
        fig = _build_escher_map(G, pos, mean_map, total_map, escher_options)
        if isinstance(fig, dict):
            fig["graphml"] = graphml
        return fig

    fig = _make_plotly_figure(
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
        show_labels=show_labels,
    )
    fig["graphml"] = graphml
    return fig

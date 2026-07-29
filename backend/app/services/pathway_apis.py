import re
import math
import asyncio
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote
import httpx
import numpy as np
from scipy import stats as scipy_stats
from statsmodels.stats.multitest import multipletests
from app.services.lipid_indices import _parse_feature


KEGG_BASE = "https://rest.kegg.jp"
REACTOME_BASE = "https://reactome.org/AnalysisService"
GPROFILER_BASE = "https://biit.cs.ut.ee/gprofiler/api/gost/profile"

GPROFILER_ORG_MAP = {
    "hsa": "hsapiens",
    "mmu": "mmusculus",
    "rno": "rnorvegicus",
    "dme": "dmelanogaster",
    "cel": "celegans",
    "sce": "scerevisiae",
    "ath": "athaliana",
    "eco": "ecoli_k12",
}
GPROFILER_TO_KEGG_ORG = {v: k for k, v in GPROFILER_ORG_MAP.items()}

# Curated lipid class -> common KEGG compound name used as a search fallback.
LIPID_CLASS_KEGG_NAME = {
    "PC": "Phosphatidylcholine",
    "PE": "Phosphatidylethanolamine",
    "PI": "Phosphatidylinositol",
    "PS": "Phosphatidylserine",
    "PG": "Phosphatidylglycerol",
    "PA": "Phosphatidic acid",
    "CL": "Cardiolipin",
    "SM": "Sphingomyelin",
    "Cer": "Ceramide",
    "HexCer": "Hexosylceramide",
    "Hex2Cer": "Hexosylceramide",
    "SHexCer": "Sulfatide",
    "CerP": "Ceramide phosphate",
    "TG": "Triacylglycerol",
    "DG": "Diacylglycerol",
    "MG": "Monoacylglycerol",
    "CE": "Cholesterol ester",
    "Chol": "Cholesterol",
    "CAR": "Acylcarnitine",
    "FA": "Fatty acid",
    "LPC": "Lysophosphatidylcholine",
    "LPE": "Lysophosphatidylethanolamine",
    "LPI": "Lysophosphatidylinositol",
    "LPS": "Lysophosphatidylserine",
    "LPG": "Lysophosphatidylglycerol",
    "LPA": "Lysophosphatidic acid",
}

# In-memory caches for repeated KEGG calls across requests
_CPD_RN_CACHE: Dict[str, List[str]] = {}
_RN_EC_CACHE: Dict[str, List[str]] = {}
_EC_GENE_CACHE: Dict[str, List[str]] = {}
_CPD_FIND_CACHE: Dict[str, Optional[str]] = {}
_CLASS_CPD_CACHE: Dict[str, Optional[str]] = {}
_class_lock = asyncio.Lock()


async def _kegg_text(client: httpx.AsyncClient, path: str, timeout: float = 20.0) -> str:
    try:
        r = await client.get(f"{KEGG_BASE}/{path}", timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def _parse_kegg_name(text: str, default: str = "") -> str:
    for line in text.splitlines():
        if line.startswith("NAME"):
            return line.split("NAME", 1)[1].strip().split(";")[0]
    return default


async def _kegg_total_compounds(client: httpx.AsyncClient) -> int:
    text = await _kegg_text(client, "info/compound")
    m = re.search(r"cpd\s+([0-9,]+)\s+entries", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 19000


async def _kegg_search_compound_name(client: httpx.AsyncClient, term: str) -> Optional[str]:
    if not term or not term.strip():
        return None
    text = await _kegg_text(client, f"find/compound/{_safe_url(term.strip())}")
    if not text:
        return None
    best = None
    for line in text.splitlines():
        parts = line.split("\t")
        if parts and (parts[0].startswith("cpd:") or re.fullmatch(r"C\d+", parts[0])):
            cpd = parts[0].replace("cpd:", "").strip()
            names = parts[1] if len(parts) > 1 else ""
            # prefer the generic exact-match compound
            if term.lower() in names.lower():
                best = cpd
                if names.lower().startswith(term.lower()):
                    return cpd
            if best is None:
                best = cpd
    return best


async def _kegg_find_compound(client: httpx.AsyncClient, name: str) -> Optional[str]:
    if not name or not str(name).strip():
        return None
    cache_key = name.strip()
    if cache_key in _CPD_FIND_CACHE:
        return _CPD_FIND_CACHE[cache_key]

    cls, _ = _parse_feature(cache_key)
    cls_name = LIPID_CLASS_KEGG_NAME.get(cls)
    # Lipid species with chain details: skip direct name (never a KEGG exact match) and use class mapping
    if cls_name and re.search(r"[(:]", cache_key):
        async with _class_lock:
            if cls_name not in _CLASS_CPD_CACHE:
                _CLASS_CPD_CACHE[cls_name] = await _kegg_search_compound_name(client, cls_name)
        result = _CLASS_CPD_CACHE.get(cls_name)
        _CPD_FIND_CACHE[cache_key] = result
        return result

    # Direct name search (metabolites, unknown lipids)
    result = await _kegg_search_compound_name(client, cache_key)
    # Fallback to class-level generic compound
    if not result and cls_name:
        async with _class_lock:
            if cls_name not in _CLASS_CPD_CACHE:
                _CLASS_CPD_CACHE[cls_name] = await _kegg_search_compound_name(client, cls_name)
        result = _CLASS_CPD_CACHE.get(cls_name)

    _CPD_FIND_CACHE[cache_key] = result
    return result


def _safe_url(value: str) -> str:
    return quote(value, safe="")


async def _map_features_to_kegg_cpds(client: httpx.AsyncClient, feature_names: List[str]) -> Dict[str, Optional[str]]:
    """Map each feature name to a KEGG compound id using the class fallback."""
    unique = sorted(set(feature_names))
    sem = asyncio.Semaphore(3)

    async def _wrapped(name: str):
        async with sem:
            return await _kegg_find_compound(client, name)

    tasks = [asyncio.create_task(_wrapped(n)) for n in unique]
    results = await asyncio.gather(*tasks)
    return dict(zip(unique, results))


async def _kegg_reactions_for_compound(client: httpx.AsyncClient, cpd_id: str) -> List[str]:
    if cpd_id in _CPD_RN_CACHE:
        return _CPD_RN_CACHE[cpd_id]
    text = await _kegg_text(client, f"link/rn/cpd:{cpd_id}")
    rns = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith("rn:"):
            rns.append(parts[1].replace("rn:", "").strip())
    _CPD_RN_CACHE[cpd_id] = rns
    return rns


async def _kegg_ecs_for_reaction(client: httpx.AsyncClient, rn_id: str) -> List[str]:
    if rn_id in _RN_EC_CACHE:
        return _RN_EC_CACHE[rn_id]
    text = await _kegg_text(client, f"link/enzyme/{rn_id}")
    ecs = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith("ec:"):
            ecs.append(parts[1].replace("ec:", "").strip())
    _RN_EC_CACHE[rn_id] = ecs
    return ecs


async def _kegg_genes_for_ec(client: httpx.AsyncClient, ec: str, organism: str) -> List[str]:
    cache_key = f"{organism}:{ec}"
    if cache_key in _EC_GENE_CACHE:
        return _EC_GENE_CACHE[cache_key]
    text = await _kegg_text(client, f"link/{organism}/ec:{ec}")
    genes = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith(f"{organism}:"):
            gene = parts[1].split(":")[-1].strip()
            if gene.isdigit():
                genes.append(gene)
    _EC_GENE_CACHE[cache_key] = genes
    return genes


async def _kegg_cpds_to_organism_genes(
    client: httpx.AsyncClient,
    cpd_ids: List[str],
    organism: str = "hsa",
    max_cpds: int = 8,
    max_rxns_per_cpd: int = 15,
    max_ecs_total: int = 30,
    max_genes: int = 500,
) -> List[str]:
    """Map KEGG compounds to organism Entrez gene ids via reaction -> EC -> gene."""
    seen_ecs: Set[str] = set()
    genes: Set[str] = set()
    sem = asyncio.Semaphore(5)

    for cpd_id in cpd_ids[:max_cpds]:
        rns = await _kegg_reactions_for_compound(client, cpd_id)
        for rn_id in rns[:max_rxns_per_cpd]:
            ecs = await _kegg_ecs_for_reaction(client, rn_id)
            for ec in ecs:
                if ec in seen_ecs or len(seen_ecs) >= max_ecs_total:
                    continue
                seen_ecs.add(ec)
                async with sem:
                    g = await _kegg_genes_for_ec(client, ec, organism)
                genes.update(g)
                if len(genes) >= max_genes:
                    return sorted(genes)[:max_genes]
    return sorted(genes)[:max_genes]


async def _kegg_pathways_for_compounds(client: httpx.AsyncClient, compound_ids: List[str]) -> Dict[str, List[str]]:
    """Return mapping pathway_id -> list of compound_ids."""
    if not compound_ids:
        return {}
    ids = "+".join(sorted(set(compound_ids)))
    text = await _kegg_text(client, f"link/pathway/{ids}")
    mapping: Dict[str, List[str]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        cpd = parts[0].replace("cpd:", "").strip()
        pathway = parts[1].replace("path:", "").strip()
        if pathway.startswith("map"):
            mapping.setdefault(pathway, []).append(cpd)
    return mapping


async def _kegg_pathway_compound_count(client: httpx.AsyncClient, pathway_id: str) -> int:
    text = await _kegg_text(client, f"link/compound/{pathway_id}")
    cpds = {line.split("\t")[0].replace("cpd:", "").strip() for line in text.splitlines() if "\t" in line}
    return len(cpds)


async def _kegg_pathway_names(client: httpx.AsyncClient, pathway_ids: List[str], organism: str) -> Dict[str, str]:
    names = {}
    for pid in pathway_ids:
        if pid.startswith("map") and organism and organism != "map":
            org_pid = f"{organism}{pid[3:]}"
            text = await _kegg_text(client, f"get/{org_pid}")
            name = _parse_kegg_name(text)
            if name:
                names[pid] = name
                continue
        text = await _kegg_text(client, f"get/{pid}")
        name = _parse_kegg_name(text, pid)
        names[pid] = name
    return names


def _fdr_adjust(pvalues: List[float]) -> List[float]:
    if not pvalues:
        return []
    try:
        _, padj, _, _ = multipletests(np.array(pvalues, dtype=float), method="fdr_bh")
        return [float(x) for x in padj]
    except Exception:
        return pvalues[:]


async def kegg_enrichment(feature_names: List[str], significant_names: List[str], organism: str = "hsa", top_n: int = 20) -> Dict[str, Any]:
    if not significant_names:
        return {"error": "No significant features provided for KEGG enrichment."}

    async with httpx.AsyncClient() as client:
        all_names = list(set(feature_names or []) | set(significant_names))
        name_to_cpd = await _map_features_to_kegg_cpds(client, all_names)

        sig_cpd_map = {name: name_to_cpd.get(name) for name in significant_names}
        cpd_to_name = {v: k for k, v in sig_cpd_map.items() if v}
        sig_cpds = set(cpd_to_name.keys())

        bg_cpds = {name_to_cpd[n] for n in (feature_names or significant_names) if name_to_cpd.get(n)}
        if not sig_cpds or not bg_cpds:
            return {"error": "No KEGG compound mappings found for the selected features."}

        all_cpds = list(sig_cpds | bg_cpds)[:200]
        pathway_to_cpds = await _kegg_pathways_for_compounds(client, all_cpds)
        if not pathway_to_cpds:
            return {"error": "No KEGG pathways found for the mapped compounds."}

        N = len(bg_cpds)
        n = len(sig_cpds)
        pvalues = []
        rows = []
        for pid, cpds in pathway_to_cpds.items():
            cpd_set = set(cpds)
            k = len(cpd_set & sig_cpds)
            K = len(cpd_set & bg_cpds)
            if k == 0 or K == 0 or n == 0 or N == 0:
                continue
            p = float(scipy_stats.hypergeom.sf(k - 1, N, K, n))
            pvalues.append(p)
            rows.append({
                "pathway_id": pid,
                "found_compounds": [cpd_to_name[c] for c in (cpd_set & sig_cpds) if c in cpd_to_name],
                "compound_count": k,
                "pathway_compound_count": K,
                "pvalue": p,
            })

        padj = _fdr_adjust(pvalues)
        for r, q in zip(rows, padj):
            r["padj"] = q

        rows.sort(key=lambda r: (r["padj"], r["pvalue"]))
        top = rows[:top_n]
        names = await _kegg_pathway_names(client, [r["pathway_id"] for r in top], organism)
        for r in top:
            r["name"] = names.get(r["pathway_id"], r["pathway_id"])

        return {"pathways": top, "n_mapped": n, "n_significant": len(significant_names), "n_background": N}


async def reactome_enrichment(feature_names: List[str], top_n: int = 20) -> Dict[str, Any]:
    if not feature_names:
        return {"error": "No features provided for Reactome enrichment."}

    async with httpx.AsyncClient() as client:
        name_to_cpd = await _map_features_to_kegg_cpds(client, feature_names)
        cpd_ids = sorted({v for v in name_to_cpd.values() if v})
        # Reactome accepts KEGG compound IDs; if mapping failed fall back to original names
        payload_terms = cpd_ids if cpd_ids else feature_names
        payload = "\n".join(payload_terms)

    url = f"{REACTOME_BASE}/identifiers/projection?pageSize={max(top_n, 100)}&page=1"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                content=payload,
                headers={"Content-Type": "text/plain", "Accept": "application/json"},
                timeout=60.0,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"error": f"Reactome API request failed: {exc}"}

    pathways = data.get("pathways", [])
    rows = []
    for p in pathways:
        ent = p.get("entities", {})
        rows.append({
            "pathway_id": p.get("stId"),
            "name": p.get("name"),
            "found": ent.get("found", 0),
            "total": ent.get("total", 0),
            "pvalue": ent.get("pValue"),
            "padj": ent.get("fdr"),
            "fdr": ent.get("fdr"),
            "source": "Reactome",
        })
    rows.sort(key=lambda r: (r["pvalue"] if r["pvalue"] is not None else 1.0, r["fdr"] if r["fdr"] is not None else 1.0))
    return {"pathways": rows[:top_n], "identifiers_not_found": data.get("identifiersNotFound"), "pathways_found": data.get("pathwaysFound"), "n_mapped": len(cpd_ids)}


async def go_enrichment(feature_names: List[str], organism: str = "hsapiens", top_n: int = 20) -> Dict[str, Any]:
    if not feature_names:
        return {"error": "No features provided for GO enrichment."}

    kegg_org = organism if organism not in GPROFILER_ORG_MAP.values() else GPROFILER_TO_KEGG_ORG.get(organism, "hsa")
    gprofiler_org = GPROFILER_ORG_MAP.get(organism, organism)

    async with httpx.AsyncClient() as client:
        name_to_cpd = await _map_features_to_kegg_cpds(client, feature_names)
        cpd_ids = sorted({v for v in name_to_cpd.values() if v})
        if not cpd_ids:
            return {"error": "No KEGG compound mappings found for GO gene derivation."}

        genes = await _kegg_cpds_to_organism_genes(client, cpd_ids, organism=kegg_org)
        if not genes:
            return {"error": "No organism genes could be derived from the mapped KEGG compounds."}

    payload = {
        "organism": gprofiler_org,
        "query": genes,
        "sources": ["GO:BP", "GO:MF", "GO:CC"],
        "user_threshold": 0.05,
        "no_evidences": True,
        "all_results": False,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(GPROFILER_BASE, json=payload, headers={"User-Agent": "isotopiq-devin"}, timeout=60.0)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"GO (g:Profiler) API request failed: {exc.response.status_code} - {exc.response.text[:300]}"}
    except Exception as exc:
        return {"error": f"GO (g:Profiler) API request failed: {exc}"}

    result = data.get("result", []) if isinstance(data, dict) else data
    rows = []
    for term in result:
        rows.append({
            "term_id": term.get("native"),
            "name": term.get("name"),
            "source": term.get("source"),
            "pvalue": term.get("p_value"),
            "padj": term.get("p_value"),
            "term_size": term.get("term_size"),
            "intersection_size": term.get("intersection_size"),
            "query_size": term.get("query_size"),
        })
    rows.sort(key=lambda r: r["pvalue"] if r["pvalue"] is not None else 1.0)
    return {"pathways": rows[:top_n], "n_mapped_compounds": len(cpd_ids), "n_genes": len(genes)}


def enrichment_bar_figure(rows: List[Dict[str, Any]], title: str, style: Dict[str, Any]) -> Dict[str, Any]:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from app.services.plots import _apply_base_layout

    if not rows:
        fig = go.Figure()
        _apply_base_layout(fig, style, title=title)
        return fig.to_dict()

    labels = [r.get("name", r.get("pathway_id", r.get("term_id", "")))[:60] for r in rows]
    scores = [-math.log10(max(r.get("padj", r.get("pvalue", 1.0)), 1e-300)) for r in rows]
    colors = ["#c44e52" if s < 0.05 else "#2e6575" for s in [r.get("padj", r.get("pvalue", 1.0)) for r in rows]]

    fig = go.Figure(go.Bar(
        x=scores,
        y=labels,
        orientation="h",
        marker_color=colors,
        hovertemplate="%{y}<br>-log10(padj): %{x:.3f}<extra></extra>",
    ))
    _apply_base_layout(fig, style, title=title)
    fig.update_layout(
        xaxis_title="-log10(adjusted p-value)",
        yaxis=dict(automargin=True, tickfont=dict(size=max(7, style.get("tick_size", 11) - 1))),
        xaxis=dict(automargin=True),
        margin=dict(l=150, r=40, t=80, b=60),
    )
    return fig.to_dict()


def enrichment_table_figure(rows: List[Dict[str, Any]], title: str, style: Dict[str, Any]) -> Dict[str, Any]:
    import plotly.graph_objects as go
    from app.services.plots import _apply_base_layout

    if not rows:
        fig = go.Figure()
        _apply_base_layout(fig, style, title=title)
        return fig.to_dict()

    headers = ["Pathway / Term", "p-value", "adj. p-value", "Found", "Total"]
    values = [
        [r.get("name", r.get("pathway_id", r.get("term_id", "")))[:60] for r in rows],
        [f"{r.get('pvalue', 1.0):.3e}" for r in rows],
        [f"{r.get('padj', r.get('pvalue', 1.0)):.3e}" for r in rows],
        [str(r.get("found", r.get("compound_count", r.get("intersection_size", 0)))) for r in rows],
        [str(r.get("total", r.get("pathway_compound_count", r.get("term_size", 0)))) for r in rows],
    ]
    fig = go.Figure(go.Table(
        header=dict(values=headers, fill_color="#f1f5f9", align="left", font=dict(size=11, color="#1e293b")),
        cells=dict(values=values, align="left", font=dict(size=10, color="#334155"), height=22),
    ))
    _apply_base_layout(fig, style, title=title)
    fig.update_layout(margin=dict(l=40, r=40, t=80, b=40))
    return fig.to_dict()

import re
import math
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx
import numpy as np
from scipy import stats as scipy_stats
from statsmodels.stats.multitest import multipletests


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


async def _kegg_find_compound(client: httpx.AsyncClient, name: str) -> Optional[str]:
    if not name or not str(name).strip():
        return None
    text = await _kegg_text(client, f"find/compound/{_safe_url(str(name).strip())}")
    if not text:
        return None
    for line in text.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("cpd:"):
            return parts[0].replace("cpd:", "").strip()
    return None


def _safe_url(value: str) -> str:
    return quote(value, safe="")


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
        # Map significant features to KEGG compound IDs (concurrent)
        find_tasks = [asyncio.create_task(_kegg_find_compound(client, name)) for name in significant_names]
        find_results = await asyncio.gather(*find_tasks)
        sig_cpd_map = dict(zip(significant_names, find_results))

        cpd_to_name = {v: k for k, v in sig_cpd_map.items() if v}
        mapped_cpds = list(cpd_to_name.keys())
        if not mapped_cpds:
            return {"error": "No KEGG compound mappings found for the significant features."}

        # Pathways for significant compounds
        pathway_to_cpds = await _kegg_pathways_for_compounds(client, mapped_cpds)
        if not pathway_to_cpds:
            return {"error": "No KEGG pathways found for the mapped compounds."}

        # Background compound count
        total_cpds = await _kegg_total_compounds(client)

        # Enrichment statistics
        n = len(mapped_cpds)
        pvalues = []
        rows = []
        counts = await asyncio.gather(
            *[_kegg_pathway_compound_count(client, pid) for pid in pathway_to_cpds.keys()]
        )
        for (pid, cpds), K in zip(pathway_to_cpds.items(), counts):
            k = len(cpds)
            if k == 0 or K == 0:
                continue
            p = float(scipy_stats.hypergeom.sf(k - 1, total_cpds, K, n))
            pvalues.append(p)
            rows.append({
                "pathway_id": pid,
                "found_compounds": [cpd_to_name[c] for c in cpds if c in cpd_to_name],
                "compound_count": k,
                "pathway_compound_count": K,
                "pvalue": p,
            })

        padj = _fdr_adjust(pvalues)
        for r, q in zip(rows, padj):
            r["padj"] = q

        # Sort by padj and annotate names
        rows.sort(key=lambda r: (r["padj"], r["pvalue"]))
        top = rows[:top_n]
        names = await _kegg_pathway_names(client, [r["pathway_id"] for r in top], organism)
        for r in top:
            r["name"] = names.get(r["pathway_id"], r["pathway_id"])

        return {"pathways": top, "n_mapped": n, "n_significant": len(significant_names)}


async def reactome_enrichment(feature_names: List[str], top_n: int = 20) -> Dict[str, Any]:
    if not feature_names:
        return {"error": "No features provided for Reactome enrichment."}
    payload = "\n".join(feature_names)
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
    return {"pathways": rows[:top_n], "identifiers_not_found": data.get("identifiersNotFound"), "pathways_found": data.get("pathwaysFound")}


async def go_enrichment(feature_names: List[str], organism: str = "hsapiens", top_n: int = 20) -> Dict[str, Any]:
    if not feature_names:
        return {"error": "No features provided for GO enrichment."}
    organism = GPROFILER_ORG_MAP.get(organism, organism)
    payload = {
        "organism": organism,
        "query": feature_names,
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
    return {"pathways": rows[:top_n]}


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

"""Lipid building block (chain-level) analysis.

Inspired by LipidOne, this module breaks each molecular species into its
constituent acyl/alkyl/alkenyl chains, divides the parent intensity by the
number of chains, and aggregates identical pseudo-lipids across the dataset.
"""

import re
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def _parse_chains(name: str):
    """Extract chains from a lipid name."""
    paren = re.search(r"\(([^)]+)\)", name)
    if paren:
        chain_str = paren.group(1)
    else:
        # fallback: look for chain tokens after the first space or after the class abbreviation
        chain_str = re.sub(r"^[^A-Za-z0-9\-]*[A-Za-z0-9\-]+\s*", "", name).strip()
        if not chain_str:
            return []
    out = []
    for token in re.split(r"[_/]+", chain_str):
        token = re.sub(r"\(.*?\)", "", token).strip()
        m = re.match(r"^(P|O|d)?-?(\d+):(\d+)", token)
        if not m:
            continue
        prefix = m.group(1) or ""
        carbon = int(m.group(2))
        db = int(m.group(3))
        out.append({
            "carbon": carbon,
            "db": db,
            "type": "plasmalogen" if prefix == "P" else ("alkyl" if prefix == "O" else "acyl"),
        })
    return out


def _normalize_class(cls: str) -> str:
    s = cls.upper().replace("-", "")
    mapping = {
        "LPC": "LPC",
        "LPE": "LPE",
        "LPI": "LPI",
        "LPS": "LPS",
        "LPG": "LPG",
        "LPA": "LPA",
        "PC": "PC",
        "PE": "PE",
        "PI": "PI",
        "PS": "PS",
        "PG": "PG",
        "PA": "PA",
        "SM": "SM",
        "CER": "Cer",
        "CERAMIDE": "Cer",
        "TG": "TG",
        "TRIACYLGLYCEROL": "TG",
        "DG": "DG",
        "DIACYLGLYCEROL": "DG",
        "CE": "CE",
        "CHOLESTERYLESTER": "CE",
        "FC": "FC",
        "FFA": "FA",
        "FA": "FA",
        "CL": "CL",
        "CAR": "CAR",
        "CARNITINE": "CAR",
    }
    return mapping.get(s, s)


def _parse_feature(name: str) -> Tuple[str, List[Dict[str, Any]]]:
    m = re.match(r"^([A-Za-z0-9\-]+?)(?:\(|:|\s|$)", name)
    cls = m.group(1) if m else "Unknown"
    chains = _parse_chains(name)
    return _normalize_class(cls), chains


def _bh(pvals: np.ndarray) -> np.ndarray:
    pvals = np.asarray(pvals, dtype=float)
    n = len(pvals)
    if n == 0:
        return pvals
    order = np.argsort(pvals)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, n + 1)
    padj = pvals * n / ranks
    padj = np.minimum.accumulate(padj[order[::-1]])[order[::-1]][order]
    return np.minimum(padj, 1.0)


def build_chain_matrix(df: pd.DataFrame, feature_metadata: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Return a chain-level matrix (rows=pseudo-lipids, columns=samples) plus row metadata."""
    samples = df.columns.tolist()
    rows: Dict[str, np.ndarray] = {}
    row_meta: Dict[str, Dict[str, Any]] = {}

    n = len(samples)
    for i, meta in enumerate(feature_metadata):
        if i >= len(df):
            continue
        name = meta.get("feature_id", "") or meta.get("name", "")
        cls, chains = _parse_feature(name)
        if not chains:
            continue
        vals = df.iloc[i].values.astype(float)
        weight = 1.0 / len(chains)
        for ch in chains:
            key = f"{cls}_{ch['carbon']}:{ch['db']}"
            if ch["type"] in ("alkyl", "plasmalogen"):
                key = f"{ch['type'][0].upper()}-{key}"
            if key not in rows:
                rows[key] = np.zeros(n)
                row_meta[key] = {"name": key, "class": cls, "carbon": ch["carbon"], "db": ch["db"], "chain_type": ch["type"]}
            rows[key] += vals * weight

    if not rows:
        return pd.DataFrame(index=[], columns=samples), {}

    matrix = pd.DataFrame({k: v for k, v in rows.items()}).T
    matrix.index = list(rows.keys())
    matrix.columns = samples
    return matrix, row_meta


def compute_building_blocks(
    df: pd.DataFrame,
    feature_metadata: List[Dict[str, Any]],
    sample_meta: Dict[str, str],
    group_a: str,
    group_b: str,
) -> Dict[str, Any]:
    """Compute chain-level summary and statistics."""
    chain_df, row_meta = build_chain_matrix(df, feature_metadata)
    if chain_df.empty:
        return {"rows": [], "summary": {}}

    a_cols = [c for c in chain_df.columns if sample_meta.get(c) == group_a]
    b_cols = [c for c in chain_df.columns if sample_meta.get(c) == group_b]

    rows = []
    for idx, row in chain_df.iterrows():
        meta = row_meta.get(idx, {})
        a_vals = row[a_cols].values.astype(float)
        b_vals = row[b_cols].values.astype(float)
        a_vals = a_vals[np.isfinite(a_vals)]
        b_vals = b_vals[np.isfinite(b_vals)]
        mean_a = float(np.nanmean(a_vals)) if len(a_vals) else 0.0
        mean_b = float(np.nanmean(b_vals)) if len(b_vals) else 0.0
        p = float(scipy_stats.ttest_ind(a_vals, b_vals, equal_var=False).pvalue) if len(a_vals) > 1 and len(b_vals) > 1 else 1.0
        log2fc = float(np.log2(mean_b / mean_a)) if mean_a > 0 and mean_b > 0 else 0.0
        rows.append({
            "name": idx,
            "class": meta.get("class", ""),
            "carbon": meta.get("carbon", 0),
            "db": meta.get("db", 0),
            "chain_type": meta.get("chain_type", "acyl"),
            "mean_a": mean_a,
            "mean_b": mean_b,
            "log2fc": log2fc,
            "pvalue": p,
        })

    pvals = np.array([r["pvalue"] for r in rows])
    padjs = _bh(pvals)
    for r, padj in zip(rows, padjs):
        r["padj"] = float(padj)
        r["significant"] = bool(padj < 0.05)

    # Summary tables by chain type, carbon length, db count
    def summarize(series_key):
        out = {}
        for g, cols in [(group_a, a_cols), (group_b, b_cols)]:
            out[g] = {}
            for r in rows:
                key = r[series_key]
                out[g][key] = out[g].get(key, 0.0) + (r["mean_a"] if g == group_a else r["mean_b"])
        return out

    return {
        "rows": rows,
        "summary": {
            "by_carbon": summarize("carbon"),
            "by_db": summarize("db"),
            "by_type": summarize("chain_type"),
        },
    }

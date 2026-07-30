import math
import re
from collections import defaultdict
import numpy as np
import pandas as pd
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe
from app.services.flux_map import build_flux_map


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


def _extract_isotopologue_groups(df: pd.DataFrame, sample_metadata: dict) -> dict:
    """Group isotopologue columns by sample group. Column names must contain M+{n}."""
    groups = defaultdict(lambda: defaultdict(list))
    for col in df.columns:
        m = re.search(r"M\+(\d+)", str(col))
        if not m:
            continue
        idx = int(m.group(1))
        group = sample_metadata.get(str(col))
        if not group or group == "unknown":
            prefix = re.match(r"^(.+?)_M\+\d+", str(col))
            suffix = re.match(r"M\+\d+_(.+)$", str(col))
            if prefix:
                group = prefix.group(1)
            elif suffix:
                group = suffix.group(1)
            else:
                group = "All"
        groups[group][idx].append(col)
    return groups


def _build_iso_df(df: pd.DataFrame, m_cols: dict, max_label: int) -> pd.DataFrame:
    """Build a numeric M+0..M+max dataframe by averaging columns in m_cols per M index."""
    cols = {}
    for i in range(max_label + 1):
        if i in m_cols and m_cols[i]:
            vals = df[m_cols[i]]
            cols[f"M+{i}"] = vals.mean(axis=1)
    iso = pd.DataFrame(cols, index=df.index)
    iso = iso.fillna(0).apply(pd.to_numeric, errors="coerce").fillna(0).clip(lower=0)
    return iso


def _compute_metrics(df_iso: pd.DataFrame, max_label: int, req: schemas.IsotopeRequest, feature_ids: list):
    """Compute isotopologue fractions and labeling metrics from a M+0..M+n dataframe."""
    row_sums = df_iso.sum(axis=1).replace(0, np.nan)
    fractions = df_iso.div(row_sums, axis=0).fillna(0)

    ordered_cols = [f"M+{i}" for i in range(max_label + 1) if f"M+{i}" in df_iso.columns]
    if not ordered_cols:
        ordered_cols = list(df_iso.columns)

    total_labeled = 1 - fractions.get("M+0", pd.Series(0, index=fractions.index))

    if req.circulating_enrichment:
        circ = float(req.circulating_enrichment)
        fractional_enrichment = total_labeled / circ if circ > 0 else total_labeled
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

    return {
        "fractions": fractions_by_feature,
        "total_labeled_fraction": _series_by_feature(total_labeled, feature_ids),
        "fractional_enrichment": _series_by_feature(fractional_enrichment, feature_ids),
        "mean_labeled_atoms": _series_by_feature(mean_labeled_atoms, feature_ids),
        "pooled_labeling": _series_by_feature(pooled_labeling, feature_ids),
        "row_sums": row_sums.fillna(0),
        "mean_labeled_atoms_series": mean_labeled_atoms,
    }


async def _build_flux_map_for_group(
    dataset: models.Dataset,
    feature_ids: list,
    metrics: dict,
    req: schemas.IsotopeRequest,
    title: str,
):
    flux_map_options = {
        "layout": getattr(req, "layout", "spring"),
        "graph_mode": getattr(req, "graph_mode", "full"),
        "edge_weight": getattr(req, "edge_weight", "label_gradient"),
        "k": getattr(req, "k", 3),
        "source_node": getattr(req, "source_node", None),
        "target_node": getattr(req, "target_node", None),
        "map_source": getattr(req, "map_source", None),
        "map_id": getattr(req, "map_id", None),
        "title": title,
        "style": getattr(req, "style", "classic"),
    }
    return await build_flux_map(
        dataset,
        feature_ids,
        metrics["mean_labeled_atoms_series"],
        metrics["row_sums"],
        options=flux_map_options,
    )


async def run_isotope_analysis(dataset: models.Dataset, req: schemas.IsotopeRequest):
    df = to_dataframe(dataset)
    feature_ids = _feature_lookup(dataset, df)
    tracer = req.tracer
    max_label = max(0, int(req.max_label))

    sample_metadata = dataset.sample_metadata or {}
    groups = _extract_isotopologue_groups(df, sample_metadata)
    if not groups:
        return {"error": "No isotopologue columns found. Columns must include M+0, M+1, etc."}

    all_groups = sorted(groups.keys())
    selected_groups = req.selected_groups or all_groups

    # Overall map: aggregate every group by M index.
    overall_mcols = defaultdict(list)
    for mcols in groups.values():
        for idx, cols in mcols.items():
            overall_mcols[idx].extend(cols)
    overall_iso = _build_iso_df(df, overall_mcols, max_label)
    overall_metrics = _compute_metrics(overall_iso, max_label, req, feature_ids)
    overall_flux = await _build_flux_map_for_group(
        dataset, feature_ids, overall_metrics, req, "Flux map"
    )

    results = {
        "tracer": tracer,
        "max_label": max_label,
        "fractions": overall_metrics["fractions"],
        "total_labeled_fraction": overall_metrics["total_labeled_fraction"],
        "fractional_enrichment": overall_metrics["fractional_enrichment"],
        "mean_labeled_atoms": overall_metrics["mean_labeled_atoms"],
        "pooled_labeling": overall_metrics["pooled_labeling"],
        "flux_map": overall_flux,
        "groups": {},
        "available_groups": all_groups,
    }

    include_groups = len(all_groups) > 1 or req.selected_groups is not None
    if all_groups == ["All"] and req.selected_groups is None:
        include_groups = False
    if include_groups:
        for group in selected_groups:
            if group not in groups:
                continue
            group_iso = _build_iso_df(df, groups[group], max_label)
            group_metrics = _compute_metrics(group_iso, max_label, req, feature_ids)
            group_flux = await _build_flux_map_for_group(
                dataset, feature_ids, group_metrics, req, f"Flux map — {group}"
            )
            results["groups"][group] = {
                "fractions": group_metrics["fractions"],
                "total_labeled_fraction": group_metrics["total_labeled_fraction"],
                "fractional_enrichment": group_metrics["fractional_enrichment"],
                "mean_labeled_atoms": group_metrics["mean_labeled_atoms"],
                "pooled_labeling": group_metrics["pooled_labeling"],
                "flux_map": group_flux,
            }

    return results

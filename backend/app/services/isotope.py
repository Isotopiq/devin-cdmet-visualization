import math
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


async def run_isotope_analysis(dataset: models.Dataset, req: schemas.IsotopeRequest):
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

    flux_map_options = {
        "layout": getattr(req, "layout", "spring"),
        "graph_mode": getattr(req, "graph_mode", "full"),
        "edge_weight": getattr(req, "edge_weight", "label_gradient"),
        "k": getattr(req, "k", 3),
        "source_node": getattr(req, "source_node", None),
        "target_node": getattr(req, "target_node", None),
        "map_source": getattr(req, "map_source", None),
        "map_id": getattr(req, "map_id", None),
        "title": "Flux map",
    }

    flux_map = await build_flux_map(
        dataset,
        feature_ids,
        mean_labeled_atoms,
        row_sums.fillna(0),
        options=flux_map_options,
    )

    results = {
        "tracer": tracer,
        "max_label": max_label,
        "fractions": fractions_by_feature,
        "total_labeled_fraction": _series_by_feature(total_labeled, feature_ids),
        "fractional_enrichment": _series_by_feature(fractional_enrichment, feature_ids),
        "mean_labeled_atoms": _series_by_feature(mean_labeled_atoms, feature_ids),
        "pooled_labeling": _series_by_feature(pooled_labeling, feature_ids),
        "flux_map": flux_map,
    }
    return results

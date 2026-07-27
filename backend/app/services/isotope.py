import math
import numpy as np
import pandas as pd
from app import models, schemas
from app.services.preprocessing import to_dataframe, _to_json_safe


def _sanitize_series(s):
    if isinstance(s, (pd.Series, pd.DataFrame)):
        return _to_json_safe(s.replace([np.inf, -np.inf], np.nan).fillna(0).to_dict())
    return _to_json_safe(s)


def run_isotope_analysis(dataset: models.Dataset, req: schemas.IsotopeRequest):
    df = to_dataframe(dataset)
    tracer = req.tracer
    max_label = max(0, int(req.max_label))

    isotopologue_cols = [c for c in df.columns if f"M+" in str(c) or tracer in str(c)]
    if not isotopologue_cols:
        return {"error": "No isotopologue columns found. Columns must include M+0, M+1, etc."}

    # Ensure non-negative values before computing fractions
    df_iso = df[isotopologue_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    df_iso = df_iso.clip(lower=0)

    row_sums = df_iso.sum(axis=1).replace(0, np.nan)
    fractions = df_iso.div(row_sums, axis=0).fillna(0)

    total_labeled = 1 - fractions.get("M+0", pd.Series(0, index=fractions.index))

    if req.natural_abundance_correction:
        # Placeholder: implement a correction method if tracer-specific isotopomer data is available.
        # For now, return fractions as-is to avoid undefined corrections.
        pass

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

    results = {
        "tracer": tracer,
        "max_label": max_label,
        "fractions": _sanitize_series(fractions),
        "total_labeled_fraction": _sanitize_series(total_labeled),
        "fractional_enrichment": _sanitize_series(fractional_enrichment),
        "mean_labeled_atoms": _sanitize_series(mean_labeled_atoms),
        "pooled_labeling": _sanitize_series(pooled_labeling),
    }
    return results

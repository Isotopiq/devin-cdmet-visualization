import numpy as np
import pandas as pd
from app import models, schemas
from app.services.preprocessing import to_dataframe


def run_isotope_analysis(dataset: models.Dataset, req: schemas.IsotopeRequest):
    df = to_dataframe(dataset)
    tracer = req.tracer
    max_label = req.max_label

    isotopologue_cols = [c for c in df.columns if f"M+" in str(c) or tracer in str(c)]
    if not isotopologue_cols:
        return {"error": "No isotopologue columns found. Columns must include M+0, M+1, etc."}

    fractions = df[isotopologue_cols].div(df[isotopologue_cols].sum(axis=1), axis=0).fillna(0)
    total_labeled = 1 - fractions.get("M+0", fractions.iloc[:, 0] * 0)
    mean_labeled_atoms = sum(i * fractions.get(f"M+{i}", 0) for i in range(max_label + 1))
    pooled_labeling = mean_labeled_atoms / max_label if max_label > 0 else 0

    if req.natural_abundance_correction:
        corrected = {}
        for i in range(max_label + 1):
            corrected[f"M+{i}"] = fractions.get(f"M+{i}", 0)
        fractions = corrected

    if req.circulating_enrichment:
        fractional_enrichment = total_labeled / req.circulating_enrichment
    else:
        fractional_enrichment = total_labeled

    results = {
        "tracer": tracer,
        "max_label": max_label,
        "fractions": fractions.to_dict(),
        "total_labeled_fraction": total_labeled.to_dict(),
        "fractional_enrichment": fractional_enrichment.to_dict() if hasattr(fractional_enrichment, "to_dict") else float(fractional_enrichment),
        "mean_labeled_atoms": mean_labeled_atoms.to_dict() if hasattr(mean_labeled_atoms, "to_dict") else float(mean_labeled_atoms),
        "pooled_labeling": pooled_labeling.to_dict() if hasattr(pooled_labeling, "to_dict") else float(pooled_labeling),
    }
    return results

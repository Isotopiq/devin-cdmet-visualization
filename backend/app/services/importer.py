import os
import math
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.services.detection import (
    read_file_to_df,
    detect_columns,
    parse_sample_metadata,
    select_top_lipid_candidate,
)
from app.services.preprocessing import _to_json_safe


def _grade_score(grade) -> int:
    if not grade:
        return 99
    g = str(grade).strip().upper()
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    return order.get(g[0], 99)


def _safe_float(value, default=0.0):
    try:
        v = float(value)
        if math.isfinite(v):
            return v
        return default
    except (TypeError, ValueError):
        return default


def _deduplicate_lipid_features(feature_metadata, data_matrix):
    """Group features by (lipid name, adduct) and keep the best-graded / highest-rated representative."""
    groups = {}
    for i, meta in enumerate(feature_metadata):
        name = str(meta.get("feature_id", "")).strip().lower()
        adduct = str(
            meta.get("adduct") or meta.get("top_candidate_adduct") or ""
        ).strip().lower()
        if not name:
            continue
        groups.setdefault((name, adduct), []).append(i)

    keep = []
    duplicate_map = {}
    for key, idxs in groups.items():
        if len(idxs) == 1:
            keep.append(idxs[0])
            continue

        def _score(i):
            meta = feature_metadata[i]
            gs = _grade_score(
                meta.get("top_candidate_grade") or meta.get("grade")
            )
            pr = _safe_float(meta.get("peak_rating"), 0.0)
            return (gs, -pr)

        sorted_idxs = sorted(idxs, key=_score)
        keep.append(sorted_idxs[0])
        for dup in sorted_idxs[1:]:
            duplicate_map[dup] = sorted_idxs[0]

    if duplicate_map:
        keep_indices = list(dict.fromkeys(keep))
        dup_report = {
            feature_metadata[dup]["feature_id"]: feature_metadata[kept]["feature_id"]
            for dup, kept in duplicate_map.items()
        }
        feature_metadata = [feature_metadata[i] for i in keep_indices]
        data_matrix = {
            col: [_to_json_safe(vals[i]) for i in keep_indices]
            for col, vals in data_matrix.items()
        }
        return feature_metadata, data_matrix, dup_report

    return feature_metadata, data_matrix, {}


async def import_dataset(
    db: AsyncSession,
    uploaded: models.UploadedFile,
    feature_type: str = "metabolite",
    metadata_path: str = None,
):
    path = os.path.join("uploads", uploaded.stored_name)
    df = read_file_to_df(path, uploaded.selected_sheet)

    metadata = None
    if metadata_path:
        metadata = parse_sample_metadata(metadata_path)

    detected = detect_columns(df, metadata=metadata)

    mapping = uploaded.column_mapping or {}
    feature_id_col = (
        mapping.get("feature_id")
        or mapping.get("name")
        or detected["suggested_mapping"].get("feature_id")
        or str(df.columns[0])
    )
    sample_cols = mapping.get("sample_columns") or detected["sample_columns"]
    if not sample_cols:
        sample_cols = list(df.columns)

    feature_keys = [
        "formula",
        "mz",
        "rt",
        "adduct",
        "lipid_class",
        "grade",
        "fa",
        "calc_mw",
        "polarity",
        "neutral_losses",
        "peak_rating",
        "num_lipidsearch_results",
    ]
    has_lipid_candidates = "_lipid_candidates" in df.columns

    feature_metadata = []
    for _, row in df.iterrows():
        raw_id = row.get(feature_id_col, "")
        meta = {"feature_id": str(raw_id) if raw_id is not None else ""}
        for key in feature_keys:
            col = mapping.get(key) or detected["suggested_mapping"].get(key)
            if col and col in row:
                meta[key] = row[col]

        if has_lipid_candidates:
            candidates = row.get("_lipid_candidates") or []
            top = select_top_lipid_candidate(candidates)
            if top:
                meta["lipid_candidates"] = candidates
                meta["top_candidate_name"] = top.get("Name")
                meta["top_candidate_formula"] = top.get("Formula")
                meta["top_candidate_class"] = top.get("Class Name")
                meta["top_candidate_sub_class"] = top.get("Sub-Class Name")
                meta["top_candidate_grade"] = top.get("Grade")
                meta["top_candidate_rank"] = top.get("Rank")
                meta["top_candidate_id_score"] = top.get("ID Score")
                meta["top_candidate_adduct"] = top.get("Adduct")
                meta["top_candidate_compound_match"] = top.get("Compound Match")

        feature_metadata.append(meta)

    data_matrix = {}
    for col in sample_cols:
        data_matrix[str(col)] = [
            _to_json_safe(v)
            for v in pd.to_numeric(df[col], errors="coerce").tolist()
        ]

    sample_groups = mapping.get("sample_groups") or detected["sample_groups"]
    sample_metadata = {str(col): sample_groups.get(str(col), "unknown") for col in sample_cols}

    feature_metadata = [
        {k: _to_json_safe(v) for k, v in meta.items()} for meta in feature_metadata
    ]

    processing_history = [
        {"step": "import", "source": uploaded.original_name}
    ]

    # Deduplicate lipid features based on identity (name + adduct) using grade and peak rating.
    if feature_type == "lipid" or has_lipid_candidates:
        feature_metadata, data_matrix, dup_report = _deduplicate_lipid_features(
            feature_metadata, data_matrix
        )
        if dup_report:
            processing_history.append({
                "step": "deduplicate",
                "duplicates_removed": len(dup_report),
                "duplicate_map": dup_report,
            })

    dataset = models.Dataset(
        project_id=uploaded.project_id,
        source_file_id=uploaded.id,
        name=uploaded.original_name,
        feature_type=feature_type,
        data_matrix=data_matrix,
        sample_metadata=sample_metadata,
        feature_metadata=feature_metadata,
        processing_history=processing_history,
    )
    db.add(dataset)
    uploaded.status = "imported"
    await db.commit()
    await db.refresh(dataset)
    return dataset

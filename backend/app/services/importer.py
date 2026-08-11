import os
import math
import re
from typing import Any, Dict, List
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.config import settings
from app.services.detection import (
    read_file_to_df,
    detect_columns,
    parse_sample_metadata,
    select_top_lipid_candidate,
    LIPIDSEARCH_AREA_RE,
    _normalize_lipidsearch_sample_id,
    _base_raw_name,
    _is_el_maven_df,
    _el_maven_sample_group,
)
from app.services.preprocessing import _to_json_safe
from app.services import storage


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


def _parse_isotope_label(label: Any) -> int:
    """Extract the mass-shift index from an El-MAVEN isotopeLabel string.

    Examples:
        "C12 PARENT" -> 0
        "D2-label-1" -> 1
        "C13-label-10" -> 10
        "N15-label-2" -> 2
    """
    s = str(label) if label is not None else ""
    if "PARENT" in s.upper():
        return 0
    m = re.search(r"(\d+)$", s.strip())
    if m:
        return int(m.group(1))
    return 0


def _pivot_el_maven(
    df: pd.DataFrame,
    source_name: str,
    feature_type: str,
    processing_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Pivot an El-MAVEN isotopologue export into a dataset matrix with M+ columns."""
    feature_cols = {
        "label", "metagroupid", "groupid", "goodpeakcount", "medmz", "medrt",
        "maxquality", "adductname", "isotopelabel", "compound", "compoundid",
        "formula", "expectedrtdiff", "ppmdiff", "parent",
    }
    sample_cols = [c for c in df.columns if str(c).lower() not in feature_cols]

    sample_groups = {c: _el_maven_sample_group(c) for c in sample_cols}

    df["_m_index"] = df["isotopeLabel"].apply(_parse_isotope_label)
    # Group by the compound name. Different adducts, if present, will be treated
    # as separate compounds only if the parent row and isotopologue rows share the
    # same adduct string; El-MAVEN typically leaves adductName blank for labels.
    df["_compound_key"] = df.apply(
        lambda r: str(r.get("compound") or r.get("compoundId") or "").strip(),
        axis=1,
    )

    max_m = int(df["_m_index"].max())

    # Build one row per compound using parent-row metadata when available.
    compound_meta: Dict[str, Dict[str, Any]] = {}
    compound_values: Dict[str, Dict[str, Any]] = {}

    for idx, row in df.iterrows():
        key = str(row["_compound_key"]) if pd.notna(row.get("_compound_key")) else str(idx)
        if key not in compound_meta:
            compound_meta[key] = {}
            compound_values[key] = {}
        # Prefer the parent isotopologue row (m=0) for metadata.
        if row["_m_index"] == 0 or not compound_meta[key]:
            formula = row.get("formula")
            compound_meta[key] = {
                "feature_id": str(row.get("compound")) if pd.notna(row.get("compound")) else key,
                "formula": str(formula) if pd.notna(formula) else None,
                "mz": float(row["medMz"]) if pd.notna(row.get("medMz")) else None,
                "rt": float(row["medRt"]) if pd.notna(row.get("medRt")) else None,
                "adduct": str(row["adductName"]) if pd.notna(row.get("adductName")) else None,
                "compound_id": str(row["compoundId"]) if pd.notna(row.get("compoundId")) else None,
                "parent_mz": float(row["parent"]) if pd.notna(row.get("parent")) else None,
            }
            if not compound_values[key]:
                compound_values[key] = {}
        m = int(row["_m_index"])
        for col in sample_cols:
            val = row[col]
            try:
                v = float(val) if pd.notna(val) else 0.0
            except (TypeError, ValueError):
                v = 0.0
            compound_values[key].setdefault(col, {})[m] = v

    feature_metadata = []
    data_matrix: Dict[str, List[Any]] = {}
    sorted_keys = sorted(compound_meta.keys())

    for key in sorted_keys:
        meta = compound_meta[key]
        feature_metadata.append({k: _to_json_safe(v) for k, v in meta.items()})
        values = compound_values[key]
        for col in sample_cols:
            col_values = values.get(col, {})
            for m in range(max_m + 1):
                new_col = f"{col}_M+{m}"
                data_matrix.setdefault(new_col, []).append(_to_json_safe(col_values.get(m, 0.0)))

    sample_metadata = {f"{col}_M+{m}": sample_groups[col] for col in sample_cols for m in range(max_m + 1)}

    processing_history.append({
        "step": "import",
        "format": "el_maven",
        "source": source_name,
        "compounds": len(feature_metadata),
        "max_label": max_m,
    })

    return {
        "feature_metadata": feature_metadata,
        "data_matrix": data_matrix,
        "sample_metadata": sample_metadata,
        "processing_history": processing_history,
    }


async def import_dataset(
    db: AsyncSession,
    uploaded: models.UploadedFile,
    feature_type: str = "metabolite",
    metadata_path: str = None,
):
    path = await storage.get_file_path(uploaded.stored_name, db)
    df = read_file_to_df(path, uploaded.selected_sheet)

    metadata = None
    if metadata_path:
        metadata = parse_sample_metadata(metadata_path)

    detected = detect_columns(df, metadata=metadata)

    # El-MAVEN isotopologue exports are pivoted into M+0/M+1... columns per sample.
    if _is_el_maven_df(df) or uploaded.detected_format == "el_maven":
        pivoted = _pivot_el_maven(
            df,
            source_name=uploaded.original_name,
            feature_type=feature_type,
            processing_history=[{"step": "import", "source": uploaded.original_name}],
        )
        dataset = models.Dataset(
            project_id=uploaded.project_id,
            source_file_id=uploaded.id,
            name=uploaded.original_name,
            feature_type=feature_type,
            data_matrix=pivoted["data_matrix"],
            sample_metadata=pivoted["sample_metadata"],
            feature_metadata=pivoted["feature_metadata"],
            processing_history=pivoted["processing_history"],
        )
        db.add(dataset)
        uploaded.status = "imported"
        await db.commit()
        await db.refresh(dataset)
        return dataset

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

    # Rename LipidSearch bracketed area columns (e.g. "OriginalArea[s1-1]") to the raw
    # sample name from the alignment file when available; otherwise use the sample id.
    sample_aliases: dict[str, str] = {}
    used_names: set[str] = set()
    for col in sample_cols:
        m = LIPIDSEARCH_AREA_RE.match(str(col))
        if m:
            sid = _normalize_lipidsearch_sample_id(m.group("sample"))
            new_col = sid
            if metadata and sid in metadata:
                new_col = metadata[sid].get("raw_name") or sid
            if new_col and new_col not in used_names:
                sample_aliases[col] = new_col
                used_names.add(new_col)
            else:
                sample_aliases[col] = col
                used_names.add(col)
        else:
            sample_aliases[col] = col
            used_names.add(col)

    if any(k != v for k, v in sample_aliases.items()):
        df = df.rename(columns=sample_aliases)
        sample_cols = [sample_aliases[c] for c in sample_cols]
        detected["sample_groups"] = {sample_aliases.get(k, k): v for k, v in detected["sample_groups"].items()}

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

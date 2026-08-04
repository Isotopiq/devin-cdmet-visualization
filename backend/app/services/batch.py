import copy
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from scipy import stats

from app import models
from app.services.preprocessing import _to_json_safe


VALID_BATCH_METHODS = {
    "reference_group",
    "log2fc_control",
    "mean_centering",
    "median_centering",
    "quantile_normalization",
}


def _positive_floor(df: pd.DataFrame) -> float:
    pos = df.values[df.values > 0]
    if pos.size == 0:
        return 1e-12
    return float(np.nanmin(pos))


def _feature_id(meta: Dict[str, Any]) -> str:
    return str(meta.get("feature_id", "")).strip()


def _unique_feature_ids(feature_metadata: List[Dict[str, Any]], dataset_id: int) -> List[str]:
    """Return a list of unique feature IDs; duplicates get a numeric suffix."""
    ids = []
    seen = {}
    for i, meta in enumerate(feature_metadata):
        fid = _feature_id(meta)
        if not fid:
            fid = f"feature_{dataset_id}_{i}"
        if fid in seen:
            seen[fid] += 1
            fid = f"{fid}_{seen[fid]}"
        else:
            seen[fid] = 0
        ids.append(fid)
    return ids


def _unique_sample_name(col: str, batch_label: str, used: set) -> str:
    col = str(col)
    batch_label = str(batch_label).strip() or "batch"
    candidate = col
    if candidate in used:
        candidate = f"{col}_{batch_label}"
    i = 2
    while candidate in used:
        candidate = f"{col}_{batch_label}_{i}"
        i += 1
    return candidate


def _build_combined_frame(
    datasets: List[models.Dataset],
    batch_assignment: Optional[Dict[str, str]],
) -> tuple[pd.DataFrame, Dict[str, str], Dict[str, str], List[Dict[str, Any]]]:
    """Return combined DataFrame, sample metadata, sample->batch map, and feature metadata."""
    batch_assignment = {int(k): v for k, v in (batch_assignment or {}).items()}
    frames: List[pd.DataFrame] = []
    sample_meta: Dict[str, str] = {}
    sample_batch: Dict[str, str] = {}
    used_samples: set = set()
    feature_meta_by_id: Dict[str, Dict[str, Any]] = {}

    for dataset in datasets:
        batch_label = (batch_assignment or {}).get(dataset.id)
        if not batch_label:
            batch_label = f"batch_{dataset.id}"
        batch_label = str(batch_label).strip() or f"batch_{dataset.id}"

        df = pd.DataFrame(dataset.data_matrix)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        feature_metadata = dataset.feature_metadata or []
        if len(feature_metadata) != len(df):
            feature_metadata = [
                {"feature_id": f"feature_{i}"} for i in range(len(df))
            ]

        fids = _unique_feature_ids(feature_metadata, dataset.id)
        df.index = fids

        # pick metadata for union of features; prefer first occurrence
        for fid, meta in zip(fids, feature_metadata):
            if fid not in feature_meta_by_id:
                feature_meta_by_id[fid] = copy.deepcopy(meta)

        # rename samples to be unique across combined dataset
        rename_map: Dict[str, str] = {}
        original_meta = dataset.sample_metadata or {}
        for raw_col in df.columns:
            new_col = _unique_sample_name(raw_col, batch_label, used_samples)
            used_samples.add(new_col)
            rename_map[raw_col] = new_col
            sample_meta[new_col] = str(original_meta.get(raw_col, "unknown"))
            sample_batch[new_col] = batch_label

        if rename_map:
            df = df.rename(columns=rename_map)
        frames.append(df)

    combined = pd.concat(frames, axis=1, join="outer", sort=False)
    combined.index = [str(i) for i in combined.index]

    # align feature metadata to combined index
    combined_feature_meta = [
        feature_meta_by_id.get(fid, {"feature_id": fid})
        for fid in combined.index
    ]
    return combined, sample_meta, sample_batch, combined_feature_meta


def _reference_control_scale(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: str,
) -> pd.DataFrame:
    """Divide each sample by the mean of the reference group within its batch."""
    result = df.copy()
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        ref_cols = [c for c in cols if sample_meta.get(c) == reference_group]
        if not ref_cols:
            continue
        ref_mean = df[ref_cols].replace(0, np.nan).mean(axis=1)
        ref_mean = ref_mean.replace(0, np.nan)
        for col in cols:
            result[col] = df[col].replace(0, np.nan).div(ref_mean)
    return result


def _log2fc_control(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: str,
) -> pd.DataFrame:
    """Convert each sample to log2 fold-change vs the batch reference group mean."""
    floor = _positive_floor(df) / 2.0
    result = df.copy()
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        ref_cols = [c for c in cols if sample_meta.get(c) == reference_group]
        if not ref_cols:
            continue
        ref_mean = df[ref_cols].replace(0, np.nan).mean(axis=1)
        ref_mean = ref_mean.replace(0, np.nan).fillna(floor)
        for col in cols:
            values = df[col].replace(0, floor).fillna(floor)
            result[col] = np.log2(values / ref_mean)
    return result


def _mean_center(df: pd.DataFrame, sample_batch: Dict[str, str]) -> pd.DataFrame:
    result = df.copy()
    global_mean = df.replace(0, np.nan).mean(axis=1)
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        if not cols:
            continue
        batch_mean = df[cols].replace(0, np.nan).mean(axis=1)
        scale = global_mean.div(batch_mean)
        scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1)
        for col in cols:
            result[col] = df[col] * scale
    return result


def _median_center(df: pd.DataFrame, sample_batch: Dict[str, str]) -> pd.DataFrame:
    result = df.copy()
    global_median = df.replace(0, np.nan).median(axis=1)
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        if not cols:
            continue
        batch_median = df[cols].replace(0, np.nan).median(axis=1)
        scale = global_median.div(batch_median)
        scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1)
        for col in cols:
            result[col] = df[col] * scale
    return result


def _quantile_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Quantile normalize across columns (samples). NaNs and zeros are filled with a small floor."""
    floor = _positive_floor(df) / 2.0
    filled = df.replace(0, floor).fillna(floor)
    ranks = filled.apply(stats.rankdata, axis=0, method="average")
    sorted_vals = np.sort(filled.values, axis=0)
    rank_means = np.mean(sorted_vals, axis=1)
    # rankdata is 1-indexed; interpolate fractional ranks and map back to sample positions
    ranks_arr = ranks.values
    result_arr = np.interp(
        ranks_arr,
        np.arange(1, len(rank_means) + 1),
        rank_means,
    )
    result = pd.DataFrame(result_arr, index=df.index, columns=df.columns)
    # preserve original NaNs and zeros
    result = result.where(df.notna())
    result = result.where(df != 0, 0)
    return result


def _apply_batch_correction(
    df: pd.DataFrame,
    method: str,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: Optional[str] = None,
) -> pd.DataFrame:
    if method == "reference_group":
        if not reference_group:
            raise HTTPException(status_code=400, detail="reference_group is required for reference_group scaling")
        return _reference_control_scale(df, sample_meta, sample_batch, reference_group)
    if method == "log2fc_control":
        if not reference_group:
            raise HTTPException(status_code=400, detail="reference_group is required for log2fc_control")
        return _log2fc_control(df, sample_meta, sample_batch, reference_group)
    if method == "mean_centering":
        return _mean_center(df, sample_batch)
    if method == "median_centering":
        return _median_center(df, sample_batch)
    if method == "quantile_normalization":
        return _quantile_normalize(df)
    raise HTTPException(status_code=400, detail=f"Unknown batch correction method: {method}")


def _from_combined_df(
    df: pd.DataFrame,
    project_id: int,
    name: str,
    feature_type: str,
    sample_meta: Dict[str, str],
    feature_meta: List[Dict[str, Any]],
    history_step: Dict[str, Any],
) -> models.Dataset:
    data_matrix = {}
    for col in df.columns:
        data_matrix[str(col)] = [_to_json_safe(v) for v in df[col].tolist()]
    return models.Dataset(
        project_id=project_id,
        source_file_id=None,
        name=name,
        feature_type=feature_type,
        data_matrix=data_matrix,
        sample_metadata={str(k): str(v) for k, v in sample_meta.items()},
        feature_metadata=[{k: _to_json_safe(v) for k, v in m.items()} for m in feature_meta],
        processing_history=[history_step],
    )


async def combine_datasets(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    dataset_ids: List[int],
    method: str,
    batch_assignment: Optional[Dict[str, str]],
    reference_group: Optional[str],
    output_name: Optional[str],
) -> models.Dataset:
    if method not in VALID_BATCH_METHODS:
        raise HTTPException(status_code=400, detail=f"Invalid method. Choose from {sorted(VALID_BATCH_METHODS)}")
    if len(dataset_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two datasets are required for batch combination")

    # load datasets
    result = await db.execute(
        select(models.Dataset)
        .join(models.Project)
        .where(
            models.Dataset.id.in_(dataset_ids),
            models.Dataset.project_id == project_id,
            models.Project.owner_id == user_id,
        )
    )
    datasets = result.scalars().all()
    if len(datasets) != len(dataset_ids):
        raise HTTPException(status_code=404, detail="One or more datasets not found")

    combined, sample_meta, sample_batch, feature_meta = _build_combined_frame(
        list(datasets), batch_assignment
    )
    corrected = _apply_batch_correction(combined, method, sample_meta, sample_batch, reference_group)

    # choose a sensible name
    default_name = f"combined_{method}"
    if output_name:
        name = str(output_name).strip()
    else:
        name = default_name

    feature_type = datasets[0].feature_type
    history_step = {
        "step": "batch_combine",
        "method": method,
        "reference_group": reference_group,
        "batch_assignment": batch_assignment,
        "source_dataset_ids": dataset_ids,
        "source_dataset_names": [d.name for d in datasets],
    }

    new_dataset = _from_combined_df(
        corrected,
        project_id,
        name,
        feature_type,
        sample_meta,
        feature_meta,
        history_step,
    )
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset

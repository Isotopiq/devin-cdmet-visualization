import copy
import math
import os
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import HTTPException
from scipy import stats
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas
from app.services import storage
from app.services.isobaric import apply_isobaric_substitution
from app.services.drift import correct_qc_pool_drift, load_run_order_file


def _to_json_safe(value):
    """Replace NaN/Inf with None and numpy scalars with native Python types for JSON storage."""
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(value):
            return None
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, np.ndarray):
        return _to_json_safe(value.tolist())
    return value


def to_dataframe(dataset: models.Dataset) -> pd.DataFrame:
    df = pd.DataFrame(dataset.data_matrix)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _positive_floor(df: pd.DataFrame) -> float:
    """Return a small positive value based on the smallest positive value in df."""
    pos = df.values[df.values > 0]
    if pos.size == 0:
        return 1e-12
    return float(np.nanmin(pos))


def _make_non_negative(df: pd.DataFrame) -> pd.DataFrame:
    """Replace zeros and negative values with a small positive floor."""
    floor = _positive_floor(df) / 2
    return df.where(df > 0, floor)


def from_dataframe(
    df: pd.DataFrame,
    dataset: models.Dataset,
    history_step: dict,
    feature_metadata: Optional[List[Dict[str, Any]]] = None,
    sample_metadata: Optional[Dict[str, Any]] = None,
) -> models.Dataset:
    # Convert any remaining NaN/Inf before storing as JSON
    data_matrix = {}
    for col in df.columns:
        data_matrix[str(col)] = [_to_json_safe(v) for v in df[col].tolist()]

    # Align feature_metadata to the rows that survived filtering/transformation
    original_meta = copy.deepcopy(feature_metadata or dataset.feature_metadata) or []
    new_meta = []
    if len(df) == len(original_meta):
        new_meta = original_meta
    elif df.index.dtype.kind in "iu" or all(isinstance(i, int) for i in df.index):
        for i in df.index:
            if 0 <= i < len(original_meta):
                new_meta.append(original_meta[i])
    else:
        meta_by_fid = {}
        for m in original_meta:
            fid = m.get("feature_id")
            if fid:
                meta_by_fid[fid] = m
        for idx in df.index:
            if isinstance(idx, int) and 0 <= idx < len(original_meta):
                new_meta.append(original_meta[idx])
            else:
                new_meta.append(meta_by_fid.get(str(idx), {"feature_id": str(idx)}))

    new_dataset = models.Dataset(
        project_id=dataset.project_id,
        source_file_id=dataset.source_file_id,
        name=f"{dataset.name}_processed",
        feature_type=dataset.feature_type,
        data_matrix=data_matrix,
        sample_metadata=copy.deepcopy(sample_metadata if sample_metadata is not None else dataset.sample_metadata),
        feature_metadata=new_meta,
        processing_history=copy.deepcopy(dataset.processing_history) + [history_step],
    )
    return new_dataset


def _rename_sample_names(df: pd.DataFrame, sample_metadata: Dict[str, Any]) -> tuple:
    """Rename sample columns to <group>_R<replicate> (e.g. FLVCR1-KO_R1) for easier plotting.

    Samples are ordered within each group by their original column name and assigned
    a sequential replicate number. Group names with spaces are normalized to underscores.
    """
    cols = list(df.columns)
    groups = [sample_metadata.get(c, "Unknown") for c in cols]
    group_to_cols: Dict[str, List[str]] = {}
    for col, group in zip(cols, groups):
        group_to_cols.setdefault(group, []).append(col)

    mapping: Dict[str, str] = {}
    for group, group_cols in group_to_cols.items():
        safe_group = re.sub(r"[^\w\-]+", "_", str(group)).strip("_") or "Sample"
        for i, col in enumerate(sorted(group_cols), start=1):
            new_name = f"{safe_group}_R{i}"
            # Avoid collisions if the new name already exists in another group by appending _<n>.
            base = new_name
            count = 1
            while new_name in mapping.values():
                new_name = f"{base}_{count}"
                count += 1
            mapping[col] = new_name

    df = df.rename(columns=mapping)
    new_metadata = {mapping.get(c, c): g for c, g in sample_metadata.items() if c in mapping}
    return df, new_metadata, mapping


async def _load_normalization_values(file_id: int, sample_columns: List[str], value_column: Optional[str], db: AsyncSession) -> Dict[str, float]:
    """Load per-sample normalization factors from an uploaded metadata file."""
    result = await db.execute(select(models.UploadedFile).where(models.UploadedFile.id == file_id))
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise ValueError(f"Normalization file not found: {file_id}")

    path = await storage.get_file_path(uploaded.stored_name, db)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        df = pd.read_csv(path, sep=None, engine="python")

    if df.empty:
        raise ValueError("Normalization file is empty")

    sample_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("sample", "sample_name", "sample id", "sample_id", "sampleid"):
            sample_col = c
            break
    if sample_col is None:
        sample_col = df.columns[0]

    value_col = None
    if value_column:
        target = str(value_column).strip().lower()
        for c in df.columns:
            if str(c).strip().lower() == target:
                value_col = c
                break
    if value_col is None:
        for c in df.columns:
            if str(c).strip().lower() in ("value", "factor", "amount", "quantity"):
                value_col = c
                break
    if value_col is None:
        value_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    mapping: Dict[str, float] = {}
    for _, row in df.iterrows():
        sample = str(row[sample_col]).strip()
        val = row[value_col]
        if sample and not pd.isna(val):
            mapping[sample] = float(val)

    missing = [c for c in sample_columns if c not in mapping]
    if missing:
        raise ValueError(
            f"Missing normalization values for {len(missing)} sample(s): {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
        )

    zero_samples = [s for s, v in mapping.items() if v == 0]
    if zero_samples:
        raise ValueError(
            f"Normalization values cannot be zero for {len(zero_samples)} sample(s): {', '.join(zero_samples[:5])}{'...' if len(zero_samples) > 5 else ''}"
        )

    return mapping


async def preprocess_dataset(db: AsyncSession, dataset: models.Dataset, params: schemas.PreprocessingParams) -> models.Dataset:
    df = to_dataframe(dataset)
    current_meta: List[Dict[str, Any]] = copy.deepcopy(dataset.feature_metadata) or []
    history = {"step": "preprocessing", "params": params.model_dump()}

    def _sync_meta():
        """Filter current_meta to match the rows remaining in df."""
        nonlocal current_meta
        if len(df) == len(current_meta):
            return
        if all(isinstance(i, int) for i in df.index):
            current_meta = [current_meta[i] for i in df.index if 0 <= i < len(current_meta)]
        else:
            meta_by_fid = {m.get("feature_id"): m for m in current_meta if m.get("feature_id")}
            current_meta = [meta_by_fid.get(str(i), current_meta[i] if isinstance(i, int) and 0 <= i < len(current_meta) else {}) for i in df.index]

    # 1. Missing value filtering: keep features observed in at least threshold samples
    if params.missing_value_filter > 0:
        threshold = int(len(df.columns) * params.missing_value_filter)
        df = df.dropna(thresh=threshold)
        _sync_meta()

    # 2. Blank subtraction (per-feature mean across blanks)
    if params.blank_subtraction and params.blank_columns:
        blank_mean = df[params.blank_columns].mean(axis=1)
        for col in df.columns:
            if col not in params.blank_columns:
                df[col] = df[col] - blank_mean
        df = _make_non_negative(df)

    # 3. QC CV filtering (remove features highly variable across QC samples)
    if params.qc_cv_filter > 0 and params.qc_columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            qc = df[params.qc_columns]
            mean = qc.mean(axis=1)
            std = qc.std(axis=1)
            cv = std / mean
            cv = cv.replace([np.inf, -np.inf], np.nan).fillna(np.inf)
        df = df[cv <= params.qc_cv_filter]
        _sync_meta()

    # 3.5 Isobaric substitution rule engine (lipidomics only)
    if params.enable_isobaric_substitution_check:
        isobaric_config = params.model_dump()
        isobaric_config["feature_type"] = dataset.feature_type
        df, current_meta, isobaric_summary = apply_isobaric_substitution(df, current_meta, isobaric_config)
        history.setdefault("isobaric_substitution", isobaric_summary)

    # 4. Duplicate handling by feature_id when available
    if params.duplicate_handling == "mean" and current_meta:
        feature_ids = [m.get("feature_id", i) for i, m in enumerate(current_meta)]
        if all(isinstance(i, int) and i < len(feature_ids) for i in df.index):
            df = df.copy()
            df["_feature_id"] = [feature_ids[i] for i in df.index]
            df = df.groupby("_feature_id").mean(numeric_only=True)
            df = df.drop(columns=["_feature_id"], errors="ignore")
            # Align metadata to the new row order.
            meta_by_fid = {m.get("feature_id"): m for m in current_meta if m.get("feature_id") is not None}
            current_meta = [meta_by_fid.get(fid, {}) for fid in df.index]

    # 5. Imputation (before normalization/log to keep values interpretable)
    if params.imputation == "min":
        pos_floor = _positive_floor(df) / 2
        df = df.fillna(pos_floor)
    elif params.imputation == "median":
        df = df.fillna(df.median())
    elif params.imputation == "knn":
        df = df.fillna(df.mean())

    # Ensure no negative values remain before normalization/log
    df = _make_non_negative(df)

    # 6. QC-Pool drift correction (optional, on positive raw intensities)
    if params.qc_pool_drift_correction:
        run_order = params.qc_pool_run_order or None
        if params.qc_pool_run_order_file_id:
            run_order = await load_run_order_file(db, params.qc_pool_run_order_file_id, df.columns.tolist())
        df, drift_diagnostics = correct_qc_pool_drift(
            df,
            dataset.sample_metadata or {},
            params,
            run_order=run_order,
        )
        history["qc_pool_drift"] = drift_diagnostics

    # 7. Normalization (on raw, non-logged sample totals)
    NORMALIZATION_BY_SAMPLE = {"internal_standard", "protein", "dna", "cell_number", "tissue_weight"}
    if params.normalization == "total_area":
        sample_sums = df.sum(axis=0)
        sample_sums = sample_sums.replace(0, np.nan)
        if sample_sums.notna().any():
            df = df.div(sample_sums, axis=1) * sample_sums.median()
        df = df.fillna(0)
    elif params.normalization == "custom_factor" and params.custom_factor:
        df = df / float(params.custom_factor)
    elif params.normalization in NORMALIZATION_BY_SAMPLE:
        if not params.normalization_file_id:
            raise HTTPException(status_code=400, detail=f"Normalization '{params.normalization}' requires an uploaded metadata file with per-sample values")
        values = await _load_normalization_values(params.normalization_file_id, df.columns.tolist(), params.normalization_column, db)
        factors = pd.Series({col: values.get(col, np.nan) for col in df.columns})
        factors = factors.replace(0, np.nan)
        median_factor = float(factors.median()) if not factors.isna().all() else 1.0
        if pd.isna(median_factor) or median_factor == 0:
            raise HTTPException(status_code=400, detail="No valid normalization factors found in uploaded file")
        df = df.div(factors, axis=1) * median_factor
        df = df.fillna(0)
        history["normalization_values"] = values

    # 7. Log transformation
    if params.log_transform:
        pos_floor = _positive_floor(df) / 2
        df = df.where(df > 0, pos_floor)
        df = np.log2(df)

    # 8. Batch correction (median-center per batch when batch labels are supplied)
    if params.batch_correction == "mean" and params.batch_labels:
        batch_df = pd.DataFrame({col: [params.batch_labels.get(col, "unknown")] for col in df.columns}, index=["batch"]).T
        for batch, cols in df.columns.to_series().groupby(batch_df["batch"]).items():
            if not cols:
                continue
            batch_median = df[cols].median(axis=1).replace(0, np.nan)
            global_median = df.median(axis=1)
            scale = global_median / batch_median
            scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1)
            for col in cols:
                df[col] = df[col] * scale

    # 9. Scaling (per feature, i.e. across samples; df rows are features)
    if params.scale == "standard":
        df = pd.DataFrame(StandardScaler().fit_transform(df.T).T, index=df.index, columns=df.columns)
    elif params.scale == "robust":
        df = pd.DataFrame(RobustScaler().fit_transform(df.T).T, index=df.index, columns=df.columns)
    elif params.scale == "minmax":
        df = pd.DataFrame(MinMaxScaler().fit_transform(df.T).T, index=df.index, columns=df.columns)

    # 10. Optional sample renaming to group_R<replicate>
    renamed_metadata = None
    if params.rename_samples:
        df, renamed_metadata, _ = _rename_sample_names(df, dataset.sample_metadata)

    new_dataset = from_dataframe(df, dataset, history, feature_metadata=current_meta, sample_metadata=renamed_metadata)
    if params.output_name:
        new_dataset.name = params.output_name
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset

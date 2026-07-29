import copy
import math
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas


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


def from_dataframe(df: pd.DataFrame, dataset: models.Dataset, history_step: dict) -> models.Dataset:
    # Convert any remaining NaN/Inf before storing as JSON
    data_matrix = {}
    for col in df.columns:
        data_matrix[str(col)] = [_to_json_safe(v) for v in df[col].tolist()]

    new_dataset = models.Dataset(
        project_id=dataset.project_id,
        source_file_id=dataset.source_file_id,
        name=f"{dataset.name}_processed",
        feature_type=dataset.feature_type,
        data_matrix=data_matrix,
        sample_metadata=copy.deepcopy(dataset.sample_metadata),
        feature_metadata=copy.deepcopy(dataset.feature_metadata),
        processing_history=copy.deepcopy(dataset.processing_history) + [history_step],
    )
    return new_dataset


async def preprocess_dataset(db: AsyncSession, dataset: models.Dataset, params: schemas.PreprocessingParams) -> models.Dataset:
    df = to_dataframe(dataset)
    history = {"step": "preprocessing", "params": params.model_dump()}

    # 1. Missing value filtering: keep features observed in at least threshold samples
    if params.missing_value_filter > 0:
        threshold = int(len(df.columns) * params.missing_value_filter)
        df = df.dropna(thresh=threshold)

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

    # 4. Duplicate handling by feature_id when available
    if params.duplicate_handling == "mean" and dataset.feature_metadata:
        feature_ids = [m.get("feature_id", i) for i, m in enumerate(dataset.feature_metadata)]
        if all(isinstance(i, int) and i < len(feature_ids) for i in df.index):
            df = df.copy()
            df["_feature_id"] = [feature_ids[i] for i in df.index]
            df = df.groupby("_feature_id").mean(numeric_only=True)
            df = df.drop(columns=["_feature_id"], errors="ignore")

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

    # 6. Normalization (on raw, non-logged sample totals)
    if params.normalization == "total_area":
        sample_sums = df.sum(axis=0)
        sample_sums = sample_sums.replace(0, np.nan)
        if sample_sums.notna().any():
            df = df.div(sample_sums, axis=1) * sample_sums.median()
        df = df.fillna(0)
    elif params.normalization == "custom_factor" and params.custom_factor:
        df = df / float(params.custom_factor)

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

    # 9. Scaling
    if params.scale == "standard":
        df = pd.DataFrame(StandardScaler().fit_transform(df), columns=df.columns, index=df.index)
    elif params.scale == "robust":
        df = pd.DataFrame(RobustScaler().fit_transform(df), columns=df.columns, index=df.index)
    elif params.scale == "minmax":
        df = pd.DataFrame(MinMaxScaler().fit_transform(df), columns=df.columns, index=df.index)

    new_dataset = from_dataframe(df, dataset, history)
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset

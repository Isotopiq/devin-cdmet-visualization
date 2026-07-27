import copy
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas


def to_dataframe(dataset: models.Dataset) -> pd.DataFrame:
    df = pd.DataFrame(dataset.data_matrix)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def from_dataframe(df: pd.DataFrame, dataset: models.Dataset, history_step: dict) -> models.Dataset:
    data_matrix = {col: df[col].tolist() for col in df.columns}
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

    if params.missing_value_filter > 0:
        threshold = int(len(df.columns) * params.missing_value_filter)
        df = df.dropna(thresh=threshold)

    if params.blank_subtraction and params.blank_columns:
        blank_mean = df[params.blank_columns].mean(axis=1)
        for col in df.columns:
            if col not in params.blank_columns:
                df[col] = df[col] - blank_mean

    if params.qc_cv_filter > 0 and params.qc_columns:
        cv = df[params.qc_columns].std(axis=1) / df[params.qc_columns].mean(axis=1)
        df = df[cv <= params.qc_cv_filter]

    if params.duplicate_handling == "mean":
        df = df.groupby(df.index).mean()

    if params.imputation == "min":
        df = df.fillna(df.min().min() / 2)
    elif params.imputation == "median":
        df = df.fillna(df.median())
    elif params.imputation == "knn":
        df = df.fillna(df.mean())

    if params.log_transform:
        df = np.log2(df.replace(0, np.nanmin(df.values[df.values > 0]) / 2))

    if params.scale == "standard":
        df = pd.DataFrame(StandardScaler().fit_transform(df), columns=df.columns, index=df.index)
    elif params.scale == "robust":
        df = pd.DataFrame(RobustScaler().fit_transform(df), columns=df.columns, index=df.index)
    elif params.scale == "minmax":
        df = pd.DataFrame(MinMaxScaler().fit_transform(df), columns=df.columns, index=df.index)

    if params.normalization == "total_area":
        df = df.div(df.sum(axis=0), axis=1)
    elif params.normalization == "custom_factor" and params.custom_factor:
        df = df / params.custom_factor

    if params.batch_correction == "mean" and params.batch_column:
        group = df.groupby(params.batch_column, axis=1)
        df = group.transform(lambda x: x / x.mean())

    new_dataset = from_dataframe(df, dataset, history)
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset

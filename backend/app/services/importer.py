import os
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.services.detection import read_file_to_df, detect_columns, parse_lipidsearch_alignment


async def import_dataset(
    db: AsyncSession,
    uploaded: models.UploadedFile,
    feature_type: str = "metabolite",
    alignment_path: str = None,
):
    path = os.path.join("uploads", uploaded.stored_name)
    df = read_file_to_df(path, uploaded.selected_sheet)

    alignment = None
    if alignment_path:
        alignment = parse_lipidsearch_alignment(alignment_path)

    detected = detect_columns(df, alignment=alignment)

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

    feature_metadata = []
    for _, row in df.iterrows():
        meta = {"feature_id": str(row.get(feature_id_col, ""))}
        for key in ["formula", "mz", "rt", "adduct", "lipid_class", "grade", "fa"]:
            col = mapping.get(key) or detected["suggested_mapping"].get(key)
            if col and col in row:
                meta[key] = row[col]
        feature_metadata.append(meta)

    data_matrix = {}
    for col in sample_cols:
        data_matrix[str(col)] = [
            None if pd.isna(v) else v for v in pd.to_numeric(df[col], errors="coerce").tolist()
        ]

    sample_groups = mapping.get("sample_groups") or detected["sample_groups"]
    sample_metadata = {str(col): sample_groups.get(str(col), "unknown") for col in sample_cols}

    def _clean_meta(value):
        if pd.isna(value):
            return None
        if isinstance(value, float):
            if pd.isna(value):
                return None
        return value

    feature_metadata = [
        {k: _clean_meta(v) for k, v in meta.items()} for meta in feature_metadata
    ]

    dataset = models.Dataset(
        project_id=uploaded.project_id,
        source_file_id=uploaded.id,
        name=uploaded.original_name,
        feature_type=feature_type,
        data_matrix=data_matrix,
        sample_metadata=sample_metadata,
        feature_metadata=feature_metadata,
        processing_history=[{"step": "import", "source": uploaded.original_name}],
    )
    db.add(dataset)
    uploaded.status = "imported"
    await db.commit()
    await db.refresh(dataset)
    return dataset

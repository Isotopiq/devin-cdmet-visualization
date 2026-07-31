import io
import csv
import math
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.preprocessing import preprocess_dataset, to_dataframe
from app.services.qc import qc_analysis

router = APIRouter()


@router.get("/{project_id}/dataset/{dataset_id}", response_model=schemas.DatasetOut)
async def get_dataset(project_id: int, dataset_id: int, db: AsyncSession = Depends(get_db),
                      current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.put("/{project_id}/dataset/{dataset_id}/sample_groups", response_model=schemas.DatasetOut)
async def update_sample_groups(
    project_id: int,
    dataset_id: int,
    body: schemas.SampleGroupsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id,
        models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id,
    ))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Only allow updating group labels for existing sample columns.
    existing = set(dataset.sample_metadata or {})
    if not existing:
        raise HTTPException(status_code=400, detail="Dataset has no sample metadata")
    sample_metadata = {col: str(body.sample_metadata.get(col, dataset.sample_metadata.get(col, "unknown"))) for col in existing}
    dataset.sample_metadata = sample_metadata
    dataset.processing_history = list(dataset.processing_history or []) + [{"step": "update_sample_groups", "updated": list(sample_metadata.values())}]
    await db.commit()
    await db.refresh(dataset)
    return dataset


@router.post("/{project_id}/dataset/{dataset_id}/preprocess", response_model=schemas.DatasetOut)
async def preprocess(project_id: int, dataset_id: int, params: schemas.PreprocessingParams,
                     db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    new_dataset = await preprocess_dataset(db, dataset, params)
    return new_dataset


@router.get("/{project_id}/datasets", response_model=List[schemas.DatasetOut])
async def list_datasets(project_id: int, db: AsyncSession = Depends(get_db),
                        current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    return result.scalars().all()


@router.get("/{project_id}/dataset/{dataset_id}/qc")
async def get_qc(
    project_id: int,
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return qc_analysis(dataset)


@router.delete("/{project_id}/dataset/{dataset_id}")
async def delete_dataset(project_id: int, dataset_id: int, db: AsyncSession = Depends(get_db),
                         current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.delete(dataset)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/analyses", response_model=List[schemas.AnalysisOut])
async def list_analyses(project_id: int, db: AsyncSession = Depends(get_db),
                        current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Analysis).join(models.Project).where(
        models.Analysis.project_id == project_id, models.Project.owner_id == current_user.id))
    return result.scalars().all()


def _fmt_export_value(v, floor: float) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return ""
    if f <= 0:
        f = floor / 2.0
    s = f"{f:.12f}".rstrip("0").rstrip(".")
    return s if s else "0"


@router.get("/{project_id}/dataset/{dataset_id}/export")
async def export_dataset(
    project_id: int,
    dataset_id: int,
    format: Literal["metaboanalyst", "lipidone"] = Query("metaboanalyst"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    df = to_dataframe(dataset)
    for step in dataset.processing_history or []:
        if not isinstance(step, dict):
            continue
        params = step.get("params", {}) or {}
        if params.get("scale") in ("standard", "robust", "minmax"):
            raise HTTPException(
                status_code=400,
                detail="Cannot export scaled data as intensities. Select the original/unprocessed dataset.",
            )
        if params.get("log_transform"):
            df = 2 ** df

    pos = df.values[df.values > 0]
    floor = float(pos.min()) if pos.size else 1e-12

    samples = df.columns.tolist()
    groups = [str(dataset.sample_metadata.get(s, "unknown")) for s in samples]
    header_key = "Sample" if format == "metaboanalyst" else "Lipid"
    header = [header_key] + samples
    label_row = ["Label"] + groups

    feature_ids = [m.get("feature_id", f"feature_{i}") for i, m in enumerate(dataset.feature_metadata or [])]
    if len(feature_ids) != len(df):
        feature_ids = [f"feature_{i}" for i in range(len(df))]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerow(label_row)
    for i, fid in enumerate(feature_ids):
        row = [fid] + [_fmt_export_value(df.at[i, s], floor) for s in samples]
        writer.writerow(row)

    out.seek(0)
    safe_name = str(dataset.name).replace(" ", "_").replace(",", "")
    filename = f"{safe_name}_{format}.csv"
    return StreamingResponse(
        iter([out.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

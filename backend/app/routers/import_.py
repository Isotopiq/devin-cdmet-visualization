import os
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.detection import preview_file, detect_columns, parse_sample_metadata
from app.services.importer import import_dataset

router = APIRouter()


def _uploaded_file_path(uploaded: models.UploadedFile) -> str:
    return os.path.join("uploads", uploaded.stored_name)


@router.get("/{file_id}/preview", response_model=schemas.ImportPreview)
async def preview_import(
    file_id: int,
    sheet: str = None,
    alignment_file_id: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(models.UploadedFile)
        .join(models.Project)
        .where(models.UploadedFile.id == file_id, models.Project.owner_id == current_user.id)
    )
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=404, detail="File not found")

    metadata = None
    if alignment_file_id:
        res = await db.execute(
            select(models.UploadedFile)
            .join(models.Project)
            .where(models.UploadedFile.id == alignment_file_id, models.Project.owner_id == current_user.id)
        )
        meta_file = res.scalar_one_or_none()
        if meta_file:
            metadata = parse_sample_metadata(_uploaded_file_path(meta_file))

    if sheet:
        uploaded.selected_sheet = sheet
        await db.commit()

    preview = preview_file(uploaded, sheet, metadata=metadata)
    return preview


@router.post("/{file_id}/map", response_model=Dict[str, Any])
async def map_columns(
    file_id: int,
    mapping: schemas.ColumnMapping,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(models.UploadedFile)
        .join(models.Project)
        .where(models.UploadedFile.id == file_id, models.Project.owner_id == current_user.id)
    )
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=404, detail="File not found")

    uploaded.column_mapping = mapping.model_dump()
    await db.commit()
    return {"ok": True}


@router.post("/{file_id}/import", response_model=schemas.DatasetOut)
async def run_import(
    file_id: int,
    feature_type: str = "metabolite",
    sheet: str = None,
    alignment_file_id: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(models.UploadedFile)
        .join(models.Project)
        .where(models.UploadedFile.id == file_id, models.Project.owner_id == current_user.id)
    )
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=404, detail="File not found")

    if sheet:
        uploaded.selected_sheet = sheet

    metadata_path = None
    if alignment_file_id:
        res = await db.execute(
            select(models.UploadedFile)
            .join(models.Project)
            .where(models.UploadedFile.id == alignment_file_id, models.Project.owner_id == current_user.id)
        )
        meta_file = res.scalar_one_or_none()
        if meta_file:
            metadata_path = _uploaded_file_path(meta_file)

    dataset = await import_dataset(db, uploaded, feature_type, metadata_path=metadata_path)
    return dataset

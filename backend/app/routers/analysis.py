from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.preprocessing import preprocess_dataset

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


@router.get("/{project_id}/analyses", response_model=List[schemas.AnalysisOut])
async def list_analyses(project_id: int, db: AsyncSession = Depends(get_db),
                        current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Analysis).join(models.Project).where(
        models.Analysis.project_id == project_id, models.Project.owner_id == current_user.id))
    return result.scalars().all()

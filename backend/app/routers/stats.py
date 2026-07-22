from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.stats import run_statistical_test

router = APIRouter()


@router.post("/{project_id}/dataset/{dataset_id}/stats", response_model=Dict[str, Any])
async def stats(project_id: int, dataset_id: int, req: schemas.StatsRequest,
                db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    results = run_statistical_test(dataset, req)
    analysis = models.Analysis(
        project_id=project_id,
        dataset_id=dataset_id,
        name=f"{req.test}_{req.group_a}_{req.group_b}",
        analysis_type="stats",
        parameters=req.model_dump(),
        results=results,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return results

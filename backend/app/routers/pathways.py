from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.pathways import create_pathway_job, run_pathway_job, get_job

router = APIRouter()


@router.post("/{project_id}/dataset/{dataset_id}/pathway", response_model=Dict[str, Any])
async def pathway(
    project_id: int,
    dataset_id: int,
    req: schemas.PathwayRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(models.Dataset)
        .join(models.Project)
        .where(
            models.Dataset.id == dataset_id,
            models.Dataset.project_id == project_id,
            models.Project.owner_id == current_user.id,
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    job_id = create_pathway_job(dataset, req, owner_id=current_user.id)
    background_tasks.add_task(run_pathway_job, job_id, dataset, req)
    return {"job_id": job_id, "status": "queued"}


@router.get("/job/{job_id}", response_model=Dict[str, Any])
async def get_pathway_job(job_id: str, current_user: models.User = Depends(get_current_active_user)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("owner_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    return job

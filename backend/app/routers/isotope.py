from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.isotope import run_isotope_analysis
from app.services.flux_map import (
    list_bigg_models,
    list_gem_models,
    get_model_summary,
)

router = APIRouter()


@router.post("/{project_id}/dataset/{dataset_id}/isotope", response_model=Dict[str, Any])
async def isotope(
    project_id: int,
    dataset_id: int,
    req: schemas.IsotopeRequest,
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

    results = await run_isotope_analysis(dataset, req)
    if "error" in results:
        return results

    analysis = models.Analysis(
        project_id=project_id,
        dataset_id=dataset_id,
        name=f"isotope_{req.tracer}",
        analysis_type="isotope",
        parameters=req.model_dump(),
        results=results,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return results


@router.get("/bigg_models", response_model=Dict[str, Any])
async def bigg_models(
    q: Optional[str] = None,
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user),
):
    return {"models": await list_bigg_models(q, limit)}


@router.get("/gem_models", response_model=Dict[str, Any])
async def gem_models(
    q: Optional[str] = None,
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user),
):
    return {"models": list_gem_models(q, limit)}


@router.get("/models/{source}/{model_id}/network", response_model=Dict[str, Any])
async def model_network(
    source: str,
    model_id: str,
    current_user: models.User = Depends(get_current_active_user),
):
    if source not in ("bigg", "gem"):
        raise HTTPException(status_code=400, detail="source must be 'bigg' or 'gem'")
    try:
        return await get_model_summary(source, model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

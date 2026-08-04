import io
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.pathways import create_pathway_job, run_pathway_job, get_job
from app.services.pdf_report import build_pathway_pdf, get_pdf_footer_logo_path

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


@router.post("/{project_id}/dataset/{dataset_id}/pathway/pdf")
async def pathway_pdf(
    project_id: int,
    dataset_id: int,
    body: schemas.PathwayPdfRequest,
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

    footer_logo_path = await get_pdf_footer_logo_path(db)
    pdf_bytes = build_pathway_pdf(
        body.result,
        dataset_name=dataset.name,
        title=body.title,
        subtitle=body.subtitle,
        primary_comparison=body.primary_comparison,
        prepared_for=body.prepared_for,
        prepared_by=body.prepared_by,
        report_contents=body.report_contents,
        report_type=body.report_type,
        description=body.description,
        cover_style=body.cover_style,
        font_family=body.font_family,
        include_table=body.include_table,
        footer_logo_path=footer_logo_path,
    )
    filename = f"{dataset.name.replace(' ', '_')}_pathway_report.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

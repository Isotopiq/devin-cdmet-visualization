import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services import storage

router = APIRouter()


@router.get("/", response_model=List[schemas.ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Project).where(models.Project.owner_id == current_user.id))
    return result.scalars().all()


@router.post("/", response_model=schemas.ProjectOut)
async def create_project(project_in: schemas.ProjectCreate, db: AsyncSession = Depends(get_db),
                         current_user: models.User = Depends(get_current_active_user)):
    project = models.Project(name=project_in.name, description=project_in.description, owner_id=current_user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=schemas.ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db),
                      current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
async def update_project(project_id: int, project_in: schemas.ProjectUpdate, db: AsyncSession = Depends(get_db),
                         current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_in.name is not None:
        if not project_in.name.strip():
            raise HTTPException(status_code=400, detail="Project name cannot be empty")
        project.name = project_in.name.strip()
    if project_in.description is not None:
        project.description = project_in.description
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db),
                         current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/reports", response_model=List[schemas.GeneratedReportOut])
async def list_project_reports(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    reports = await storage.list_reports(db, project_id=project_id)
    return reports


@router.get("/{project_id}/reports/{report_id}")
async def download_project_report(
    project_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = await storage.get_report(db, report_id)
    if not report or report.project_id != project_id:
        raise HTTPException(status_code=404, detail="Report not found")
    data = await storage.download_report_bytes(report, db)
    headers = {"Content-Disposition": f"attachment; filename={report.name}"}
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers=headers)


@router.delete("/{project_id}/reports/{report_id}")
async def delete_project_report(
    project_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = await storage.get_report(db, report_id)
    if not report or report.project_id != project_id:
        raise HTTPException(status_code=404, detail="Report not found")
    await storage.delete_report(report, db)
    return {"ok": True}

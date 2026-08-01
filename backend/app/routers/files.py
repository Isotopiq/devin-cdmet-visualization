import os
import shutil
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.detection import detect_file_format
from app.services import storage

router = APIRouter()


@router.post("/{project_id}/upload", response_model=schemas.UploadedFileOut)
async def upload_file(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                      current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Project).where(models.Project.id == project_id, models.Project.owner_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ext = os.path.splitext(file.filename)[1].lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    staging_path = os.path.join(settings.UPLOAD_DIR, stored_name)
    with open(staging_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    detection = detect_file_format(staging_path, ext)
    stored_ref = await storage.save_upload(staging_path, stored_name, db)
    uploaded = models.UploadedFile(
        project_id=project_id,
        original_name=file.filename,
        stored_name=stored_ref,
        file_type=ext.lstrip("."),
        detected_format=detection.get("format"),
        sheets=detection.get("sheets", []),
        status="uploaded",
    )
    db.add(uploaded)
    await db.commit()
    await db.refresh(uploaded)
    return uploaded


@router.get("/{project_id}", response_model=List[schemas.UploadedFileOut])
async def list_files(project_id: int, db: AsyncSession = Depends(get_db),
                     current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.UploadedFile).join(models.Project).where(
        models.UploadedFile.project_id == project_id, models.Project.owner_id == current_user.id))
    return result.scalars().all()


@router.delete("/{file_id}")
async def delete_file(file_id: int, db: AsyncSession = Depends(get_db),
                    current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.UploadedFile).join(models.Project).where(
        models.UploadedFile.id == file_id, models.Project.owner_id == current_user.id))
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=404, detail="File not found")
    await storage.delete_file(uploaded.stored_name, db)
    await db.delete(uploaded)
    await db.commit()
    return {"ok": True}

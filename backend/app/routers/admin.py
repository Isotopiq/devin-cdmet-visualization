import os
import shutil
import datetime as dt
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import get_db
from app import schemas, models
from app.auth import get_current_admin_user, get_password_hash
from app.config import settings
from app.services.email import encrypt_smtp_password, get_smtp_config
from app.services.storage import encrypt_setting as _encrypt_setting, get_storage_config

router = APIRouter()


def _logo_dir():
    path = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(path, exist_ok=True)
    return path


async def _get_setting(db: AsyncSession, key: str) -> Optional[models.SiteSetting]:
    result = await db.execute(select(models.SiteSetting).where(models.SiteSetting.key == key))
    return result.scalar_one_or_none()


async def _set_setting(db: AsyncSession, key: str, value: str) -> models.SiteSetting:
    setting = await _get_setting(db, key)
    if setting is None:
        setting = models.SiteSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    await db.commit()
    await db.refresh(setting)
    return setting


async def _log(db: AsyncSession, action: str, user: models.User, target_user_id: Optional[int] = None, details: dict = None):
    log = models.AdminLog(
        user_id=user.id,
        action=action,
        target_user_id=target_user_id,
        details=details or {},
    )
    db.add(log)
    await db.commit()


@router.get("/users", response_model=list[schemas.UserOut])
async def list_users(db: AsyncSession = Depends(get_db), admin: models.User = Depends(get_current_admin_user)):
    result = await db.execute(select(models.User))
    return result.scalars().all()


@router.post("/users", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: schemas.UserAdminCreate,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    result = await db.execute(select(models.User).where(models.User.email == user_in.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(
        email=user_in.email,
        name=user_in.name.strip() if user_in.name else None,
        hashed_password=get_password_hash(user_in.password),
        is_active=user_in.is_active,
        is_admin=user_in.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await _log(db, "create_user", admin, target_user_id=user.id, details={"email": user.email, "name": user.name})
    return user


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
async def update_user(
    user_id: int,
    user_in: schemas.UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email == admin.email and user_in.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin role")
    if user_in.email is not None:
        result = await db.execute(select(models.User).where(models.User.email == user_in.email))
        existing = result.scalar_one_or_none()
        if existing and existing.id != user_id:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = user_in.email
    if user_in.name is not None:
        user.name = user_in.name.strip() or None
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.is_admin is not None:
        user.is_admin = user_in.is_admin
    await db.commit()
    await db.refresh(user)
    await _log(db, "update_user", admin, target_user_id=user.id, details=user_in.model_dump(exclude_unset=True))
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await _log(db, "delete_user", admin, target_user_id=user.id, details={"email": user.email})
    await db.delete(user)
    await db.commit()
    return {"ok": True}


@router.get("/logs", response_model=list[schemas.AdminLogOut])
async def list_logs(
    user_id: Optional[int] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    query = select(models.AdminLog).order_by(models.AdminLog.created_at.desc())
    if user_id:
        query = query.where(
            (models.AdminLog.user_id == user_id) | (models.AdminLog.target_user_id == user_id)
        )
    result = await db.execute(query.limit(limit))
    logs = result.scalars().all()
    user_ids = {log.user_id for log in logs if log.user_id}
    user_ids |= {log.target_user_id for log in logs if log.target_user_id}
    if user_id:
        user_ids.add(user_id)
    emails = {}
    if user_ids:
        user_result = await db.execute(select(models.User.id, models.User.email).where(models.User.id.in_(user_ids)))
        emails = {uid: email for uid, email in user_result.all()}
    return [
        schemas.AdminLogOut(
            id=log.id,
            user_id=log.user_id,
            user_email=emails.get(log.user_id),
            action=log.action,
            target_user_id=log.target_user_id,
            target_user_email=emails.get(log.target_user_id),
            details=log.details or {},
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.delete("/logs")
async def clear_logs(
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    if user_id:
        await db.execute(
            delete(models.AdminLog).where(
                (models.AdminLog.user_id == user_id) | (models.AdminLog.target_user_id == user_id)
            )
        )
        detail = f"Cleared logs for user {user_id}"
    else:
        await db.execute(delete(models.AdminLog))
        detail = "Cleared all admin logs"
    await db.commit()
    await _log(db, "clear_logs", admin, details={"user_id": user_id, "cleared_by": admin.email})
    return {"ok": True, "detail": detail}


def _logo_content_type(filename: str, raw_content_type: Optional[str]) -> str:
    if raw_content_type and raw_content_type != "application/octet-stream":
        return raw_content_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _logo_ext(filename: str, content_type: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower() if "." in filename else ""
    if ext in ("png", "jpg", "jpeg", "svg", "ico"):
        return "jpg" if ext == "jpeg" else ext
    ct_ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/svg+xml": "svg", "image/x-icon": "ico"}
    return ct_ext.get(content_type, "png")


def _file_response(path: str) -> FileResponse:
    media_type, _ = mimetypes.guess_type(path)
    response = FileResponse(path, media_type=media_type or "image/png")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.post("/logo/{logo_type}")
async def upload_logo(
    logo_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    if logo_type not in ("login", "dashboard"):
        raise HTTPException(status_code=400, detail="logo_type must be 'login' or 'dashboard'")
    content_type = _logo_content_type(file.filename or "", file.content_type)
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/svg+xml"}
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or SVG logos are allowed")
    ext = _logo_ext(file.filename or "", content_type)
    stored_name = f"{logo_type}_logo_{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    dest_path = os.path.join(_logo_dir(), stored_name)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Clean up previous logo files for this type
    for existing in Path(_logo_dir()).glob(f"{logo_type}_logo_*"):
        if existing.name != stored_name:
            try:
                existing.unlink()
            except OSError:
                pass
    await _set_setting(db, f"{logo_type}_logo", stored_name)
    await _log(db, f"upload_{logo_type}_logo", admin, details={"filename": stored_name})
    return {"ok": True, "logo_type": logo_type, "filename": stored_name}


@router.get("/settings/logo/{logo_type}")
async def get_logo(logo_type: str, db: AsyncSession = Depends(get_db)):
    if logo_type not in ("login", "dashboard"):
        raise HTTPException(status_code=400, detail="logo_type must be 'login' or 'dashboard'")
    setting = await _get_setting(db, f"{logo_type}_logo")
    if not setting or not setting.value:
        raise HTTPException(status_code=404, detail="Logo not set")
    filename = os.path.basename(setting.value)
    if not filename or filename != setting.value or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid logo filename")
    path = os.path.join(_logo_dir(), filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Logo file not found")
    return _file_response(path)


@router.get("/analyses/count")
async def analysis_count(
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    result = await db.execute(select(func.count(models.Analysis.id)))
    return {"count": result.scalar()}


@router.post("/analyses/reset")
async def reset_analyses(
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    result = await db.execute(select(func.count(models.Analysis.id)))
    count = result.scalar()
    await db.execute(delete(models.Analysis))
    await db.commit()
    await _log(db, "reset_analyses", admin, details={"deleted_count": count})
    return {"ok": True, "deleted": count}


@router.get("/settings", response_model=schemas.SiteSettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    login = await _get_setting(db, "login_logo")
    dashboard = await _get_setting(db, "dashboard_logo")
    favicon = await _get_setting(db, "favicon")
    smtp_host = await _get_setting(db, "smtp_host")
    smtp_port = await _get_setting(db, "smtp_port")
    smtp_user = await _get_setting(db, "smtp_user")
    smtp_from = await _get_setting(db, "smtp_from")
    smtp_use_tls = await _get_setting(db, "smtp_use_tls")
    smtp_password = await _get_setting(db, "smtp_password")
    s3_cfg = await get_storage_config(db)
    return {
        "login_logo_url": "/api/admin/settings/logo/login" if login and login.value else None,
        "dashboard_logo_url": "/api/admin/settings/logo/dashboard" if dashboard and dashboard.value else None,
        "favicon_url": "/api/admin/settings/favicon" if favicon and favicon.value else None,
        "smtp_host": smtp_host.value if smtp_host else None,
        "smtp_port": int(smtp_port.value) if smtp_port and smtp_port.value else None,
        "smtp_user": smtp_user.value if smtp_user else None,
        "smtp_from": smtp_from.value if smtp_from else None,
        "smtp_use_tls": smtp_use_tls.value.lower() != "false" if smtp_use_tls and smtp_use_tls.value else True,
        "smtp_configured": bool(smtp_host and smtp_port and smtp_user and smtp_password),
        "s3_enabled": s3_cfg["enabled"],
        "s3_endpoint_url": s3_cfg["endpoint_url"],
        "s3_bucket": s3_cfg["bucket"],
        "s3_region": s3_cfg["region"],
        "s3_use_path_style": s3_cfg["use_path_style"],
        "s3_configured": s3_cfg["configured"],
    }


@router.put("/settings")
async def update_settings(
    body: schemas.SiteSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    if body.login_logo_url is not None:
        await _set_setting(db, "login_logo", body.login_logo_url)
    if body.dashboard_logo_url is not None:
        await _set_setting(db, "dashboard_logo", body.dashboard_logo_url)
    if body.favicon_url is not None:
        await _set_setting(db, "favicon", body.favicon_url)
    if body.smtp_host is not None:
        await _set_setting(db, "smtp_host", body.smtp_host)
    if body.smtp_port is not None:
        await _set_setting(db, "smtp_port", str(body.smtp_port))
    if body.smtp_user is not None:
        await _set_setting(db, "smtp_user", body.smtp_user)
    if body.smtp_from is not None:
        await _set_setting(db, "smtp_from", body.smtp_from)
    if body.smtp_use_tls is not None:
        await _set_setting(db, "smtp_use_tls", "true" if body.smtp_use_tls else "false")
    if body.smtp_password is not None:
        await _set_setting(db, "smtp_password", encrypt_smtp_password(body.smtp_password))
    if body.s3_enabled is not None:
        await _set_setting(db, "s3_enabled", "true" if body.s3_enabled else "false")
    if body.s3_endpoint_url is not None:
        await _set_setting(db, "s3_endpoint_url", body.s3_endpoint_url)
    if body.s3_bucket is not None:
        await _set_setting(db, "s3_bucket", body.s3_bucket)
    if body.s3_region is not None:
        await _set_setting(db, "s3_region", body.s3_region)
    if body.s3_use_path_style is not None:
        await _set_setting(db, "s3_use_path_style", "true" if body.s3_use_path_style else "false")
    if body.s3_access_key:
        await _set_setting(db, "s3_access_key", _encrypt_setting(body.s3_access_key))
    if body.s3_secret_key:
        await _set_setting(db, "s3_secret_key", _encrypt_setting(body.s3_secret_key))
    await _log(db, "update_settings", admin)
    return {"ok": True}


@router.post("/favicon")
async def upload_favicon(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    content_type = _logo_content_type(file.filename or "", file.content_type)
    allowed = {"image/x-icon", "image/png", "image/jpeg", "image/jpg", "image/svg+xml"}
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only ICO, PNG, JPEG, or SVG favicons are allowed")
    ext = _logo_ext(file.filename or "", content_type)
    stored_name = f"favicon_{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    dest_path = os.path.join(_logo_dir(), stored_name)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Clean up previous favicons
    for existing in Path(_logo_dir()).glob("favicon_*"):
        if existing.name != stored_name:
            try:
                existing.unlink()
            except OSError:
                pass
    await _set_setting(db, "favicon", stored_name)
    await _log(db, "upload_favicon", admin, details={"filename": stored_name})
    return {"ok": True, "filename": stored_name}


@router.get("/settings/favicon")
async def get_favicon(db: AsyncSession = Depends(get_db)):
    setting = await _get_setting(db, "favicon")
    if not setting or not setting.value:
        raise HTTPException(status_code=404, detail="Favicon not set")
    filename = os.path.basename(setting.value)
    if not filename or filename != setting.value or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid favicon filename")
    path = os.path.join(_logo_dir(), filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Favicon file not found")
    return _file_response(path)


async def _smtp_config(db: AsyncSession) -> dict:
    return await get_smtp_config(db)


@router.get("/settings/smtp", response_model=schemas.SMTPSettingsOut)
async def get_smtp_settings(db: AsyncSession = Depends(get_db), admin: models.User = Depends(get_current_admin_user)):
    cfg = await _smtp_config(db)
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "from_address": cfg["from_address"],
        "use_tls": cfg["use_tls"],
        "configured": cfg["configured"],
    }


@router.post("/settings/smtp/test")
async def test_smtp(
    payload: schemas.SMTPSettingsOut,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(get_current_admin_user),
):
    cfg = await _smtp_config(db)
    # Allow override from test payload
    host = payload.host or cfg.get("host")
    port = payload.port or cfg.get("port")
    user = payload.user or cfg.get("user")
    password = cfg.get("password")
    from_address = payload.from_address or cfg.get("from_address") or user
    use_tls = payload.use_tls if payload.use_tls is not None else cfg.get("use_tls", True)
    if not host or not port or not user or not password:
        raise HTTPException(status_code=400, detail="SMTP host, port, user and password are required")
    from app.services.email import send_email
    try:
        await send_email(
            db,
            to=admin.email,
            subject="SMTP test",
            body="This is a test email from your metabolomics platform.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SMTP test failed: {exc}")
    return {"ok": True, "recipient": admin.email}

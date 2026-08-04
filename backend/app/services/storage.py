import asyncio
import base64
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings


def _crypto() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_setting(value: str) -> str:
    return _crypto().encrypt(value.encode()).decode()


def decrypt_setting(token: str) -> str:
    return _crypto().decrypt(token.encode()).decode()


def _truthy(value, default=False) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() in ("true", "1", "yes", "on")


def _is_s3_key(stored_name: str) -> bool:
    return isinstance(stored_name, str) and stored_name.startswith("s3://")


def _s3_key(stored_name: str) -> str:
    return stored_name[5:].lstrip("/")


def _cache_path(key: str) -> str:
    safe_key = key.lstrip("/")
    if ".." in Path(safe_key).parts:
        raise ValueError("Invalid S3 key contains path traversal")
    return os.path.abspath(os.path.join(settings.UPLOAD_DIR, safe_key))


def _s3_client(config: dict):
    s3_config = Config(s3={"addressing_style": "path" if config.get("use_path_style") else "virtual"})
    return boto3.client(
        "s3",
        endpoint_url=config.get("endpoint_url") or None,
        aws_access_key_id=config.get("access_key") or None,
        aws_secret_access_key=config.get("secret_key") or None,
        region_name=config.get("region") or None,
        config=s3_config,
    )


async def get_storage_config(db: AsyncSession) -> dict:
    keys = [
        "s3_enabled",
        "s3_endpoint_url",
        "s3_bucket",
        "s3_access_key",
        "s3_secret_key",
        "s3_region",
        "s3_use_path_style",
    ]
    values = {}
    for key in keys:
        result = await db.execute(select(models.SiteSetting).where(models.SiteSetting.key == key))
        row = result.scalar_one_or_none()
        values[key] = row.value if row else None

    enabled = _truthy(values.get("s3_enabled"), default=settings.S3_ENABLED)
    endpoint_url = values.get("s3_endpoint_url") or settings.S3_ENDPOINT_URL
    bucket = values.get("s3_bucket") or settings.S3_BUCKET
    access_key = values.get("s3_access_key") or settings.S3_ACCESS_KEY
    secret_key = values.get("s3_secret_key") or settings.S3_SECRET_KEY
    region = values.get("s3_region") or settings.S3_REGION or "us-east-1"
    use_path_style = _truthy(values.get("s3_use_path_style"), default=settings.S3_USE_PATH_STYLE)

    if secret_key:
        try:
            # If the secret was stored encrypted, decrypt it; otherwise use it as-is.
            if secret_key.startswith("gAAAA"):
                secret_key = decrypt_setting(secret_key)
        except Exception:
            pass
    if access_key:
        try:
            if access_key.startswith("gAAAA"):
                access_key = decrypt_setting(access_key)
        except Exception:
            pass

    configured = bool(enabled and bucket and access_key and secret_key and endpoint_url)
    return {
        "enabled": bool(enabled),
        "endpoint_url": endpoint_url,
        "bucket": bucket,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": region,
        "use_path_style": bool(use_path_style),
        "configured": configured,
    }


async def _s3_upload_file(config: dict, local_path: str, key: str):
    client = _s3_client(config)
    await asyncio.to_thread(client.upload_file, local_path, config["bucket"], key)


async def _s3_download_file(config: dict, key: str, dest_path: str):
    client = _s3_client(config)
    await asyncio.to_thread(client.download_file, config["bucket"], key, dest_path)


async def _s3_delete(config: dict, key: str):
    client = _s3_client(config)
    try:
        await asyncio.to_thread(client.delete_object, Bucket=config["bucket"], Key=key)
    except ClientError:
        pass


async def _s3_put_bytes(config: dict, key: str, data: bytes):
    client = _s3_client(config)
    await asyncio.to_thread(client.put_object, Bucket=config["bucket"], Key=key, Body=data)


async def get_file_path(stored_name: str, db: AsyncSession) -> str:
    """Return a local path for a stored file reference.

    For local files this is the upload directory. For S3 files the object is
    downloaded to a local cache path if it is not already present.
    """
    if not _is_s3_key(stored_name):
        return os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_name))

    key = _s3_key(stored_name)
    cache = _cache_path(key)
    if os.path.exists(cache):
        return cache

    config = await get_storage_config(db)
    if not config["enabled"]:
        raise RuntimeError("S3 storage is disabled but a stored S3 file was requested")
    if not config["configured"]:
        raise RuntimeError("S3 storage is not fully configured")

    os.makedirs(os.path.dirname(cache), exist_ok=True)
    await _s3_download_file(config, key, cache)
    return cache


async def save_upload(local_path: str, stored_name: str, db: AsyncSession) -> str:
    """Persist an uploaded file. Returns the storage reference for the file."""
    config = await get_storage_config(db)
    if not config["enabled"]:
        dest = os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_name))
        if os.path.abspath(local_path) != dest:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(local_path, dest)
        return stored_name

    if not config["configured"]:
        raise RuntimeError("S3 is enabled but missing endpoint, bucket, or credentials")

    key = f"uploads/{stored_name}"
    cache = _cache_path(key)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.abspath(local_path) != cache:
        if os.path.exists(cache):
            os.remove(cache)
        shutil.move(local_path, cache)
    await _s3_upload_file(config, cache, key)
    return f"s3://{key}"


async def delete_file(stored_name: str, db: AsyncSession):
    if _is_s3_key(stored_name):
        key = _s3_key(stored_name)
        config = await get_storage_config(db)
        if config["enabled"] and config["configured"]:
            await _s3_delete(config, key)
        cache = _cache_path(key)
        if os.path.exists(cache):
            os.remove(cache)
    else:
        path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_name))
        if os.path.exists(path):
            os.remove(path)


async def save_report(pdf_bytes: bytes, project_id: int, dataset_id: int, db: AsyncSession, name: Optional[str] = None) -> Optional[str]:
    """Upload a generated PDF report to S3 if enabled. Returns the S3 reference or None."""
    config = await get_storage_config(db)
    if not config["enabled"] or not config["configured"]:
        return None
    safe_name = (name or "report").replace(" ", "_").replace("/", "_")[:80]
    key = f"reports/{project_id}/{dataset_id}/{safe_name}_{uuid.uuid4().hex}.pdf"
    await _s3_put_bytes(config, key, pdf_bytes)
    return f"s3://{key}"


async def create_report_record(
    db: AsyncSession,
    project_id: int,
    dataset_id: Optional[int],
    user_id: Optional[int],
    name: str,
    report_type: str,
    s3_key: str,
) -> models.GeneratedReport:
    report = models.GeneratedReport(
        project_id=project_id,
        dataset_id=dataset_id,
        user_id=user_id,
        name=name,
        report_type=report_type,
        s3_key=s3_key,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def list_reports(
    db: AsyncSession,
    project_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    user_id: Optional[int] = None,
):
    from sqlalchemy import select
    stmt = select(models.GeneratedReport)
    if project_id is not None:
        stmt = stmt.where(models.GeneratedReport.project_id == project_id)
    if dataset_id is not None:
        stmt = stmt.where(models.GeneratedReport.dataset_id == dataset_id)
    if user_id is not None:
        stmt = stmt.where(models.GeneratedReport.user_id == user_id)
    stmt = stmt.order_by(models.GeneratedReport.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_report(db: AsyncSession, report_id: int, user_id: Optional[int] = None) -> Optional[models.GeneratedReport]:
    from sqlalchemy import select
    stmt = select(models.GeneratedReport).where(models.GeneratedReport.id == report_id)
    if user_id is not None:
        stmt = stmt.join(models.Project).where(models.Project.owner_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def download_report_bytes(report: models.GeneratedReport, db: AsyncSession) -> bytes:
    path = await get_file_path(report.s3_key, db)
    loop = asyncio.get_event_loop()
    with open(path, "rb") as f:
        return await loop.run_in_executor(None, f.read)


async def delete_report(report: models.GeneratedReport, db: AsyncSession):
    await delete_file(report.s3_key, db)
    await db.delete(report)
    await db.commit()

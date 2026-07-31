import datetime as dt
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app import schemas, models
from app.auth import verify_password, get_password_hash, create_access_token, get_current_active_user
from app.config import settings


_CT_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}

router = APIRouter()


def _avatar_dir():
    path = Path(settings.UPLOAD_DIR) / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _allowed_image(content_type: str, ext: str) -> bool:
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    allowed_exts = {"png", "jpg", "jpeg", "webp"}
    return content_type in allowed_types and ext in allowed_exts


@router.post("/register", response_model=schemas.UserOut)
async def register(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user_in.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(email=user_in.email, hashed_password=get_password_hash(user_in.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserOut)
async def me(current_user: models.User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserOut)
async def update_me(
    user_in: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if user_in.email is not None:
        result = await db.execute(select(models.User).where(models.User.email == user_in.email))
        existing = result.scalar_one_or_none()
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = user_in.email
    if user_in.name is not None:
        current_user.name = user_in.name.strip() or None
    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.content_type:
        raise HTTPException(status_code=400, detail="Could not determine file type")
    ext = (
        Path(file.filename or "").suffix.lstrip(".").lower()
        if file.filename and "." in file.filename
        else _CT_EXT.get(file.content_type, "png")
    )
    # Allow jpeg extension to be saved as jpg for consistency
    if ext == "jpeg":
        ext = "jpg"
    if not _allowed_image(file.content_type, ext):
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WebP images are allowed")
    MAX_AVATAR_SIZE = 5 * 1024 * 1024
    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=413, detail="Avatar must be under 5 MB")
    avatar_dir = _avatar_dir()
    # Clean up any previous avatar for this user
    for existing in avatar_dir.glob(f"user_{current_user.id}_*"):
        try:
            existing.unlink()
        except OSError:
            pass
    suffix = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"user_{current_user.id}_{suffix}.{ext}"
    dest_path = avatar_dir / stored_name
    with open(dest_path, "wb") as buffer:
        buffer.write(contents)
    current_user.avatar_url = f"/api/auth/avatar/{current_user.id}?v={suffix}"
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/avatar/{user_id}")
async def get_avatar(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.avatar_url:
        raise HTTPException(status_code=404, detail="Avatar not found")
    avatar_dir = _avatar_dir()
    matches = list(avatar_dir.glob(f"user_{user_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Avatar file not found")
    response = FileResponse(matches[0])
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

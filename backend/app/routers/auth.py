import datetime as dt
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from jose import jwt as _jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app import schemas, models
from app.auth import verify_password, get_password_hash, create_access_token, get_current_active_user
from app.config import settings
from app.services.email import send_email


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
    # Fast-forward content type from filename if the client did not send one.
    content_type = file.content_type
    filename = file.filename or ""
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        content_type = guessed or content_type

    ext = (
        Path(filename).suffix.lstrip(".").lower()
        if "." in filename
        else _CT_EXT.get(content_type or "", "png")
    )
    # Allow jpeg extension to be saved as jpg for consistency
    if ext == "jpeg":
        ext = "jpg"
    if not _allowed_image(content_type or "", ext):
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WebP images are allowed")
    MAX_AVATAR_SIZE = 20 * 1024 * 1024
    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=413, detail="Avatar must be under 20 MB")
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
    media_type, _ = mimetypes.guess_type(str(matches[0]))
    response = FileResponse(matches[0], media_type=media_type or "image/png")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.post("/forgot-password")
async def forgot_password(
    req: schemas.ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.User).where(models.User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"ok": True, "detail": "If this email exists, a reset link has been sent."}
    token = create_access_token({"sub": str(user.id), "scope": "reset"}, expires_delta=dt.timedelta(minutes=30))
    base_url = settings.FRONTEND_URL or ""
    reset_url = f"{base_url}/reset-password?token={token}"
    try:
        await send_email(
            db,
            to=user.email,
            subject="Password reset request",
            body=f"Click the following link to reset your password (expires in 30 minutes): {reset_url}",
            html=f"<p>Click the following link to reset your password (expires in 30 minutes):</p><a href='{reset_url}'>{reset_url}</a>",
        )
    except Exception as exc:
        if settings.RESET_TOKEN_IN_RESPONSE:
            return {"ok": True, "detail": f"SMTP not configured ({exc}); reset token returned for development.", "reset_token": token, "reset_url": reset_url}
        raise HTTPException(status_code=503, detail="SMTP not configured. Please configure SMTP in the admin panel or set FRONTEND_URL/RESET_TOKEN_IN_RESPONSE for development.")
    return {"ok": True, "detail": "If this email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    req: schemas.ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = _jwt.decode(req.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token")
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = get_password_hash(req.new_password)
    await db.commit()
    return {"ok": True}

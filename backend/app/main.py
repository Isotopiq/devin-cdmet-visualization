import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import auth, projects, files, import_, analysis, stats, plots, isotope, pathways, admin
from app import models
from app.auth import get_password_hash


async def ensure_admin_user():
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(models.User).where(models.User.email == settings.ADMIN_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = models.User(
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
            db.add(user)
        else:
            user.is_active = True
            user.is_admin = True
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    await ensure_admin_user()
    yield


app = FastAPI(title="Metabolomics Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(import_.router, prefix="/api/import", tags=["import"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(plots.router, prefix="/api/plots", tags=["plots"])
app.include_router(isotope.router, prefix="/api/isotope", tags=["isotope"])
app.include_router(pathways.router, prefix="/api/pathways", tags=["pathways"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}

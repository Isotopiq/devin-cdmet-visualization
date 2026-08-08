import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from app.config import settings
from app import database as db_module
from app.routers import auth, projects, files, import_, analysis, stats, plots, isotope, pathways, admin
from app import models
from app.auth import get_password_hash

logger = logging.getLogger(__name__)


def _is_pytest() -> bool:
    return bool(os.environ.get("PYTEST_VERSION"))


async def ensure_admin_user():
    # Allow either ADMIN_EMAIL or ADMIN_USERNAME (treated as the login email).
    admin_email = settings.ADMIN_EMAIL or settings.ADMIN_USERNAME
    if not admin_email:
        return
    if not settings.ADMIN_PASSWORD:
        logger.warning("ADMIN_EMAIL is set but ADMIN_PASSWORD is not; skipping admin auto-creation.")
        return

    async with db_module.AsyncSessionLocal() as db:
        # If an admin already exists, do nothing unless a specific email is configured.
        result = await db.execute(select(models.User).where(models.User.email == admin_email))
        user = result.scalar_one_or_none()
        if user is None:
            user = models.User(
                email=admin_email,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
            db.add(user)
            logger.info("Created admin user %s", admin_email)
        else:
            # Only re-activate/elevate an existing account when an admin password is
            # explicitly configured. Without it, do not promote a regular user.
            user.is_active = True
            user.is_admin = True
            logger.info("Ensured admin privileges for %s", admin_email)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _is_pytest() and settings.SECRET_KEY == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is set to the default value. Set a strong SECRET_KEY before running in production."
        )
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    await ensure_admin_user()
    yield


app = FastAPI(title="Metabolomics Platform", version="0.1.0", lifespan=lifespan)

# CORS: do not allow wildcard origins together with credentials. Restrict to the
# configured frontend URL when available.
if settings.FRONTEND_URL:
    allow_origins = [settings.FRONTEND_URL]
    allow_credentials = True
else:
    logger.warning("FRONTEND_URL is not set; CORS is unrestricted and credentials are disabled.")
    allow_origins = ["*"]
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
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
    try:
        async with db_module.AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Health check failed")
        raise RuntimeError("Database connection failed") from exc
    return {"status": "ok"}

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, projects, files, import_, analysis, stats, plots, isotope, pathways


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}

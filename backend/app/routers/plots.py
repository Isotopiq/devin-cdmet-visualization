from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.plots import generate_plot
from app.services.plots import _merge_style
from app.services.stats import run_statistical_test

router = APIRouter()


@router.post("/{project_id}/dataset/{dataset_id}/plot", response_model=Any)
async def plot(project_id: int, dataset_id: int, req: schemas.PlotRequest,
               db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    figure = generate_plot(dataset, req)
    return figure


@router.post("/{project_id}/dataset/{dataset_id}/report", response_model=List[Dict[str, Any]])
async def report(project_id: int, dataset_id: int, req: schemas.ReportRequest,
                 db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    style = _merge_style(req.style)
    params = req.parameters or {}
    stats_data = []
    if any(k in req.include for k in ("volcano", "per_lipid_bars")):
        stats_req = schemas.StatsRequest(
            test=params.get("test", "t_test"),
            group_a=params.get("group_a"),
            group_b=params.get("group_b"),
            paired=params.get("paired", False),
            multiple_testing=params.get("multiple_testing", "fdr_bh"),
            alpha=params.get("alpha", 0.05),
        )
        stats_data = run_statistical_test(dataset, stats_req).get("results", [])

    sections = []
    for key in req.include:
        if key == "pca":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="pca", parameters={"plot": "score"}, style=style))
            sections.append({"key": key, "title": "PCA Score Plot", "figure": fig})
        elif key == "volcano":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="volcano", parameters={
                "stats": stats_data,
                "fc_threshold": params.get("fc_threshold", 1.0),
                "p_threshold": params.get("p_threshold", 0.05),
                "show_labels": params.get("show_labels", False),
                "top_n": params.get("top_n", 15),
                "group_b": params.get("group_b"),
            }, style=style))
            sections.append({"key": key, "title": "Volcano Plot", "figure": fig})
        elif key == "heatmap":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="heatmap", parameters={
                "heatmap_type": "abundance",
                "top_n": params.get("heatmap_top_n", 50),
                "scale": params.get("scale", "row_zscore"),
                "metric": params.get("metric", "euclidean"),
                "method": params.get("method", "average"),
                "cluster_rows": params.get("cluster_rows", True),
                "cluster_cols": params.get("cluster_cols", True),
            }, style=style))
            sections.append({"key": key, "title": "Heatmap", "figure": fig})
        elif key == "per_lipid_bars":
            top_n = params.get("per_lipid_top_n", 8)
            if params.get("all_lipids"):
                top_n = max(len(stats_data), 1)
            figs = generate_plot(dataset, schemas.PlotRequest(plot_type="per_lipid_bars", parameters={
                "stats": stats_data,
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                "top_n": top_n,
            }, style=style))
            sections.append({"key": key, "title": "Per-lipid bars", "figures": figs})
        elif key == "lipid_classes":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="lipid_class", parameters={}, style=style))
            sections.append({"key": key, "title": "Lipid class analysis", "figure": fig})

    return sections

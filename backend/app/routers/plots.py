import io
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.plots import generate_plot
from app.services.plots import _merge_style
from app.services.stats import run_statistical_test
from app.services.pdf_report import build_pdf, get_pdf_footer_logo_path, get_pdf_prepared_by
from app.services import storage

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
    base_params = {"excluded_groups": params.get("excluded_groups") or []}
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
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="pca", parameters={"plot": "score", **base_params}, style=style))
            sections.append({"key": key, "title": "PCA Score Plot", "figure": fig})
        elif key == "pls_da":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="pls_da", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "PLS-DA", "figure": fig})
        elif key == "opls_da":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="opls_da", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "OPLS-DA", "figure": fig})
        elif key == "biomarker":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="biomarker", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Biomarker discovery", "figure": fig})
        elif key == "permanova":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="permanova", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "PERMANOVA", "figure": fig})
        elif key == "volcano":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="volcano", parameters={
                "stats": stats_data,
                "fc_threshold": params.get("fc_threshold", 1.0),
                "p_threshold": params.get("p_threshold", 0.05),
                "show_labels": params.get("show_labels", False),
                "top_n": params.get("top_n", 15),
                "group_b": params.get("group_b"),
                **base_params,
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
                **base_params,
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
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Per-lipid bars", "figures": figs})
        elif key == "lipid_classes":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="lipid_class", parameters={**base_params}, style=style))
            sections.append({"key": key, "title": "Lipid class analysis", "figure": fig})
        elif key == "outlier":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="outlier", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Outlier analysis", "figure": fig})
        elif key == "functional":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="functional", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Functional lipid indices", "figure": fig})
        elif key == "food_profile":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="food_profile", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Lipid food profile", "figure": fig})
        elif key == "chain_space":
            fig = generate_plot(dataset, schemas.PlotRequest(plot_type="chain_space", parameters={
                "group_a": params.get("group_a"),
                "group_b": params.get("group_b"),
                **base_params,
            }, style=style))
            sections.append({"key": key, "title": "Chain space", "figure": fig})

    return sections


@router.post("/{project_id}/dataset/{dataset_id}/report/pdf")
async def report_pdf(
    project_id: int,
    dataset_id: int,
    req: schemas.PDFReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    project_result = await db.execute(select(models.Project).where(models.Project.id == project_id))
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else ""

    footer_logo_path = await get_pdf_footer_logo_path(db)
    default_prepared_by = await get_pdf_prepared_by(db)
    if not req.prepared_by:
        req.prepared_by = default_prepared_by or "Metabolomics Platform"
    pdf_bytes = build_pdf(dataset, project_name, req, footer_logo_path=footer_logo_path)
    filename = f"{dataset.name.replace(' ', '_')}_report.pdf"
    if req.save_to_s3:
        s3_key = await storage.save_report(pdf_bytes, project_id, dataset_id, db, name=filename)
        if s3_key:
            await storage.create_report_record(
                db,
                project_id=project_id,
                dataset_id=dataset_id,
                user_id=current_user.id,
                name=filename,
                report_type="report",
                s3_key=s3_key,
            )
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )

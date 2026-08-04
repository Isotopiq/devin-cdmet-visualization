import io
import csv
import math
from typing import List, Literal
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.auth import get_current_active_user
from app import models, schemas
from app.services.preprocessing import preprocess_dataset, to_dataframe
from app.services.qc import qc_analysis, qc_export_excel
from app.services.batch import combine_datasets
from app.services.pdf_report import build_qc_pdf
from app.services import storage

router = APIRouter()


@router.get("/{project_id}/dataset/{dataset_id}", response_model=schemas.DatasetOut)
async def get_dataset(project_id: int, dataset_id: int, db: AsyncSession = Depends(get_db),
                      current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    project_result = await db.execute(select(models.Project).where(models.Project.id == project_id))
    project = project_result.scalar_one_or_none()
    dataset.project_name = project.name if project else None
    return dataset


@router.put("/{project_id}/dataset/{dataset_id}/sample_groups", response_model=schemas.DatasetOut)
async def update_sample_groups(
    project_id: int,
    dataset_id: int,
    body: schemas.SampleGroupsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id,
        models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id,
    ))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Only allow updating group labels for existing sample columns.
    existing = set(dataset.sample_metadata or {})
    if not existing:
        raise HTTPException(status_code=400, detail="Dataset has no sample metadata")
    sample_metadata = {col: str(body.sample_metadata.get(col, dataset.sample_metadata.get(col, "unknown"))) for col in existing}
    dataset.sample_metadata = sample_metadata
    dataset.processing_history = list(dataset.processing_history or []) + [{"step": "update_sample_groups", "updated": list(sample_metadata.values())}]
    await db.commit()
    await db.refresh(dataset)
    return dataset


@router.post("/{project_id}/dataset/{dataset_id}/preprocess", response_model=schemas.DatasetOut)
async def preprocess(project_id: int, dataset_id: int, params: schemas.PreprocessingParams,
                     db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    new_dataset = await preprocess_dataset(db, dataset, params)
    return new_dataset


@router.get("/{project_id}/datasets", response_model=List[schemas.DatasetOut])
async def list_datasets(project_id: int, db: AsyncSession = Depends(get_db),
                        current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    datasets = result.scalars().all()
    project_result = await db.execute(select(models.Project).where(models.Project.id == project_id))
    project = project_result.scalar_one_or_none()
    for d in datasets:
        d.project_name = project.name if project else None
    return datasets


@router.get("/datasets/all", response_model=schemas.PaginatedDatasetOut)
async def list_all_datasets(
    project_ids: List[int] = Query(default=[]),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    where_clause = models.Project.owner_id == current_user.id
    if project_ids:
        where_clause = where_clause & models.Dataset.project_id.in_(project_ids)

    result = await db.execute(
        select(models.Dataset)
        .join(models.Project)
        .where(where_clause)
        .offset(offset)
        .limit(limit)
    )
    datasets = result.scalars().all()

    count_result = await db.execute(
        select(func.count(models.Dataset.id))
        .select_from(models.Dataset)
        .join(models.Project)
        .where(where_clause)
    )
    total = count_result.scalar() or 0

    loaded_project_ids = {d.project_id for d in datasets}
    project_result = await db.execute(select(models.Project).where(models.Project.id.in_(loaded_project_ids)))
    project_names = {p.id: p.name for p in project_result.scalars().all()}
    for d in datasets:
        d.project_name = project_names.get(d.project_id)

    return {"items": datasets, "total": total}


@router.post("/{project_id}/datasets/combine", response_model=schemas.BatchCombineOut)
async def batch_combine(
    project_id: int,
    body: schemas.BatchCombineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await combine_datasets(
        db,
        project_id,
        current_user.id,
        dataset_ids=body.dataset_ids,
        method=body.method,
        batch_assignment=body.batch_assignment,
        reference_group=body.reference_group,
        per_dataset_reference_group=body.per_dataset_reference_group,
        output_name=body.output_name,
        control_features=body.control_features,
        n_unwanted_factors=body.n_unwanted_factors or 1,
        include_qc_plots=body.include_qc_plots,
        style=body.style,
    )
    if isinstance(result, dict):
        return result
    return {"dataset": result, "qc_report": None}


@router.get("/{project_id}/dataset/{dataset_id}/qc")
async def get_qc(
    project_id: int,
    dataset_id: int,
    selected_groups: List[str] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return qc_analysis(dataset, selected_groups=selected_groups)


@router.get("/{project_id}/dataset/{dataset_id}/qc/excel")
async def get_qc_excel(
    project_id: int,
    dataset_id: int,
    selected_groups: List[str] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id, models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    excel_bytes = qc_export_excel(dataset, selected_groups=selected_groups)
    filename = f"{dataset.name.replace(' ', '_')}_qc_summary.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{project_id}/dataset/{dataset_id}/qc/pdf")
async def get_qc_pdf(
    project_id: int,
    dataset_id: int,
    body: schemas.QCPdfRequest = Body(default_factory=schemas.QCPdfRequest),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(models.Dataset, models.Project)
        .join(models.Project)
        .where(
            models.Dataset.id == dataset_id,
            models.Dataset.project_id == project_id,
            models.Project.owner_id == current_user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Dataset not found")
    dataset, project = row

    pdf_bytes = build_qc_pdf(dataset, project.name if project else "", selected_groups=body.selected_groups)
    s3_key = await storage.save_report(pdf_bytes, project_id, dataset_id, db)
    filename = f"{dataset.name.replace(' ', '_')}_qc_report.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    if s3_key:
        headers["X-S3-Key"] = s3_key
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


@router.delete("/{project_id}/dataset/{dataset_id}")
async def delete_dataset(project_id: int, dataset_id: int, db: AsyncSession = Depends(get_db),
                         current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.delete(dataset)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/analyses", response_model=List[schemas.AnalysisOut])
async def list_analyses(project_id: int, db: AsyncSession = Depends(get_db),
                        current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Analysis).join(models.Project).where(
        models.Analysis.project_id == project_id, models.Project.owner_id == current_user.id))
    return result.scalars().all()


@router.delete("/{project_id}/analyses/{analysis_id}")
async def delete_analysis(project_id: int, analysis_id: int, db: AsyncSession = Depends(get_db),
                          current_user: models.User = Depends(get_current_active_user)):
    result = await db.execute(select(models.Analysis).join(models.Project).where(
        models.Analysis.id == analysis_id, models.Analysis.project_id == project_id,
        models.Project.owner_id == current_user.id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await db.delete(analysis)
    await db.commit()
    return {"ok": True}


def _fmt_export_value(v, floor: float) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return ""
    if f <= 0:
        f = floor / 2.0
    s = f"{f:.12f}".rstrip("0").rstrip(".")
    return s if s else "0"


@router.get("/{project_id}/dataset/{dataset_id}/export")
async def export_dataset(
    project_id: int,
    dataset_id: int,
    format: Literal["metaboanalyst", "lipidone"] = Query("metaboanalyst"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    result = await db.execute(select(models.Dataset).join(models.Project).where(
        models.Dataset.id == dataset_id, models.Dataset.project_id == project_id,
        models.Project.owner_id == current_user.id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    df = to_dataframe(dataset)
    feature_metadata = dataset.feature_metadata or []

    # Only export representative (or combined) rows; skip isobaric component rows that
    # were excluded from rollups by the "report combined" resolution modes.
    if feature_metadata:
        keep_rows = [not bool(m.get("isobaric_substitution_rollup_exclude")) for m in feature_metadata]
        if not all(keep_rows):
            df = df[keep_rows].reset_index(drop=True)
            feature_metadata = [m for m, ok in zip(feature_metadata, keep_rows) if ok]

    for step in dataset.processing_history or []:
        if not isinstance(step, dict):
            continue
        params = step.get("params", {}) or {}
        if params.get("scale") in ("standard", "robust", "minmax"):
            raise HTTPException(
                status_code=400,
                detail="Cannot export scaled data as intensities. Select the original/unprocessed dataset.",
            )
        if params.get("log_transform"):
            df = 2 ** df

    pos = df.values[df.values > 0]
    floor = float(pos.min()) if pos.size else 1e-12

    samples = df.columns.tolist()
    groups = [str(dataset.sample_metadata.get(s, "unknown")) for s in samples]
    header_key = "Sample" if format == "metaboanalyst" else "Lipid"
    header = [header_key] + samples
    label_row = ["Label"] + groups

    feature_ids = [m.get("feature_id", f"feature_{i}") for i, m in enumerate(feature_metadata)]
    if len(feature_ids) != len(df):
        feature_ids = [f"feature_{i}" for i in range(len(df))]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerow(label_row)
    for i, fid in enumerate(feature_ids):
        row = [fid] + [_fmt_export_value(df.at[i, s], floor) for s in samples]
        writer.writerow(row)

    out.seek(0)
    safe_name = str(dataset.name).replace(" ", "_").replace(",", "")
    filename = f"{safe_name}_{format}.csv"
    return StreamingResponse(
        iter([out.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

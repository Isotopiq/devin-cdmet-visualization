import io
import datetime as dt
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fpdf import FPDF
import plotly.graph_objects as go

from app import models, schemas
from app.services.preprocessing import to_dataframe
from app.services.stats import run_statistical_test
from app.services.plots import generate_plot

# Kaleido 0.2.1 is required for headless Plotly->PNG export in this container;
# newer versions need a separate Chrome install. Silence its deprecation chatter.
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*Kaleido versions less than 1\.0\.0.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*Use of plotly\.io\.kaleido\.scope.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*setDaemon.*")


class _ReportPDF(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self._set_fonts()

    def _set_fonts(self):
        regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if Path(regular).exists() and Path(bold).exists():
            self.add_font("DejaVu", "", regular)
            self.add_font("DejaVu", "B", bold)
        else:
            regular = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            bold = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            if Path(regular).exists() and Path(bold).exists():
                self.add_font("Liberation", "", regular)
                self.add_font("Liberation", "B", bold)

    def set_body_font(self, size=11, style=""):
        for family in ["DejaVu", "Liberation", "Helvetica"]:
            try:
                self.set_font(family, style, size)
                return
            except RuntimeError:
                pass
        self.set_font("Helvetica", style, size)


def _fig_to_png(fig_dict: dict, width: int = 1200, height: int = 700, scale: int = 2) -> io.BytesIO:
    fig = go.Figure(data=fig_dict.get("data", []), layout=fig_dict.get("layout", {}))
    buffer = io.BytesIO()
    # Suppress Kaleido/Plotly deprecation noise for the headless PNG export.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.write_image(buffer, format="png", width=width, height=height, scale=scale)
    buffer.seek(0)
    return buffer


def _groups(dataset: models.Dataset) -> List[str]:
    meta = dataset.sample_metadata or {}
    groups = sorted(set(str(g) for g in meta.values() if g))
    if "Unknown" in groups:
        groups = [g for g in groups if g != "Unknown"] + ["Unknown"]
    return groups


def _comparison(dataset: models.Dataset, group_a: Optional[str], group_b: Optional[str]) -> Tuple[str, str]:
    groups = _groups(dataset)
    if group_a and group_b and group_a in groups and group_b in groups:
        return group_a, group_b
    if len(groups) >= 2:
        return groups[0], groups[1]
    if len(groups) == 1:
        return groups[0], ""
    return "", ""


SECTION_TITLES = {
    "summary": "Summary",
    "heatmap_unclustered": "Heatmap - Abundance (Un-clustered)",
    "heatmap_clustered": "Heatmap - Abundance (Clustered)",
    "pca_score": "PCA Score Plot",
    "pca_loadings": "PCA Top Loadings",
    "pca_scree": "PCA Scree Plot",
    "pls_da": "PLS-DA",
    "opls_da": "OPLS-DA",
    "volcano": "Volcano Plot",
    "functional": "Functional Lipid Volcano Plot",
    "food_profile": "Nutritional Metabolic Lipid Profile",
    "chain_space": "Chain Space Analysis",
    "lipid_class": "Lipid Class Distribution",
    "per_lipid_bars": "Individual Feature Bar Plots",
    "biomarker": "Biomarker Discovery",
    "permanova": "PERMANOVA",
    "outlier": "Outlier Analysis",
    "rt_mz": "Retention Time vs m/z",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _summary_metrics(dataset: models.Dataset, group_a: str, group_b: str, stats_data: List[dict], p_threshold: float) -> dict:
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata or {}
    groups = _groups(dataset)
    group_counts = {g: sum(1 for s in df.columns if sample_meta.get(s) == g) for g in groups}

    missing_total = df.isna().sum().sum()
    total = df.size
    missing_pct = round(missing_total / total * 100, 2) if total else 0.0

    sig_count = sum(1 for s in stats_data if _safe_float(s.get("padj"), 1.0) < p_threshold)
    up_count = sum(1 for s in stats_data if _safe_float(s.get("padj"), 1.0) < p_threshold and _safe_float(s.get("log2fc"), 0.0) > 0)
    down_count = sig_count - up_count

    # QC-like medians
    def _median_cv(cols):
        if not cols:
            return None
        sub = df[cols]
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = sub.mean(axis=1, skipna=True)
            std = sub.std(axis=1, skipna=True)
            cv = (std / mean).replace([np.inf, -np.inf], np.nan).dropna()
        return round(float(cv.median()) * 100, 2) if not cv.empty else None

    qc_groups = {g for g in groups if "qc" in g.lower()}
    blank_groups = {g for g in groups if any(b in g.lower() for b in ["blank", "solvent", "ntc", "standard", "pool"])}
    qc_median_cv = _median_cv([c for c in df.columns if sample_meta.get(c) in qc_groups])

    sample_to_blank = None
    sample_groups = [g for g in groups if g not in blank_groups and g not in qc_groups]
    blank_cols = [c for c in df.columns if sample_meta.get(c) in blank_groups]
    sample_cols = [c for c in df.columns if sample_meta.get(c) in sample_groups]
    if blank_cols and sample_cols:
        blank_mean = df[blank_cols].mean(axis=1, skipna=True).replace(0, np.nan)
        sample_mean = df[sample_cols].mean(axis=1, skipna=True)
        ratio = (sample_mean / blank_mean).replace([np.inf, -np.inf], np.nan).dropna()
        sample_to_blank = round(float(ratio.median()), 2) if not ratio.empty else None

    top_features = sorted(
        [s for s in stats_data if s.get("padj") is not None],
        key=lambda s: _safe_float(s.get("padj"), 1.0),
    )[:10]

    return {
        "features": df.shape[0],
        "samples": df.shape[1],
        "groups": groups,
        "group_counts": group_counts,
        "missing_pct": missing_pct,
        "significant": sig_count,
        "up": up_count,
        "down": down_count,
        "qc_median_cv": qc_median_cv,
        "sample_to_blank": sample_to_blank,
        "top_features": top_features,
    }


def _add_cover(pdf: _ReportPDF, title: str, subtitle: str, dataset_name: str, project_name: str,
               group_a: str, group_b: str, prepared_for: str, prepared_by: str, sections: List[str]):
    pdf.add_page()
    pdf.set_body_font(28, "B")
    pdf.set_y(60)
    pdf.cell(0, 20, title or "Statistical Report", align="C", new_x="LMARGIN", new_y="NEXT")
    if subtitle:
        pdf.set_body_font(14)
        pdf.cell(0, 12, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_body_font(12)
    lines = [
        f"Dataset: {dataset_name}",
    ]
    if project_name:
        lines.append(f"Project: {project_name}")
    if group_a or group_b:
        lines.append(f"Primary comparison: {group_a} vs {group_b}")
    lines.append(f"Generated: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    if prepared_for:
        lines.append(f"Prepared for: {prepared_for}")
    if prepared_by:
        lines.append(f"Prepared by: {prepared_by}")
    for line in lines:
        pdf.cell(0, 10, line, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(20)
    pdf.set_body_font(14, "B")
    pdf.cell(0, 12, "Report Contents", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_body_font(11)
    for section in sections:
        pdf.cell(0, 8, f"  • {SECTION_TITLES.get(section, section)}", align="C", new_x="LMARGIN", new_y="NEXT")


def _add_summary(pdf: _ReportPDF, metrics: dict, group_a: str, group_b: str, p_threshold: float):
    pdf.add_page()
    pdf.set_body_font(18, "B")
    pdf.cell(0, 14, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_body_font(11)

    rows = [
        ["Features", str(metrics["features"])],
        ["Samples", str(metrics["samples"])],
        ["Groups", ", ".join(metrics["groups"])],
        ["Missing values", f"{metrics['missing_pct']}%"],
        ["Significant features", f"{metrics['significant']} (padj < {p_threshold})"],
        ["Up-regulated", str(metrics["up"])],
        ["Down-regulated", str(metrics["down"])],
    ]
    if metrics["qc_median_cv"] is not None:
        rows.append(["QC median CV", f"{metrics['qc_median_cv']}%"])
    if metrics["sample_to_blank"] is not None:
        rows.append(["Sample/Blank ratio", f"{metrics['sample_to_blank']}x"])

    col_widths = [90, 90]
    for row in rows:
        for i, text in enumerate(row):
            pdf.cell(col_widths[i], 10, text, border=1, align="L")
        pdf.ln()

    pdf.ln(6)
    pdf.set_body_font(12, "B")
    pdf.cell(0, 10, f"Group counts", new_x="LMARGIN", new_y="NEXT")
    pdf.set_body_font(11)
    for g, count in metrics["group_counts"].items():
        pdf.cell(90, 8, str(g), border=1)
        pdf.cell(90, 8, str(count), border=1, new_x="LMARGIN", new_y="NEXT")

    if metrics["top_features"]:
        pdf.ln(6)
        pdf.set_body_font(12, "B")
        pdf.cell(0, 10, f"Top 10 significant features ({group_b} vs {group_a})", new_x="LMARGIN", new_y="NEXT")
        pdf.set_body_font(10)
        pdf.cell(120, 8, "Feature", border=1)
        pdf.cell(30, 8, "log2FC", border=1)
        pdf.cell(40, 8, "padj", border=1, new_x="LMARGIN", new_y="NEXT")
        for s in metrics["top_features"]:
            pdf.cell(120, 8, str(s.get("feature_id", "")), border=1)
            pdf.cell(30, 8, f"{_safe_float(s.get('log2fc'), 0.0):.3f}", border=1)
            pdf.cell(40, 8, f"{_safe_float(s.get('padj'), 1.0):.3e}", border=1, new_x="LMARGIN", new_y="NEXT")


SECTION_LAYOUTS: Dict[str, Dict[str, Any]] = {
    "default": {"width": 1200, "height": 700, "orientation": "P"},
    "heatmap_unclustered": {"width": 1600, "height": 900, "orientation": "L"},
    "heatmap_clustered": {"width": 1600, "height": 900, "orientation": "L"},
    "pca_score": {"width": 1200, "height": 900, "orientation": "P"},
    "pca_loadings": {"width": 1200, "height": 700, "orientation": "P"},
    "pca_scree": {"width": 800, "height": 600, "orientation": "P"},
    "pls_da": {"width": 1400, "height": 900, "orientation": "L"},
    "opls_da": {"width": 1400, "height": 900, "orientation": "L"},
    "volcano": {"width": 1200, "height": 800, "orientation": "P"},
    "per_lipid_bars": {"width": 600, "height": 400, "orientation": "P"},
}


def _add_plot_page(pdf: _ReportPDF, title: str, img_buffer: io.BytesIO, section: str = "default"):
    layout = SECTION_LAYOUTS.get(section, SECTION_LAYOUTS["default"])
    orientation = layout.get("orientation", "P")
    pdf.add_page(orientation)
    pdf.set_body_font(16, "B")
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    # Landscape A4 usable width ~277 mm, portrait ~190 mm.
    width_mm = 277 if orientation == "L" else 190
    pdf.image(img_buffer, x=10, y=25, w=width_mm)


def _add_multi_plot_page(pdf: _ReportPDF, title: str, buffers: List[io.BytesIO], per_page: int = 4):
    pdf.add_page()
    pdf.set_body_font(16, "B")
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    positions = [(10, 35, 90, 60), (105, 35, 90, 60), (10, 115, 90, 60), (105, 115, 90, 60)]
    for i, buf in enumerate(buffers):
        if i > 0 and i % per_page == 0:
            pdf.add_page()
            pdf.set_body_font(16, "B")
            pdf.cell(0, 12, title + " (continued)", new_x="LMARGIN", new_y="NEXT")
        x, y, w, h = positions[i % per_page]
        pdf.image(buf, x=x, y=y, w=w, h=h)


def _section_params(section: str, group_a: str, group_b: str, stats_data: List[dict],
                    req: schemas.PDFReportRequest) -> Optional[dict]:
    p = {
        "group_a": group_a,
        "group_b": group_b,
    }
    if section == "heatmap_unclustered":
        return {
            "heatmap_type": "abundance",
            "top_n": 50,
            "scale": "row_zscore",
            "metric": "euclidean",
            "method": "average",
            "cluster_rows": False,
            "cluster_cols": False,
            **p,
        }
    if section == "heatmap_clustered":
        return {
            "heatmap_type": "abundance",
            "top_n": 50,
            "scale": "row_zscore",
            "metric": "euclidean",
            "method": "average",
            "cluster_rows": True,
            "cluster_cols": True,
            **p,
        }
    if section in ("pca_score", "pca_loadings", "pca_scree"):
        return {"plot": section.split("_")[1], **p}
    if section == "pls_da":
        return {"n_components": 2, "n_perm": req.n_perm, **p}
    if section == "opls_da":
        return {"n_orth": 1, "n_perm": req.n_perm, **p}
    if section in ("volcano", "per_lipid_bars"):
        return {
            "stats": stats_data,
            "fc_threshold": req.fc_threshold,
            "p_threshold": req.p_threshold,
            "padj_threshold": req.p_threshold,
            "show_labels": req.show_labels,
            "top_n": req.top_n,
            **p,
        }
    if section in ("functional", "food_profile", "chain_space", "biomarker", "permanova", "outlier", "lipid_class"):
        return p
    if section == "rt_mz":
        return {}
    return p


def build_pdf(dataset: models.Dataset, project_name: str, req: schemas.PDFReportRequest) -> bytes:
    group_a, group_b = _comparison(dataset, req.group_a, req.group_b)
    sections = [s for s in req.sections if s in SECTION_TITLES]

    # Precompute stats if needed
    needs_stats = any(s in ("volcano", "per_lipid_bars") for s in sections)
    stats_data = []
    if needs_stats and group_a and group_b:
        stats_req = schemas.StatsRequest(
            test=req.test,
            group_a=group_a,
            group_b=group_b,
            paired=False,
            multiple_testing=req.multiple_testing,
            alpha=req.alpha,
        )
        stats_res = run_statistical_test(dataset, stats_req)
        stats_data = stats_res.get("results", [])

    pdf = _ReportPDF()
    pdf.set_auto_page_break(False)

    title = req.title or f"{dataset.name} Report"
    subtitle = req.subtitle or (f"{group_b} vs {group_a}" if group_b and group_a else "")
    if "summary" in sections or "cover" in sections:
        _add_cover(
            pdf,
            title,
            subtitle,
            dataset.name,
            project_name,
            group_a,
            group_b,
            req.prepared_for or "",
            req.prepared_by or "Metabolomics Platform",
            sections,
        )

    if "summary" in sections:
        metrics = _summary_metrics(dataset, group_a, group_b, stats_data, req.p_threshold)
        _add_summary(pdf, metrics, group_a, group_b, req.p_threshold)

    style = req.style or {}

    for section in sections:
        if section == "summary":
            continue
        params = _section_params(section, group_a, group_b, stats_data, req)
        if params is None:
            continue
        plot_type = section
        if section in ("heatmap_unclustered", "heatmap_clustered"):
            plot_type = "heatmap"
        elif section == "pca_score":
            plot_type = "pca"
        elif section == "pca_loadings":
            plot_type = "pca"
        elif section == "pca_scree":
            plot_type = "pca"
        try:
            fig = generate_plot(
                dataset,
                schemas.PlotRequest(plot_type=plot_type, parameters=params, style=style),
            )
        except Exception:
            continue

        title = SECTION_TITLES.get(section, section)
        layout = SECTION_LAYOUTS.get(section, SECTION_LAYOUTS["default"])
        if section == "per_lipid_bars":
            if not isinstance(fig, list):
                continue
            buffers = [_fig_to_png(f, width=600, height=400, scale=2) for f in fig[:req.top_n]]
            if buffers:
                _add_multi_plot_page(pdf, title, buffers)
        else:
            if isinstance(fig, list):
                fig = fig[0] if fig else None
            if not isinstance(fig, dict):
                continue
            img = _fig_to_png(fig, width=layout["width"], height=layout["height"], scale=2)
            _add_plot_page(pdf, title, img, section=section)

    return bytes(pdf.output())

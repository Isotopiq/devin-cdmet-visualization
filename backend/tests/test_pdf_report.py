import numpy as np
import pytest

from app.models import Dataset
from app.schemas import PDFReportRequest
from app.services.pdf_report import build_pdf, _comparison, _groups


def _make_dataset():
    np.random.seed(0)
    n_features = 20
    samples = [f"s{i}" for i in range(1, 7)]
    groups = ["A", "A", "A", "B", "B", "B"]
    data = {s: list(np.random.lognormal(3, 1.5, n_features)) for s in samples}
    return Dataset(
        id=1,
        project_id=1,
        source_file_id=None,
        name="Pilot Dataset",
        feature_type="lipid",
        data_matrix=data,
        sample_metadata={s: g for s, g in zip(samples, groups)},
        feature_metadata=[
            {"feature_id": f"Lipid_{i}", "class": "PC" if i % 2 == 0 else "PE"}
            for i in range(n_features)
        ],
        processing_history=[],
    )


def test_groups_and_comparison():
    dataset = _make_dataset()
    assert _groups(dataset) == ["A", "B"]
    assert _comparison(dataset, "A", "B") == ("A", "B")
    assert _comparison(dataset, None, None) == ("A", "B")


def test_build_pdf_basic():
    dataset = _make_dataset()
    req = PDFReportRequest(
        title="Test Report",
        subtitle="A vs B",
        group_a="A",
        group_b="B",
        sections=[
            "summary",
            "heatmap_clustered",
            "pca_score",
            "pca_loadings",
            "volcano",
            "lipid_class",
        ],
        top_n=4,
        n_perm=20,
    )
    pdf = build_pdf(dataset, "Test Project", req)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_build_pdf_empty_sections():
    dataset = _make_dataset()
    req = PDFReportRequest(sections=[], title="Empty Report")
    pdf = build_pdf(dataset, "Test Project", req)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100


@pytest.mark.parametrize("hstyle", ["lipidone", "seaborn", "matplotlib", "publication"])
def test_build_pdf_heatmap_styles_and_per_lipid(hstyle):
    dataset = _make_dataset()
    req = PDFReportRequest(
        title="Style Test",
        group_a="A",
        group_b="B",
        sections=["summary", "heatmap_clustered", "per_lipid_bars"],
        parameters={
            "heatmap_top_n": 15,
            "heatmap_style": hstyle,
            "scale": "row_zscore",
            "metric": "euclidean",
            "method": "average",
            "cluster_rows": True,
            "cluster_cols": False,
            "selected_groups": ["A", "B"],
            "per_lipid_top_n": 3,
            "test": "anova",
        },
    )
    pdf = build_pdf(dataset, "Test Project", req)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_build_pdf_heatmap_top_n_flows_through():
    dataset = _make_dataset()
    req_small = PDFReportRequest(
        title="TopN Test",
        group_a="A",
        group_b="B",
        sections=["heatmap_clustered"],
        parameters={"heatmap_top_n": 5},
    )
    req_large = PDFReportRequest(
        title="TopN Test",
        group_a="A",
        group_b="B",
        sections=["heatmap_clustered"],
        parameters={"heatmap_top_n": 15},
    )
    pdf_small = build_pdf(dataset, "Test Project", req_small)
    pdf_large = build_pdf(dataset, "Test Project", req_large)
    assert pdf_small.startswith(b"%PDF")
    assert pdf_large.startswith(b"%PDF")
    assert len(pdf_large) >= len(pdf_small)

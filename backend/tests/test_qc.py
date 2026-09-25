import numpy as np
import pytest

from app import models
from app.services.qc import qc_analysis
from app.services.plots import STYLE_DEFAULTS, _apply_base_layout
import plotly.graph_objects as go


def _make_dataset(n_samples=36, n_features=120, seed=42):
    rng = np.random.default_rng(seed)
    groups = (
        ["CTRL"] * 6
        + ["MCT-EGCG"] * 6
        + ["MCT-Veh"] * 6
        + ["SuHX-EGCG"] * 6
        + ["SuHx-Veh"] * 6
        + ["QC-Pool"] * 4
        + ["Blank"] * 2
    )
    samples = [f"Area: JP_{i + 1:03d}.raw (F{i + 1})" for i in range(len(groups))]
    sample_meta = {s: g for s, g in zip(samples, groups)}
    data = {}
    for s, g in zip(samples, groups):
        base = rng.lognormal(8.0, 0.6, n_features)
        if "QC" in g:
            base *= rng.uniform(0.95, 1.05, n_features)
        elif "Blank" in g:
            base *= 0.05
        arr = base.copy()
        mask = rng.random(n_features) < 0.03
        arr[mask] = np.nan
        data[s] = arr.tolist()
    feature_meta = [
        {"name": f"Feature_{i + 1}", "mz": 100 + i, "rt": 1 + i * 0.1}
        for i in range(n_features)
    ]
    return models.Dataset(
        id=1,
        project_id=1,
        source_file_id=1,
        name="Preview",
        feature_type="metabolite",
        data_matrix=data,
        sample_metadata=sample_meta,
        feature_metadata=feature_meta,
        processing_history=[{"step": "import"}],
    )


def test_qc_xaxis_has_one_label_per_sample():
    """Every QC bar/box plot must have a visible x-axis label for every sample."""
    dataset = _make_dataset(36)
    result = qc_analysis(dataset)
    sample_count = len(dataset.sample_metadata)

    for key in ["tic", "missing_pct", "detected_features", "log2_intensity"]:
        fig = result["figures"][key]
        xaxis = fig["layout"]["xaxis"]
        assert xaxis["tickmode"] == "array", key
        assert len(xaxis["tickvals"]) == sample_count, key
        assert len(xaxis["ticktext"]) == sample_count, key
        assert xaxis["tickangle"] == -90, key
        assert xaxis.get("categoryorder") == "array", key
        assert xaxis.get("ticklabeloverflow") == "allow", key
        assert "Area:" not in str(xaxis["ticktext"][0]), key


def test_qc_cv_by_group_xaxis_has_one_label_per_group():
    dataset = _make_dataset(36)
    result = qc_analysis(dataset)
    fig = result["figures"]["cv_by_group"]
    xaxis = fig["layout"]["xaxis"]
    group_count = len(set(dataset.sample_metadata.values()))
    assert xaxis["tickmode"] == "array"
    assert len(xaxis["tickvals"]) == group_count
    assert len(xaxis["ticktext"]) == group_count
    assert xaxis.get("categoryorder") == "array"


def test_apply_base_layout_preserves_array_xaxis():
    """A caller that already set an explicit tick array should keep its angle/font."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["a", "b", "c"], y=[1, 2, 3]))
    fig.update_xaxes(
        tickmode="array",
        tickvals=["a", "b", "c"],
        ticktext=["A", "B", "C"],
        tickangle=-90,
        tickfont={"size": 8},
    )
    _apply_base_layout(fig, dict(STYLE_DEFAULTS), x_labels=["a"] * 30)
    assert fig.layout.xaxis.tickmode == "array"
    assert fig.layout.xaxis.tickangle == -90
    assert fig.layout.xaxis.tickfont.size == 8


def test_qc_group_color_overrides_apply_to_all_group_traces():
    dataset = _make_dataset(36)
    overrides = {"CTRL": "#123456", "MCT-Veh": "#abcdef"}
    result = qc_analysis(dataset, style={"group_color_map": overrides})

    for key in ["tic", "cv_by_group", "pca"]:
        fig = result["figures"][key]
        by_name = {t.get("name"): t for t in fig["data"] if t.get("name")}
        for grp, color in overrides.items():
            assert by_name[grp]["marker"]["color"] == color, (key, grp)
        # Non-overridden groups keep the default palette assignment.
        assert by_name["MCT-EGCG"]["marker"]["color"] in STYLE_DEFAULTS["group_colors"], key


def test_qc_group_color_overrides_ignore_unknown_groups():
    dataset = _make_dataset(36)
    baseline = qc_analysis(dataset)
    result = qc_analysis(dataset, style={"group_color_map": {"Nope": "#000000"}})
    for key in ["tic", "cv_by_group"]:
        assert result["figures"][key]["data"] == baseline["figures"][key]["data"], key

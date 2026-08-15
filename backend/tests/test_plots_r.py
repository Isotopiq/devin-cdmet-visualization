import shutil

import numpy as np
import pandas as pd
import pytest

from app.services import plots_r


def _make_df():
    samples = ["S_A_1", "S_A_2", "S_B_1", "S_B_2"]
    return pd.DataFrame(
        {
            "S_A_1": [1.0, 5.0, 3.0, 8.0],
            "S_A_2": [1.2, 5.1, 3.2, 7.8],
            "S_B_1": [8.0, 1.0, 6.0, 2.0],
            "S_B_2": [7.8, 1.1, 6.1, 2.2],
        },
        index=[0, 1, 2, 3],
    )


def _make_meta():
    return {
        "S_A_1": "A",
        "S_A_2": "A",
        "S_B_1": "B",
        "S_B_2": "B",
    }


def _make_feature_metadata():
    return [
        {"feature_id": "Lipid_1", "name": "PC(34:1)", "class": "PC"},
        {"feature_id": "Lipid_2", "name": "PE(36:2)", "class": "PE"},
        {"feature_id": "Lipid_3", "name": "LPC(16:0)", "class": "LPC"},
        {"feature_id": "Lipid_4", "name": "SM(d18:1/16:0)", "class": "SM"},
    ]


def test_prepare_heatmap_uses_feature_names_and_class_annotation():
    df = _make_df()
    params = {
        "sample_metadata": _make_meta(),
        "feature_metadata": _make_feature_metadata(),
        "scale": "row_zscore",
        "top_n": 10,
        "cluster_rows": True,
        "cluster_cols": False,
    }
    style = {"heatmap_colorscale": "RdBu_r"}
    payload = plots_r._prepare_heatmap_data(df, params, style)

    assert payload["labels_row"] == ["PC(34:1)", "PE(36:2)", "LPC(16:0)", "SM(d18:1/16:0)"]
    assert all("Class" in row for row in payload["annotation_row"])
    assert payload["center_zero"] is True
    assert payload["cellwidth"] > 0
    assert payload["cellheight"] > 0
    assert "A" in payload["group_color_map"]
    assert "B" in payload["group_color_map"]


def test_prepare_heatmap_limits_wide_matrices():
    df = pd.DataFrame(np.random.randn(200, 50))
    params = {
        "sample_metadata": {f"S{i}": "A" for i in range(50)},
        "feature_metadata": [],
        "top_n": 150,
        "scale": "row_zscore",
    }
    style = {"max_heatmap_rows": 80, "max_heatmap_cols": 40}
    payload = plots_r._prepare_heatmap_data(df, params, style)

    assert len(payload["labels_row"]) == 80
    assert len(payload["labels_col"]) == 40
    assert payload["show_rownames"] is True


def test_prepare_per_lipid_bars_sizing_and_color_map():
    df = _make_df()
    params = {
        "sample_metadata": _make_meta(),
        "feature_metadata": _make_feature_metadata(),
        "stats": [
            {"feature_id": "Lipid_1", "padj": 0.01},
            {"feature_id": "Lipid_2", "padj": 0.001},
        ],
        "groups": ["A", "B"],
        "top_n": 4,
    }
    style = {"title_size": 16, "tick_size": 11, "r_bar_width": 0.6}
    payload = plots_r._prepare_per_lipid_bars_data(df, params, style)

    assert len(payload["plots"]) == 4  # 2 features × 2 groups
    assert payload["group_color_map"] == {"A": "#2e6575", "B": "#7eb5c9"}
    assert payload["width"] >= 360
    assert payload["height"] >= 320
    assert payload["bar_width"] == 0.6
    assert all(p["feature_raw"] for p in payload["plots"])


def test_prepare_lipid_class_data():
    df = _make_df()
    params = {
        "sample_metadata": _make_meta(),
        "feature_metadata": _make_feature_metadata(),
    }
    style = {"title_size": 16}
    payload = plots_r._prepare_lipid_class_data(df, params, style)

    classes = {row["class"] for row in payload["data"]}
    assert classes == {"PC", "PE", "LPC", "SM"}
    groups = {row["group"] for row in payload["data"]}
    assert groups == {"A", "B"}
    assert "group_color_map" in payload
    assert payload["width"] > 0 and payload["height"] > 0


def test_prepare_volcano_data():
    params = {
        "stats": [
            {"name": "PC(34:1)", "log2_fold_change": 2.5, "padj": 0.001},
            {"name": "PE(36:2)", "log2_fold_change": -1.2, "padj": 0.1},
        ],
        "fc_threshold": 1.0,
        "p_threshold": 0.05,
    }
    style = {"up_color": "#c44e52", "down_color": "#2e6575", "non_significant_color": "#a0aec0"}
    payload = plots_r._prepare_volcano_data(params, style)

    assert len(payload["points"]) == 2
    assert payload["points"][0]["regulation"] == "up"
    assert payload["points"][1]["regulation"] == "ns"
    assert payload["non_significant_color"] == "#a0aec0"


def test_prepare_pca_data():
    df = _make_df()
    params = {"sample_metadata": _make_meta(), "plot": "score"}
    style = {"group_colors": ["#2e6575", "#7eb5c9"]}
    payload = plots_r._prepare_pca_data(df, params, style)

    assert len(payload["points"]) == 4
    assert payload["group_color_map"] == {"A": "#2e6575", "B": "#7eb5c9"}
    assert "PC1" in payload["pc1_label"]
    assert "PC2" in payload["pc2_label"]


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not installed")
def test_heatmap_r_script_runs():
    df = _make_df()
    params = {
        "sample_metadata": _make_meta(),
        "feature_metadata": _make_feature_metadata(),
        "scale": "row_zscore",
    }
    style = {"heatmap_colorscale": "RdBu_r"}
    payload = plots_r._prepare_heatmap_data(df, params, style)
    data = plots_r._run_r_script("heatmap.R", payload)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

import numpy as np
import pandas as pd
import pytest

from app import models, schemas
from app.services.isotope import (
    _lipid_class,
    _compute_class_labeling,
    _compute_class_differences,
    run_isotope_analysis,
)


def test_lipid_class_extraction():
    assert _lipid_class("PC(34:1)") == "PC"
    assert _lipid_class("LPC(14:0)") == "LPC"
    assert _lipid_class("SM(d18:1/16:0)") == "SM"
    assert _lipid_class("PE(O-36:3)") == "PE"
    assert _lipid_class("TG(16:0/18:1/18:2)") == "TG"
    assert _lipid_class("123_unknown") == "Other"


def test_compute_class_labeling_averages_by_class():
    fractions = {
        "LPC(14:0)": {"M+0": 0.9, "M+1": 0.1},
        "LPC(16:0)": {"M+0": 0.8, "M+1": 0.2},
        "PC(34:1)": {"M+0": 0.7, "M+1": 0.3},
    }
    out = _compute_class_labeling(fractions)
    assert out["LPC"]["M+0"] == pytest.approx(0.85)
    assert out["LPC"]["M+1"] == pytest.approx(0.15)
    assert out["PC"]["M+0"] == pytest.approx(0.7)
    assert out["PC"]["feature_count"] == 1


def test_compute_class_differences():
    ref = {
        "LPC": {"M+0": 0.9, "M+1": 0.1, "feature_count": 2},
        "PC": {"M+0": 0.8, "M+1": 0.2, "feature_count": 1},
    }
    cmp = {
        "LPC": {"M+0": 0.8, "M+1": 0.2, "feature_count": 2},
        "PC": {"M+0": 0.85, "M+1": 0.15, "feature_count": 1},
    }
    diffs = _compute_class_differences(ref, cmp)
    assert diffs["LPC"]["M+0"] == pytest.approx(-0.1)
    assert diffs["LPC"]["M+1"] == pytest.approx(0.1)
    assert diffs["LPC"]["M+0_pct"] == pytest.approx(-10.0)


@pytest.mark.asyncio
async def test_isotope_class_labeling_and_group_differences():
    # Build a wide isotopologue matrix with CTRL and KO groups.
    columns = ["CTRL_M+0", "CTRL_M+1", "KO_M+0", "KO_M+1"]
    data = np.array([
        [90, 10, 80, 20],   # LPC(14:0)
        [80, 20, 70, 30],   # LPC(16:0)
        [95, 5, 90, 10],    # PC(34:1)
    ])
    df = pd.DataFrame(data, columns=columns)
    ds = models.Dataset(
        id=1,
        project_id=1,
        source_file_id=1,
        name="test",
        feature_type="lipid",
        data_matrix={c: df[c].tolist() for c in df.columns},
        sample_metadata={
            "CTRL_M+0": "CTRL", "CTRL_M+1": "CTRL",
            "KO_M+0": "KO", "KO_M+1": "KO",
        },
        feature_metadata=[
            {"feature_id": "LPC(14:0)"},
            {"feature_id": "LPC(16:0)"},
            {"feature_id": "PC(34:1)"},
        ],
        processing_history=[{"step": "import"}],
    )
    req = schemas.IsotopeRequest(
        tracer="D",
        max_label=1,
        class_reference_group="CTRL",
        class_compare_group="KO",
    )
    result = await run_isotope_analysis(ds, req)
    assert "error" not in result or result.get("error") is None
    assert "class_labeling" in result
    assert "overall" in result["class_labeling"]
    assert "CTRL" in result["class_labeling"]
    assert "KO" in result["class_labeling"]
    assert "LPC" in result["class_labeling"]["overall"]
    assert "PC" in result["class_labeling"]["overall"]
    assert "class_differences" in result
    assert result["class_reference_group"] == "CTRL"
    assert result["class_compare_group"] == "KO"
    # KO is more labeled than CTRL for LPC.
    ko_lpc_m1 = result["class_labeling"]["KO"]["LPC"]["M+1"]
    ctrl_lpc_m1 = result["class_labeling"]["CTRL"]["LPC"]["M+1"]
    assert ko_lpc_m1 > ctrl_lpc_m1
    assert result["class_differences"]["LPC"]["M+1"] > 0

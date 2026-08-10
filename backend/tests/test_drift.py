import numpy as np
import pandas as pd
import pytest

from app.services.drift import (
    auto_detect_qc_pool_group,
    _run_order_map,
    correct_qc_pool_drift,
)


def test_auto_detect_qc_pool_group():
    meta = {
        "S1": "Control",
        "S2": "Control",
        "QC1": "QC-Pool",
        "QC2": "QC-Pool",
    }
    assert auto_detect_qc_pool_group(meta) == "QC-Pool"
    # Falls back to any QC group
    meta2 = {"S1": "A", "S2": "B", "Q1": "Quality Control", "Q2": "Quality Control"}
    assert auto_detect_qc_pool_group(meta2) == "Quality Control"
    # Returns None when nothing matches
    assert auto_detect_qc_pool_group({"S1": "A"}) is None


def test_run_order_map_defaults_to_column_order():
    df = pd.DataFrame({"C": [1], "A": [2], "B": [3]})
    mapping = _run_order_map(df, None)
    assert mapping == {"C": 0, "A": 1, "B": 2}


def test_run_order_map_fills_missing_columns():
    df = pd.DataFrame({"C": [1], "A": [2], "B": [3]})
    mapping = _run_order_map(df, {"A": 10, "B": 5})
    assert mapping["A"] == 10
    assert mapping["B"] == 5
    assert mapping["C"] > 10


@pytest.fixture
def declining_qc_df():
    rng = np.random.default_rng(42)
    # 30 samples, 5 features, QC-Pool at positions 5, 15, 25 with declining TIC
    samples = [f"S{i}" for i in range(30)]
    base = 1000.0
    features = [f"F{i}" for i in range(5)]
    data = {}
    for i, s in enumerate(samples):
        # Drift: linear decline across the run
        drift = 1 - (i / 50)
        data[s] = base * drift + rng.normal(0, 20, 5)
    df = pd.DataFrame(data, index=features)
    # Force QC-Pool samples to decline strongly
    qc_positions = [5, 15, 25]
    for rank, pos in enumerate(qc_positions):
        df.iloc[:, pos] = df.iloc[:, pos] * (1 - rank * 0.2)
    sample_meta = {s: "Sample" for s in samples}
    for pos in qc_positions:
        sample_meta[samples[pos]] = "QC-Pool"
    return df, sample_meta, qc_positions


def test_qc_pool_drift_correction_scales_later_samples_up(declining_qc_df):
    df, sample_meta, qc_positions = declining_qc_df
    params = {
        "qc_pool_drift_correction": True,
        "qc_pool_group": None,  # auto-detect
        "qc_pool_method": "loess_tic",
        "qc_pool_space": "log",
        "qc_pool_span": 0.75,
        "qc_pool_target": "median",
        "qc_pool_extrapolate": "last",
    }
    corrected, diagnostics = correct_qc_pool_drift(df, sample_meta, params)
    assert corrected.shape == df.shape
    assert not corrected.isna().any().any()

    # Later QC samples should be scaled closer to earlier QCs
    raw_qc_tics = df.iloc[:, qc_positions].sum(axis=0).to_numpy()
    corrected_qc_tics = corrected.iloc[:, qc_positions].sum(axis=0).to_numpy()
    assert np.std(corrected_qc_tics) < np.std(raw_qc_tics)

    # The last sample (outside QC range) should be scaled up because drift declines
    raw_last_tic = float(df.iloc[:, -1].sum())
    corrected_last_tic = float(corrected.iloc[:, -1].sum())
    assert corrected_last_tic > raw_last_tic


def test_qc_pool_drift_correction_raw_space(declining_qc_df):
    df, sample_meta, qc_positions = declining_qc_df
    params = {
        "qc_pool_drift_correction": True,
        "qc_pool_group": "QC-Pool",
        "qc_pool_method": "linear_tic",
        "qc_pool_space": "raw",
        "qc_pool_span": 0.75,
        "qc_pool_target": "median",
        "qc_pool_extrapolate": "linear",
    }
    corrected, diagnostics = correct_qc_pool_drift(df, sample_meta, params)
    assert corrected.shape == df.shape
    assert not corrected.isna().any().any()


def test_qc_pool_drift_per_feature(declining_qc_df):
    df, sample_meta, qc_positions = declining_qc_df
    params = {
        "qc_pool_drift_correction": True,
        "qc_pool_group": "QC-Pool",
        "qc_pool_method": "loess_per_feature",
        "qc_pool_space": "log",
        "qc_pool_span": 0.75,
        "qc_pool_target": "first",
        "qc_pool_extrapolate": "linear",
    }
    corrected, diagnostics = correct_qc_pool_drift(df, sample_meta, params)
    assert corrected.shape == df.shape
    assert "features" in diagnostics or "feature_count" in diagnostics


def test_qc_pool_drift_no_qc_group_raises():
    df = pd.DataFrame({"S1": [1, 2], "S2": [3, 4]})
    meta = {"S1": "A", "S2": "A"}
    params = {"qc_pool_group": None}
    with pytest.raises(Exception):
        correct_qc_pool_drift(df, meta, params)


def test_qc_pool_drift_too_few_qc_raises():
    df = pd.DataFrame({"S1": [1, 2], "S2": [3, 4], "QC1": [5, 6]})
    meta = {"S1": "A", "S2": "A", "QC1": "QC-Pool"}
    params = {"qc_pool_group": "QC-Pool"}
    with pytest.raises(Exception):
        correct_qc_pool_drift(df, meta, params)

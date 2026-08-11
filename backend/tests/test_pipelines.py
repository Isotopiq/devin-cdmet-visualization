import math
import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.services.preprocessing import _to_json_safe, _positive_floor, preprocess_dataset, to_dataframe
from app.services.stats import _safe_log2fc, run_statistical_test
from app.services.plots import generate_plot
from app.services.isotope import run_isotope_analysis, _correct_natural_abundance
from app.services.importer import _pivot_el_maven
from app.services.detection import detect_file_format, detect_columns


def test_to_json_safe_replaces_infinities():
    assert _to_json_safe(float("inf")) is None
    assert _to_json_safe(float("-inf")) is None
    assert _to_json_safe(float("nan")) is None
    assert _to_json_safe({"a": [1, np.nan, np.inf]}) == {"a": [1, None, None]}


def test_safe_log2fc_handles_zeros_and_negatives():
    assert _safe_log2fc(0, 0) == 0.0
    assert _safe_log2fc(1.0, 2.0) == pytest.approx(1.0)
    assert _safe_log2fc(-1.0, 2.0) is None
    assert _safe_log2fc(0.0, 5.0) > 0


def _make_dataset(df: pd.DataFrame, groups=None) -> models.Dataset:
    groups = groups or {c: "A" if i < len(df.columns) // 2 else "B" for i, c in enumerate(df.columns)}
    return models.Dataset(
        id=1,
        project_id=1,
        source_file_id=1,
        name="test",
        feature_type="metabolite",
        data_matrix={c: df[c].tolist() for c in df.columns},
        sample_metadata=groups,
        feature_metadata=[{"feature_id": f"F{i}"} for i in range(len(df))],
        processing_history=[{"step": "import"}],
    )


@pytest_asyncio.fixture
async def dataset_for_preprocess():
    np.random.seed(42)
    samples = [f"S{i}" for i in range(12)]
    df = pd.DataFrame(np.random.lognormal(3, 1, (10, 12)), columns=samples)
    # Inject a few missing values
    df.iloc[0, 0] = np.nan
    df.iloc[1, 2] = np.nan
    groups = {samples[i]: "A" if i < 6 else "B" for i in range(12)}
    return _make_dataset(df, groups)


@pytest.mark.asyncio
async def test_preprocess_total_area_no_infinities(dataset_for_preprocess):
    params = schemas.PreprocessingParams(
        missing_value_filter=0.2,
        imputation="min",
        log_transform=True,
        scale="standard",
        normalization="total_area",
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, dataset_for_preprocess, params)
    df = to_dataframe(new)
    assert df.shape[0] > 0
    assert df.notna().all().all()
    assert not np.isinf(df.values).any()
    # Standard scaling is applied per feature (row), so each feature has
    # mean ~0 and std ~1 across samples.
    assert np.allclose(df.mean(axis=1), 0, atol=1e-6)
    assert np.allclose(df.std(axis=1, ddof=0), 1, atol=1e-6)


@pytest.mark.asyncio
async def test_preprocess_total_area_normalizes_samples(dataset_for_preprocess):
    params = schemas.PreprocessingParams(
        missing_value_filter=0.2,
        imputation="min",
        log_transform=False,
        scale="none",
        normalization="total_area",
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, dataset_for_preprocess, params)
    df = to_dataframe(new)
    # After total-area normalization on raw intensities, sample sums equal the median total area.
    sample_sums = df.sum()
    assert sample_sums.max() - sample_sums.min() < 1e-6


@pytest.mark.asyncio
async def test_stats_on_processed_data(dataset_for_preprocess):
    params = schemas.PreprocessingParams(
        missing_value_filter=0.2,
        imputation="min",
        log_transform=True,
        normalization="total_area",
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, dataset_for_preprocess, params)
    req = schemas.StatsRequest(test="t_test", group_a="A", group_b="B", multiple_testing="fdr_bh", alpha=0.05)
    results = run_statistical_test(new, req)
    assert results["n_features"] > 0
    for r in results["results"]:
        assert r["pvalue"] is not None
        assert math.isfinite(r["pvalue"])
        assert r.get("padj") is None or math.isfinite(r["padj"])


def test_generate_box_plot():
    df = pd.DataFrame({"S1": [1, 2, 3], "S2": [1, 2, 3], "S3": [4, 5, 6], "S4": [4, 5, 6]})
    ds = _make_dataset(df, {"S1": "A", "S2": "A", "S3": "B", "S4": "B"})
    req = schemas.PlotRequest(plot_type="box", parameters={"feature": 0})
    fig = generate_plot(ds, req)
    assert "data" in fig


def test_generate_plot_rename_samples():
    df = pd.DataFrame({"EL-001": [1, 2, 3], "EL-002": [1, 2, 3], "EL-003": [4, 5, 6], "EL-004": [4, 5, 6]})
    ds = _make_dataset(df, {"EL-001": "FLVCR1-KO", "EL-002": "FLVCR1-KO", "EL-003": "FLVCR1-CTRL", "EL-004": "FLVCR1-CTRL"})
    req = schemas.PlotRequest(plot_type="bar", parameters={"feature": 0, "rename_samples": True})
    fig = generate_plot(ds, req)
    assert "data" in fig
    all_x = [label for t in fig["data"] for label in t["x"]]
    assert "FLVCR1-KO_R1" in all_x
    assert "FLVCR1-CTRL_R2" in all_x


@pytest.mark.asyncio
async def test_preprocess_rename_samples(dataset_for_preprocess):
    params = schemas.PreprocessingParams(
        missing_value_filter=0.0,
        imputation="min",
        log_transform=False,
        scale="none",
        normalization="none",
        rename_samples=True,
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, dataset_for_preprocess, params)
    assert all("_R" in c for c in new.sample_metadata)
    assert new.sample_metadata == {c: new.sample_metadata[c] for c in new.data_matrix}


def test_biomarker_multi_group_generates_multiple_figures():
    samples = [f"S{i}" for i in range(9)]
    df = pd.DataFrame(np.random.lognormal(3, 1, (10, 9)), columns=samples)
    groups = {samples[i]: "A" if i < 3 else ("B" if i < 6 else "C") for i in range(9)}
    ds = models.Dataset(
        id=1, project_id=1, source_file_id=1, name="biomarker_test",
        feature_type="metabolite",
        data_matrix={c: df[c].tolist() for c in df.columns},
        sample_metadata=groups,
        feature_metadata=[{"feature_id": f"F{i}"} for i in range(10)],
        processing_history=[{"step": "import"}],
    )
    req = schemas.PlotRequest(plot_type="biomarker", parameters={"comparisons": [{"group_a": "A", "group_b": "B"}, {"group_a": "A", "group_b": "C"}]})
    result = generate_plot(ds, req)
    assert isinstance(result, list)
    assert len(result) == 2
    for fig in result:
        assert "data" in fig


def test_chain_space_multi_group_generates_pairwise_figures():
    samples = [f"S{i}" for i in range(9)]
    df = pd.DataFrame(np.random.lognormal(3, 1, (6, 9)), columns=samples)
    groups = {samples[i]: "A" if i < 3 else ("B" if i < 6 else "C") for i in range(9)}
    feature_meta = [
        {"feature_id": "PC(16:0_18:1)"},
        {"feature_id": "PE(18:0_20:4)"},
        {"feature_id": "TG(16:0_18:1_18:2)"},
        {"feature_id": "LPC(14:0)"},
        {"feature_id": "SM(d18:1/24:0)"},
        {"feature_id": "Cer(d18:1/24:1)"},
    ]
    ds = models.Dataset(
        id=1,
        project_id=1,
        source_file_id=1,
        name="chain_test",
        feature_type="lipid",
        data_matrix={c: df[c].tolist() for c in df.columns},
        sample_metadata=groups,
        feature_metadata=feature_meta,
        processing_history=[{"step": "import"}],
    )
    req = schemas.PlotRequest(plot_type="chain_space", parameters={"group_a": "A", "selected_groups": ["A", "B", "C"]})
    result = generate_plot(ds, req)
    assert isinstance(result, list)
    assert len(result) == 2
    for fig in result:
        assert "data" in fig
        assert "layout" in fig
        title = fig["layout"].get("title", {})
        text = title.get("text") if isinstance(title, dict) else title
        assert text and "A" in text


@pytest.mark.asyncio
async def test_isotope_no_isotopologue_columns_returns_clear_error():
    df = pd.DataFrame({"S1": [1, 2], "S2": [3, 4]})
    ds = _make_dataset(df)
    req = schemas.IsotopeRequest(tracer="13C", max_label=6)
    result = await run_isotope_analysis(ds, req)
    assert "error" in result


@pytest.mark.asyncio
async def test_preprocess_qc_pool_drift_correction():
    rng = np.random.default_rng(7)
    samples = [f"S{i}" for i in range(20)]
    df = pd.DataFrame(rng.lognormal(3, 1, (5, 20)), columns=samples)
    # QC-Pool samples at positions 2, 10, 18 with declining signal
    qc_positions = [2, 10, 18]
    for rank, pos in enumerate(qc_positions):
        df.iloc[:, pos] *= 1 - rank * 0.25
    groups = {s: "Sample" for s in samples}
    for pos in qc_positions:
        groups[samples[pos]] = "QC-Pool"
    ds = _make_dataset(df, groups)
    params = schemas.PreprocessingParams(
        missing_value_filter=0.0,
        imputation="min",
        log_transform=False,
        scale="none",
        normalization="none",
        qc_pool_drift_correction=True,
        qc_pool_method="loess_tic",
        qc_pool_space="log",
        qc_pool_target="median",
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, ds, params)
    out_df = to_dataframe(new)
    # QC-Pool TICs should be compressed after correction
    qc_tic_raw = df.iloc[:, qc_positions].sum().to_numpy()
    qc_tic_corr = out_df.iloc[:, qc_positions].sum().to_numpy()
    assert np.std(qc_tic_corr) < np.std(qc_tic_raw)
    # History records the drift correction
    assert any(step.get("step") == "preprocessing" and "qc_pool_drift" in step for step in new.processing_history)


@pytest.mark.asyncio
async def test_preprocess_exclude_blanks_from_imputation_manual():
    df = pd.DataFrame(
        {"S1": [np.nan, 2.0, 3.0], "S2": [1.0, 2.0, 3.0], "S3": [np.nan, 5.0, 6.0], "S4": [4.0, 5.0, 6.0]},
        index=["F1", "F2", "F3"],
    )
    ds = _make_dataset(df, {"S1": "Blank", "S2": "Blank", "S3": "A", "S4": "A"})
    params = schemas.PreprocessingParams(
        missing_value_filter=0.0,
        imputation="min",
        blank_columns=["S1"],
        exclude_blanks_from_imputation=True,
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, ds, params)
    out_df = to_dataframe(new)
    # Blank sample missing value should remain missing; non-blank missing value should be imputed.
    assert pd.isna(out_df.loc[0, "S1"])
    assert not pd.isna(out_df.loc[0, "S3"])


@pytest.mark.asyncio
async def test_preprocess_exclude_blanks_from_imputation_auto_detection():
    df = pd.DataFrame(
        {"S1": [np.nan, 2.0, 3.0], "S2": [1.0, np.nan, 3.0], "S3": [np.nan, 5.0, 6.0], "S4": [4.0, 5.0, 6.0]},
        index=["F1", "F2", "F3"],
    )
    ds = _make_dataset(df, {"S1": "Blank 1", "S2": "Blank 1", "S3": "A", "S4": "A"})
    params = schemas.PreprocessingParams(
        missing_value_filter=0.0,
        imputation="min",
        exclude_blanks_from_imputation=True,
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, ds, params)
    out_df = to_dataframe(new)
    # Auto-detected blank columns should not be imputed.
    assert pd.isna(out_df.loc[0, "S1"])
    assert pd.isna(out_df.loc[1, "S2"])
    assert not pd.isna(out_df.loc[0, "S3"])


@pytest.mark.asyncio
async def test_preprocess_exclude_blanks_from_imputation_with_normalization_log():
    df = pd.DataFrame(
        {"S1": [np.nan, 2.0, 3.0], "S2": [1.0, 2.0, 3.0], "S3": [np.nan, 5.0, 6.0], "S4": [4.0, 5.0, 6.0]},
        index=["F1", "F2", "F3"],
    )
    ds = _make_dataset(df, {"S1": "Blank", "S2": "Blank", "S3": "A", "S4": "A"})
    params = schemas.PreprocessingParams(
        missing_value_filter=0.0,
        imputation="min",
        blank_columns=["S1"],
        exclude_blanks_from_imputation=True,
        normalization="total_area",
        log_transform=True,
    )
    fake_db = _FakeAsyncSession()
    new = await preprocess_dataset(fake_db, ds, params)
    out_df = to_dataframe(new)
    assert pd.isna(out_df.loc[0, "S1"])
    assert not pd.isna(out_df.loc[0, "S3"])
    assert not out_df.isin([np.inf, -np.inf]).any().any()


class _FakeAsyncSession:
    """Minimal async session double used to exercise preprocess_dataset without a DB."""

    def __init__(self):
        self._objects = []

    def add(self, obj):
        self._objects.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        obj.id = 1


def _make_el_maven_df() -> pd.DataFrame:
    return pd.DataFrame({
        "label": ["", ""],
        "metaGroupId": [1, 1],
        "groupId": [1, 2],
        "goodPeakCount": [10, 5],
        "medMz": [468.3, 469.3],
        "medRt": [3.0, 3.0],
        "maxQuality": [0.8, 0.7],
        "adductName": ["[M+H]+", ""],
        "isotopeLabel": ["C12 PARENT", "D2-label-1"],
        "compound": ["LPC(14:0)", "LPC(14:0)"],
        "compoundId": ["LPC(14:0)", "LPC(14:0)"],
        "formula": ["C22H46NO7P", "C22H46NO7P"],
        "expectedRtDiff": [0.0, 0.0],
        "ppmDiff": [0.0, 0.0],
        "parent": [468.3, 468.3],
        "FLVCR1-ETN_CTRL_R1_pos": [1000.0, 50.0],
        "FLVCR1-ETN_CTRL_R2_pos": [1100.0, 60.0],
        "FLVCR1-ETN_KO_R1_pos": [900.0, 200.0],
        "QC-Pool1_pos": [1000.0, 70.0],
    })


def test_el_maven_format_detection():
    df = _make_el_maven_df()
    result = detect_columns(df)
    assert set(result["sample_columns"]) == {
        "FLVCR1-ETN_CTRL_R1_pos", "FLVCR1-ETN_CTRL_R2_pos",
        "FLVCR1-ETN_KO_R1_pos", "QC-Pool1_pos",
    }
    assert result["sample_groups"] == {
        "FLVCR1-ETN_CTRL_R1_pos": "FLVCR1-ETN_CTRL",
        "FLVCR1-ETN_CTRL_R2_pos": "FLVCR1-ETN_CTRL",
        "FLVCR1-ETN_KO_R1_pos": "FLVCR1-ETN_KO",
        "QC-Pool1_pos": "QC-Pool",
    }
    assert result["suggested_mapping"]["feature_id"] == "compound"


def test_el_maven_pivot_produces_m_columns():
    df = _make_el_maven_df()
    pivoted = _pivot_el_maven(df, "test.csv", "lipid", [])
    assert len(pivoted["feature_metadata"]) == 1
    assert pivoted["feature_metadata"][0]["feature_id"] == "LPC(14:0)"
    assert pivoted["feature_metadata"][0]["formula"] == "C22H46NO7P"
    # 4 sample columns x (M+0..M+1) = 8 columns
    assert len(pivoted["data_matrix"]) == 8
    assert set(pivoted["sample_metadata"].values()) == {"FLVCR1-ETN_CTRL", "FLVCR1-ETN_KO", "QC-Pool"}
    # Parent M+0 value should be preserved.
    assert pivoted["data_matrix"]["FLVCR1-ETN_CTRL_R1_pos_M+0"][0] == 1000.0
    assert pivoted["data_matrix"]["FLVCR1-ETN_KO_R1_pos_M+1"][0] == 200.0


def test_natural_abundance_correction_reduces_unlabeled_m1():
    # C22 with 13C natural abundance: a pure M+0 metabolite should have ~23% M+1
    # from natural 13C. After correction M+1 should be near zero.
    iso = pd.DataFrame({
        "M+0": [0.77],
        "M+1": [0.21],
        "M+2": [0.02],
    }, index=[0])
    corrected = _correct_natural_abundance(iso, formulas=["C22H46NO7P"], tracer="13C", max_label=2)
    assert corrected.loc[0, "M+0"] > 0.95
    assert corrected.loc[0, "M+1"] < 0.05
    assert abs(corrected.sum(axis=1).iloc[0] - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_isotope_analysis_on_el_maven_pivot():
    df = _make_el_maven_df()
    pivoted = _pivot_el_maven(df, "test.csv", "lipid", [])
    ds = models.Dataset(
        id=1,
        project_id=1,
        source_file_id=1,
        name="test",
        feature_type="lipid",
        data_matrix=pivoted["data_matrix"],
        sample_metadata=pivoted["sample_metadata"],
        feature_metadata=pivoted["feature_metadata"],
        processing_history=pivoted["processing_history"],
    )
    req = schemas.IsotopeRequest(tracer="D", max_label=1, natural_abundance_correction=True)
    result = await run_isotope_analysis(ds, req)
    assert "error" not in result or result.get("error") is None
    assert "fractions" in result
    assert "FLVCR1-ETN_CTRL" in result["groups"]
    assert "FLVCR1-ETN_KO" in result["groups"]
    # KO has stronger M+1 labeling than CTRL
    ko_frac = result["groups"]["FLVCR1-ETN_KO"]["fractions"]["LPC(14:0)"]["M+1"]
    ctrl_frac = result["groups"]["FLVCR1-ETN_CTRL"]["fractions"]["LPC(14:0)"]["M+1"]
    assert ko_frac > ctrl_frac

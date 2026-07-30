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
from app.services.isotope import run_isotope_analysis


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
    # After total-area normalization, sample sums should be equal (median)
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


@pytest.mark.asyncio
async def test_isotope_no_isotopologue_columns_returns_clear_error():
    df = pd.DataFrame({"S1": [1, 2], "S2": [3, 4]})
    ds = _make_dataset(df)
    req = schemas.IsotopeRequest(tracer="13C", max_label=6)
    result = await run_isotope_analysis(ds, req)
    assert "error" in result


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

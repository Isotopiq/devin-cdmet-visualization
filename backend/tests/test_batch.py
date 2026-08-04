import uuid
import pytest
import pytest_asyncio
import numpy as np
import app.database as db_module
from app import models
from app.services.batch import combine_datasets


@pytest_asyncio.fixture
async def batch_setup(setup_db):
    async with db_module.AsyncSessionLocal() as db:
        db.expire_on_commit = False
        email = f"batch_{uuid.uuid4().hex[:8]}@example.com"
        user = models.User(email=email, hashed_password="x", is_active=True)
        project = models.Project(name="batch project", owner=user)
        db.add(user)
        db.add(project)
        await db.flush()

        user_id = user.id
        project_id = project.id

        ds1 = models.Dataset(
            project_id=project_id,
            name="run1.csv",
            feature_type="metabolite",
            data_matrix={
                "s1": [100.0, 200.0],
                "s2": [110.0, 190.0],
                "s3": [1000.0, 400.0],
            },
            sample_metadata={"s1": "CTRL", "s2": "CTRL", "s3": "TREAT"},
            feature_metadata=[{"feature_id": "A"}, {"feature_id": "B"}],
            processing_history=[{"step": "import"}],
        )
        ds2 = models.Dataset(
            project_id=project_id,
            name="run2.csv",
            feature_type="metabolite",
            data_matrix={
                "s1": [200.0, 80.0],
                "s2": [220.0, 90.0],
                "s4": [600.0, 300.0],
            },
            sample_metadata={"s1": "CTRL", "s2": "CTRL", "s4": "TREAT"},
            feature_metadata=[{"feature_id": "A"}, {"feature_id": "C"}],
            processing_history=[{"step": "import"}],
        )
        db.add(ds1)
        db.add(ds2)
        await db.commit()
        await db.refresh(ds1)
        await db.refresh(ds2)
        yield db, user_id, project_id, ds1.id, ds2.id


@pytest.mark.asyncio
async def test_combine_reference_group(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="reference_group",
        batch_assignment={str(ds1_id): "run1", str(ds2_id): "run2"},
        reference_group="CTRL",
        output_name="combined_ref",
    )
    assert new_ds.name == "combined_ref"
    assert new_ds.sample_metadata is not None
    assert len(new_ds.sample_metadata) == 6
    assert len(new_ds.feature_metadata) == 3
    fids = [m["feature_id"] for m in new_ds.feature_metadata]
    assert set(fids) == {"A", "B", "C"}
    df = new_ds.data_matrix
    ctrl_samples = [s for s, g in new_ds.sample_metadata.items() if g == "CTRL"]
    for idx in range(3):
        vals = [df[s][idx] if df[s][idx] is not None else np.nan for s in ctrl_samples]
        assert np.nanmean(vals) == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_combine_log2fc(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="log2fc_control",
        batch_assignment={},
        reference_group="CTRL",
        output_name=None,
    )
    assert new_ds.name == "combined_log2fc_control"
    df = new_ds.data_matrix
    ctrl_samples = [s for s, g in new_ds.sample_metadata.items() if g == "CTRL"]
    for idx in range(3):
        vals = [df[s][idx] if df[s][idx] is not None else np.nan for s in ctrl_samples]
        assert np.nanmean(vals) == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_combine_quantile_normalization(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="quantile_normalization",
        batch_assignment={},
        reference_group=None,
        output_name=None,
    )
    assert new_ds.name == "combined_quantile_normalization"
    assert len(new_ds.sample_metadata) == 6
    means = [
        np.nanmean([v if v is not None else np.nan for v in new_ds.data_matrix[s]])
        for s in new_ds.data_matrix
    ]
    assert max(means) - min(means) < 1e-6


@pytest.mark.asyncio
async def test_combine_requires_two_datasets(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    with pytest.raises(Exception):
        await combine_datasets(
            db,
            project_id=project_id,
            user_id=user_id,
            dataset_ids=[ds1_id],
            method="mean_centering",
            batch_assignment={},
            reference_group=None,
            output_name=None,
        )


@pytest.mark.asyncio
async def test_combine_combat(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="combat",
        batch_assignment={str(ds1_id): "run1", str(ds2_id): "run2"},
        reference_group=None,
        output_name="combined_combat",
    )
    assert new_ds.name == "combined_combat"
    assert len(new_ds.sample_metadata) == 6
    assert len(new_ds.feature_metadata) == 3
    # all values finite (no NaN/None/inf)
    for s, vals in new_ds.data_matrix.items():
        for v in vals:
            assert v is None or (isinstance(v, float) and np.isfinite(v))


@pytest.mark.asyncio
async def test_combine_loess(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="loess_signal_drift",
        batch_assignment={str(ds1_id): "run1", str(ds2_id): "run2"},
        reference_group=None,
        output_name="combined_loess",
    )
    assert new_ds.name == "combined_loess"
    assert len(new_ds.sample_metadata) == 6
    assert len(new_ds.feature_metadata) == 3
    for s, vals in new_ds.data_matrix.items():
        for v in vals:
            assert v is None or (isinstance(v, float) and np.isfinite(v))


@pytest.mark.asyncio
async def test_combine_ruv_iii_c(batch_setup):
    db, user_id, project_id, ds1_id, ds2_id = batch_setup
    new_ds = await combine_datasets(
        db,
        project_id=project_id,
        user_id=user_id,
        dataset_ids=[ds1_id, ds2_id],
        method="ruv_iii_c",
        batch_assignment={str(ds1_id): "run1", str(ds2_id): "run2"},
        reference_group=None,
        output_name="combined_ruv",
        control_features=["A"],
        n_unwanted_factors=1,
    )
    assert new_ds.name == "combined_ruv"
    assert len(new_ds.sample_metadata) == 6
    assert len(new_ds.feature_metadata) == 3
    for s, vals in new_ds.data_matrix.items():
        for v in vals:
            assert v is None or (isinstance(v, float) and np.isfinite(v))

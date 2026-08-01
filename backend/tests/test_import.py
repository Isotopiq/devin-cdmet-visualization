import math
import shutil
from pathlib import Path

import pytest

from app import models
from app.services.importer import import_dataset


CD_LIPIDSET_ATTACHMENT = Path(__file__).parent / "fixtures" / "example-compound-discoverer-export-lipidset.xlsx"
LS_EXPORT_ATTACHMENT = Path(__file__).parent / "fixtures" / "lipidsearch-export.txt"
LS_ALIGNMENT_ATTACHMENT = Path(__file__).parent / "fixtures" / "lipidsearch-alignment.txt"


class _FakeAsyncSession:
    def __init__(self):
        self._objects = []

    def add(self, obj):
        self._objects.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        obj.id = 1


@pytest.fixture
def cd_lipidset_file(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    dest = uploads / "cd_lipidset.xlsx"
    shutil.copy(CD_LIPIDSET_ATTACHMENT, dest)
    monkeypatch.chdir(tmp_path)
    return "cd_lipidset.xlsx"


@pytest.mark.asyncio
async def test_import_cd_lipidset(cd_lipidset_file):
    db = _FakeAsyncSession()
    uploaded = models.UploadedFile()
    uploaded.stored_name = cd_lipidset_file
    uploaded.original_name = "cd_lipidset.xlsx"
    uploaded.project_id = 1
    uploaded.selected_sheet = None
    uploaded.column_mapping = None
    uploaded.status = "uploaded"

    dataset = await import_dataset(db, uploaded, feature_type="lipid")

    assert dataset is not None
    assert len(dataset.feature_metadata) == 6
    assert len(dataset.sample_metadata) == 23

    first = dataset.feature_metadata[0]
    assert first["feature_id"] == "PC(33:6COOH)"
    assert first["top_candidate_name"] == "PC(33:6COOH)"
    assert first["top_candidate_grade"] == "C"

    # All sample intensity values should be finite JSON-safe numbers
    for col, values in dataset.data_matrix.items():
        for v in values:
            assert isinstance(v, (int, float, type(None)))
            if isinstance(v, float):
                assert math.isfinite(v)


@pytest.fixture
def lipidsearch_files(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    dest_export = uploads / "lipidsearch_export.txt"
    dest_align = uploads / "lipidsearch_alignment.txt"
    shutil.copy(LS_EXPORT_ATTACHMENT, dest_export)
    shutil.copy(LS_ALIGNMENT_ATTACHMENT, dest_align)
    monkeypatch.chdir(tmp_path)
    return dest_export.name, dest_align.name


@pytest.mark.asyncio
async def test_import_lipidsearch_with_alignment(lipidsearch_files, tmp_path):
    export_name, align_name = lipidsearch_files
    db = _FakeAsyncSession()
    uploaded = models.UploadedFile()
    uploaded.stored_name = export_name
    uploaded.original_name = "lipidsearch_export.txt"
    uploaded.project_id = 1
    uploaded.selected_sheet = None
    uploaded.column_mapping = None
    uploaded.status = "uploaded"

    dataset = await import_dataset(db, uploaded, feature_type="lipid", metadata_path=str(tmp_path / "uploads" / align_name))

    assert dataset is not None
    # 10 data rows from the fixture
    assert len(dataset.feature_metadata) == 10
    assert len(dataset.sample_metadata) == 12

    first = dataset.feature_metadata[0]
    assert first["feature_id"] == "PE(O-16:0)"
    assert first["lipid_class"] == "PE"
    assert first["grade"] == "C"

    # Columns should be renamed to raw sample names from the alignment file.
    assert "FLVCR1-ETN_CTRL_R1" in dataset.sample_metadata
    assert dataset.sample_metadata["FLVCR1-ETN_CTRL_R1"] == "FLVCR1-CTRL"
    assert dataset.sample_metadata["QC-Pool1"] == "QC-Pools"

    for col, values in dataset.data_matrix.items():
        for v in values:
            assert isinstance(v, (int, float, type(None)))
            if isinstance(v, float):
                assert math.isfinite(v)

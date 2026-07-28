import math
import shutil
from pathlib import Path

import pytest

from app import models
from app.services.importer import import_dataset


CD_LIPIDSET_ATTACHMENT = Path(
    "/home/ubuntu/attachments/a3deded1-fad8-48b0-83c5-5230a93d7dda/fDownloadsexample-compound-discoverer-export-lipidset.xlsx"
)


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

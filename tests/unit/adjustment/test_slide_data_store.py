import json
import pytest
from src.core.adjustment.slide_data_store import SlideDataStore


@pytest.fixture
def store_dir(tmp_path):
    d = tmp_path / "slide_data"
    d.mkdir()
    return d


@pytest.fixture
def store(store_dir):
    return SlideDataStore(data_dir=str(store_dir))


def _make_slide_data_list():
    return [
        {"slide_type": "cover", "title": "Report"},
        {"slide_type": "content", "title": "Market Size", "items": ["TAM $10B"]},
    ]


class TestSlideDataStorePersist:
    def test_persist_creates_json_file(self, store, store_dir):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        fpath = store_dir / "t1.json"
        assert fpath.exists()
        loaded = json.loads(fpath.read_text(encoding="utf-8"))
        assert len(loaded["slides"]) == 2

    def test_version_is_loaded_by_a_new_store_instance(self, store_dir):
        first = SlideDataStore(data_dir=str(store_dir), task_id="t1")
        first.persist("t1", _make_slide_data_list())
        second = SlideDataStore(data_dir=str(store_dir), task_id="t1")
        assert second.get_version("t1") == 1

    def test_persist_increments_version(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        assert store.get_version("t1") == 1
        store.persist("t1", sdl)
        assert store.get_version("t1") == 2

    def test_persist_creates_backup(self, store, store_dir):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        sdl[0]["title"] = "Updated"
        store.persist("t1", sdl)
        bak = store_dir / "t1.json.bak"
        assert bak.exists()
        bak_data = json.loads(bak.read_text(encoding="utf-8"))
        assert bak_data["slides"][0]["title"] == "Report"


class TestSlideDataStoreLoad:
    def test_load_returns_slide_data_list(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        loaded = store.load("t1")
        assert loaded[0]["title"] == "Report"

    def test_load_missing_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent")


class TestSlideDataStoreVersion:
    def test_version_starts_at_zero(self, store):
        assert store.get_version("t1") == 0

    def test_version_hash_stored(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        h = store.get_hash("t1")
        assert h is not None
        assert len(h) == 64


class TestSlideDataStorePptxPath:
    def test_set_and_get_pptx_path(self, store):
        store.set_pptx_path("t1", "/output/report.pptx")
        assert store.get_pptx_path("t1") == "/output/report.pptx"

    def test_pptx_path_default_none(self, store):
        assert store.get_pptx_path("t1") is None


class TestSlideDataStoreOptimisticLock:
    def test_check_version_match(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        assert store.check_version("t1", 1) is True

    def test_check_version_mismatch(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        assert store.check_version("t1", 0) is False


class TestSlideDataStoreRecovery:
    def test_restore_from_backup(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        sdl[0]["title"] = "Updated"
        store.persist("t1", sdl)
        store.restore_backup("t1")
        loaded = store.load("t1")
        assert loaded[0]["title"] == "Report"

    def test_pptx_path_survives_persist_and_restore(self, store):
        pptx_path = "/output/report.pptx"
        store.set_pptx_path("t1", pptx_path)
        store.persist("t1", _make_slide_data_list())
        updated = _make_slide_data_list()
        updated[0]["title"] = "Updated"
        store.persist("t1", updated)
        store.restore_backup("t1")
        assert store.get_pptx_path("t1") == pptx_path

    def test_restore_no_backup_raises(self, store):
        sdl = _make_slide_data_list()
        store.persist("t1", sdl)
        with pytest.raises(FileNotFoundError):
            store.restore_backup("t1")

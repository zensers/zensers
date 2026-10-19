import os
import json
import pytest
from src.core.adjustment.ppt_version_manager import PptVersionManager


@pytest.fixture
def version_dir(tmp_path):
    d = tmp_path / "revisions"
    d.mkdir()
    return d


@pytest.fixture
def mgr(version_dir):
    return PptVersionManager(revisions_dir=str(version_dir), max_versions=5)


@pytest.fixture
def pptx_file(tmp_path):
    p = tmp_path / "report.pptx"
    p.write_bytes(b"PK\x03\x04fake_pptx_content_v1")
    return p


class TestSnapshot:
    def test_create_snapshot_copies_pptx(self, mgr, version_dir, pptx_file):
        v = mgr.create_snapshot("t1", str(pptx_file), "L1", "change title")
        assert v == 1
        snap = version_dir / "t1" / "v1.pptx"
        assert snap.exists()
        assert snap.read_bytes() == pptx_file.read_bytes()

    def test_snapshot_increments_version(self, mgr, pptx_file):
        v1 = mgr.create_snapshot("t1", str(pptx_file), "L1", "msg1")
        v2 = mgr.create_snapshot("t1", str(pptx_file), "L2", "msg2")
        assert v1 == 1
        assert v2 == 2

    def test_snapshot_version_continues_across_manager_instances(self, version_dir, pptx_file):
        first = PptVersionManager(revisions_dir=str(version_dir), max_versions=5)
        assert first.create_snapshot("t1", str(pptx_file), "L1", "msg1") == 1
        second = PptVersionManager(revisions_dir=str(version_dir), max_versions=5)
        assert second.create_snapshot("t1", str(pptx_file), "L2", "msg2") == 2

    def test_snapshot_stores_metadata(self, mgr, version_dir, pptx_file):
        mgr.create_snapshot("t1", str(pptx_file), "L3", "modify table")
        meta_path = version_dir / "t1" / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert len(meta) == 1
        assert meta[0]["version"] == 1
        assert meta[0]["revision_level"] == "L3"
        assert meta[0]["user_message"] == "modify table"

    def test_snapshot_stores_slide_data_for_stateful_rollback(self, mgr, version_dir, pptx_file):
        slide_data = [{"slide_type": "content", "title": "Original"}]
        mgr.create_snapshot("t1", str(pptx_file), "L3", "change", slide_data=slide_data)
        snapshot = mgr.get_snapshot_slide_data("t1", 1)
        assert snapshot == slide_data

    def test_max_versions_enforced(self, mgr, version_dir, pptx_file):
        for i in range(7):
            mgr.create_snapshot("t1", str(pptx_file), "L1", f"msg{i}")
        remaining = list((version_dir / "t1").glob("v*.pptx"))
        assert len(remaining) == 5

    def test_metadata_trimmed_with_versions(self, mgr, version_dir, pptx_file):
        for i in range(7):
            mgr.create_snapshot("t1", str(pptx_file), "L1", f"msg{i}")
        meta = json.loads((version_dir / "t1" / "metadata.json").read_text(encoding="utf-8"))
        assert len(meta) == 5
        assert meta[0]["version"] == 3


class TestRollback:
    def test_rollback_restores_pptx(self, mgr, tmp_path, version_dir):
        p1 = tmp_path / "report_v1.pptx"
        p1.write_bytes(b"content_v1")
        p2 = tmp_path / "report_v2.pptx"
        p2.write_bytes(b"content_v2")
        active = tmp_path / "active.pptx"
        active.write_bytes(b"content_v2")

        mgr.create_snapshot("t1", str(p1), "L1", "first")
        mgr.create_snapshot("t1", str(active), "L2", "second")

        mgr.rollback("t1", 1, str(active))
        assert active.read_bytes() == b"content_v1"

    def test_rollback_invalid_version_raises(self, mgr, pptx_file):
        mgr.create_snapshot("t1", str(pptx_file), "L1", "msg")
        with pytest.raises(ValueError):
            mgr.rollback("t1", 99, str(pptx_file))

    def test_rollback_no_snapshots_raises(self, mgr, tmp_path):
        active = tmp_path / "active.pptx"
        active.write_bytes(b"content")
        with pytest.raises(ValueError):
            mgr.rollback("t1", 1, str(active))

    def test_rollback_returns_snapshot_slide_data(self, mgr, tmp_path):
        source = tmp_path / "source.pptx"
        active = tmp_path / "active.pptx"
        source.write_bytes(b"v1")
        active.write_bytes(b"v2")
        slide_data = [{"slide_type": "content", "title": "v1"}]
        mgr.create_snapshot("t1", str(source), "L1", "first", slide_data=slide_data)
        restored = mgr.rollback("t1", 1, str(active))
        assert restored == slide_data


class TestListVersions:
    def test_list_returns_metadata(self, mgr, pptx_file):
        mgr.create_snapshot("t1", str(pptx_file), "L1", "msg1")
        mgr.create_snapshot("t1", str(pptx_file), "L2", "msg2")
        versions = mgr.list_versions("t1")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

    def test_list_empty_task(self, mgr):
        assert mgr.list_versions("nonexistent") == []

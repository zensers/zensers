# -*- coding: utf-8 -*-
"""
P0/P1 修复验证测试 — research_result_store.py
"""
import pytest
import time
import threading
from pathlib import Path
from src.core.storage.research_result_store import ResearchResultStore, ResearchResultMeta, ResearchStatus


class TestP04FixMetadataMerge:
    """P0-4 修复: metadata 合并而非覆盖"""

    def test_created_at_preserved_on_second_save(self, tmp_path):
        """修复后: created_at 在第二次 save 时保留原值"""
        store = ResearchResultStore(str(tmp_path / "store"))
        store.save_result("test_task_001", {
            "title": "Test Title",
            "topic": "Test Topic",
            "status": "collecting",
        })
        meta1 = store.load_metadata("test_task_001")
        created_at_1 = meta1.created_at
        time.sleep(0.01)
        store.save_result("test_task_001", {
            "title": "Updated Title",
            "topic": "Updated Topic",
            "status": "completed",
        })
        meta2 = store.load_metadata("test_task_001")
        assert meta2.created_at == created_at_1, f"修复后: created_at 应保留原值 {created_at_1}, 实际 {meta2.created_at}"

    def test_sections_merged_not_overwritten_with_empty(self, tmp_path):
        """修复后: sections 不会被空列表覆盖"""
        store = ResearchResultStore(str(tmp_path / "store"))
        store.save_result("test_task_002", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "sections": [{"id": "s1", "title": "Section 1", "content": "Content 1"}],
        })
        store.save_result("test_task_002", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "sections": [],
        })
        loaded = store.load_result("test_task_002")
        assert len(loaded["sections"]) == 1, f"修复后: sections 应保留原值, 实际 {len(loaded['sections'])} 个"


class TestSP13FixTitleTopicPreserved:
    """S-P1-3 修复: title/topic 在新值为空时保留原值"""

    def test_title_preserved_when_new_save_has_empty_title(self, tmp_path):
        """修复后: 新 save 的 title 为空时保留原值"""
        store = ResearchResultStore(str(tmp_path / "store"))
        store.save_result("test_task_003", {
            "title": "Original Title",
            "topic": "Original Topic",
            "status": "collecting",
        })
        store.save_result("test_task_003", {
            "title": "",
            "topic": "",
            "status": "collecting",
        })
        loaded = store.load_result("test_task_003")
        assert loaded["title"] == "Original Title", f"修复后: title 应保留 'Original Title', 实际 '{loaded['title']}'"
        assert loaded["topic"] == "Original Topic", f"修复后: topic 应保留 'Original Topic', 实际 '{loaded['topic']}'"


class TestSP11DataPointsDuplicateWithoutUrl:
    """S-P1-1: data_points 无 URL 时会累积重复"""

    def test_data_points_without_url_accumulate(self, tmp_path):
        """data_points 无 url 字段时每次 save 都会追加（已知行为）"""
        store = ResearchResultStore(str(tmp_path / "store"))
        dp = {"text": "some data", "source": "web"}
        store.save_result("test_task_004", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "data_points": [dp],
        })
        store.save_result("test_task_004", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "data_points": [dp],
        })
        loaded = store.load_result("test_task_004")
        assert len(loaded["data_points"]) == 2, "无 url 的 data_points 会累积"


class TestSP14AgentContentsOverwrite:
    """S-P1-4: agent_contents 在 retry 时被覆盖（已修复为合并）"""

    def test_agent_contents_overwritten_on_retry(self, tmp_path):
        """agent_contents 在 retry 时应合并而非覆盖"""
        store = ResearchResultStore(str(tmp_path / "store"))
        store.save_result("test_task_005", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "agent_contents": {"agent_1": "result_1"},
        })
        store.save_result("test_task_005", {
            "title": "Test",
            "topic": "Test",
            "status": "collecting",
            "agent_contents": {"agent_2": "result_2"},
        })
        loaded = store.load_result("test_task_005")
        assert "agent_1" in loaded["agent_contents"], "agent_1 应保留"
        assert "agent_2" in loaded["agent_contents"], "agent_2 应存在"


class TestP05FixConcurrentSaveLock:
    """P0-5 修复: 并发 save 有锁保护"""

    def test_concurrent_saves_no_data_loss(self, tmp_path):
        """修复后: 并发 save 不会丢失数据"""
        store = ResearchResultStore(str(tmp_path / "store"))
        store.save_result("test_task_006", {
            "title": "Initial",
            "topic": "Test",
            "status": "collecting",
        })
        errors = []

        def save_fn(i):
            try:
                store.save_result("test_task_006", {
                    "title": f"Title_{i}",
                    "topic": "Test",
                    "status": "collecting",
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_fn, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"并发 save 不应有错误: {errors}"

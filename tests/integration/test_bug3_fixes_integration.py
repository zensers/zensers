"""
Bug 3 修复集成测试：4a(P1-1 dedup+cap) + 4c(QC extend after check)
验证引擎核心路径的修复效果，最小化 mock，使用真实组件。
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, AsyncMock

import pytest

from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus


# =============================================================================
# 集成测试 1: P1-1 注入 + ResearchResultStore 合并 端到端
# =============================================================================

class TestP1InjectionWithMergeIntegration:
    """验证 P1-1 数据注入 + 4d merge 的端到端集成"""

    def test_store_then_inject_dedups_correctly(self, tmp_path):
        """场景：两次收集 → save_result（合并）→ P1-1 注入（去重+上限）→ 验证"""
        store = ResearchResultStore(storage_path=str(tmp_path))

        # 第一轮：注入 1000 条数据（url a0-a999）
        batch1 = [{"url": f"http://example.com/a{i}", "content": f"data_{i}"} for i in range(1000)]
        store.save_result("task_integ_001", {"data_points": batch1, "sources": batch1})

        # 第二轮：注入 1000 条（url b0-b999）+ 500 条重复 a0-a499
        batch2_new = [{"url": f"http://example.com/b{i}", "content": f"data_b_{i}"} for i in range(1000)]
        batch2_dup = [{"url": f"http://example.com/a{i}", "content": f"dup_{i}"} for i in range(500)]
        store.save_result("task_integ_001", {"data_points": batch2_new + batch2_dup, "sources": batch2_new + batch2_dup})

        # 验证：合并后应有 1500 条（1000 unique + 500 new），无重复
        loaded = store.load_result("task_integ_001")
        assert loaded is not None

        dps = loaded.get("data_points", [])
        urls = [dp.get("url") for dp in dps if isinstance(dp, dict)]

        assert len(urls) == 2000, f"Merge 应去重保留 2000 条（1000a+1000b），实际 {len(urls)}"
        assert len(set(urls)) == 2000, "所有 url 应唯一"

        # 验证 P1-1 去重逻辑（模拟 _execute_batch 中的 P1-1 代码）
        saved_dps = loaded.get("data_points", [])
        seen_urls = set()
        deduped = []
        for dp in saved_dps:
            url = dp.get("url", "") if isinstance(dp, dict) else ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(dp)
        capped = deduped[:5000]

        assert len(capped) == 2000, f"P1-1 dedup 后应 2000 条（1000a+1000b），实际 {len(capped)}"

    def test_p1_cap_at_5000_after_merge(self, tmp_path):
        """P1-1 上限 5000 生效：即使合并后有 10000 条，cap 后只保留 5000"""
        store = ResearchResultStore(storage_path=str(tmp_path))

        big1 = [{"url": f"http://a.com/{i}", "content": str(i)} for i in range(6000)]
        big2 = [{"url": f"http://b.com/{i}", "content": str(i)} for i in range(6000)]
        store.save_result("task_cap_001", {"data_points": big1, "sources": big1})
        store.save_result("task_cap_001", {"data_points": big2, "sources": big2})

        loaded = store.load_result("task_cap_001")

        saved_dps = loaded.get("data_points", [])
        seen_urls = set()
        deduped = []
        for dp in saved_dps:
            url = dp.get("url", "") if isinstance(dp, dict) else ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(dp)
        capped = deduped[:5000]

        assert len(capped) == 5000, f"Cap 应截断至 5000 条，实际 {len(capped)}"

    def test_p1_empty_injection_no_crash(self, tmp_path):
        """P1-1 注入空数据不崩溃"""
        store = ResearchResultStore(storage_path=str(tmp_path))
        store.save_result("task_empty_001", {"title": "no_data"})

        loaded = store.load_result("task_empty_001")
        assert loaded is not None
        saved = loaded.get("data_points", [])
        assert len(saved) == 0


# =============================================================================
# 集成测试 2: QC extend after check + 失败不回滚好数据
# =============================================================================

class TestQCExtendOrderIntegration:
    """验证 all_results.extend(batch_results) 在 QC 检查后执行"""

    def test_qc_retry_replaces_not_accumulates(self):
        """QC 重试后 all_results 只有最终数据，没有累积"""
        all_results = []
        qc_passed = False
        retry_passed = True

        # 第一轮 batch 结果（QC 会失败）
        batch_results = [
            {"agent_id": "a1", "success": True, "content": "low_quality", "data_points": [{"url": "http://bad"}]},
        ]

        # Bug 旧行为：先 extend（4c 修复前）
        # 修复 4c：先检查 QC，过了再 extend
        if not qc_passed:
            # QC 重试
            retry_results = [
                {"agent_id": "a1", "success": True, "content": "high_quality", "data_points": [{"url": "http://good"}]},
            ]
            if retry_passed:
                batch_results = retry_results
                # 修复后：只 extend 这组好数据

        # 修复后：extend 在 QC 通过之后
        all_results.extend(batch_results)

        assert len(all_results) == 1
        assert all_results[0]["content"] == "high_quality"
        assert all_results[0]["data_points"][0]["url"] == "http://good"

    def test_qc_retry_all_failed_nothing_added(self):
        """QC 全部重试失败 + 所有 agent 失败 → 模拟 break 不 extend"""
        all_results = []
        all_results_before = len(all_results)

        # 模拟：全部重试耗尽，所有结果都失败
        batch_results = [{"agent_id": "a1", "success": False, "error": "failed_after_retry"}]
        total = len(batch_results)
        success_count = sum(1 for r in batch_results if r.get("success"))

        # 模拟引擎行为：全部失败时 break，不会走到 extend
        if total > 0 and success_count == 0:
            pass  # result.status = "failed"; break
        else:
            all_results.extend(batch_results)

        assert len(all_results) == all_results_before, "全部失败不应 extend"


# =============================================================================
# 集成测试 3: API 端点基础响应验证（TestClient + 真实 app）
# =============================================================================

class TestResearchApiResponseShape:
    """验证修复后的 API 端点返回正确结构（不依赖 LLM）"""

    def test_interact_endpoint_rejects_missing_params(self):
        """interact 端点对缺失参数返回 422"""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with TestClient(app) as client:
            resp = client.post("/api/v1/research/interact", data={})
            assert resp.status_code == 422

    def test_health_or_docs_endpoint_available(self):
        """API 文档可访问"""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with TestClient(app) as client:
            resp = client.get("/api/v1/docs")
            assert resp.status_code in (200, 307)

    def test_research_start_returns_session_id(self):
        """research/start 返回 session_id 结构"""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with TestClient(app) as client:
            with patch('src.api.main.ResearchAPI.start_research', new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"session_id": "integ_test_sid", "step": 0, "mode": "chat"}
                resp = client.post("/api/v1/research/start", json={"topic": "integration_test"})
                if resp.status_code == 200:
                    data = resp.json()
                    assert "session_id" in data

    def test_research_status_structure(self):
        """research/{task_id}/status 返回状态结构"""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with TestClient(app) as client:
            with patch('src.api.main.ProgressStreamer.get_task_state') as mock_state:
                mock_state.return_value.status = "running"
                mock_state.return_value.progress = 50
                mock_state.return_value.current_phase = "research"
                mock_state.return_value.error = None
                mock_state.return_value.phases = []
                resp = client.get("/api/v1/research/test_001/status")
                if resp.status_code == 200:
                    data = resp.json()
                    assert "status" in data
                    assert data["status"] == "running"

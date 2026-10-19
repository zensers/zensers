"""
真实数据集成测试 — 使用 research_efbdc8ef (BYD财务分析) 的历史数据

验证：
1. 真实 section_details vs agent _section_id 的匹配链路
2. 真实 cancelled agent 的恢复链路
3. 真实 agent result 格式在聚合器中的处理
4. 真实 research_01150942 (成功研究) 的端到端聚合
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

DATA_DIR = Path(r"E:\market_report_systerm\data")


def _load_registry(task_id):
    path = DATA_DIR / "registries" / f"{task_id}.json"
    if not path.exists():
        pytest.skip(f"Registry not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_cache(task_id):
    path = DATA_DIR / f"research_{task_id}" / "research_result_cache.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 真实 BYD 数据：8 个章节全部为占位符
# ============================================================

class TestRealBYDData:
    """使用 research_efbdc8ef 真实数据验证匹配链路"""

    REAL_SECTION_DETAILS = [
        {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
        {"id": "盈利能力分析", "name": "盈利能力分析", "content": "盈利能力分析"},
        {"id": "偿债能力与资本结构分析", "name": "偿债能力与资本结构分析", "content": "偿债能力与资本结构分析"},
        {"id": "运营效率分析", "name": "运营效率分析", "content": "运营效率分析"},
        {"id": "现金流分析", "name": "现金流分析", "content": "现金流分析"},
        {"id": "成长性分析", "name": "成长性分析", "content": "成长性分析"},
        {"id": "风险分析", "name": "风险分析", "content": "风险分析"},
        {"id": "估值与投资价值分析", "name": "估值与投资价值分析", "content": "估值与投资价值分析"},
    ]

    REAL_AGENT_SECTION_IDS = [
        "section_0_营收构成分析",
        "section_1_盈利能力分析",
        "section_2_偿债能力与资本结构分析",
        "section_3_运营效率分析",
        "section_4_现金流分析",
        "section_5_成长性分析",
        "section_6_风险分析",
        "section_7_估值与投资价值分析",
    ]

    def test_normalize_matches_all_real_section_ids(self):
        """验证 _normalize_key 能消除所有真实 section_id 前缀"""
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        for section_detail, agent_section_id in zip(
            self.REAL_SECTION_DETAILS, self.REAL_AGENT_SECTION_IDS
        ):
            norm_detail = _normalize_key(section_detail["id"])
            norm_agent = _normalize_key(agent_section_id)
            assert norm_detail == norm_agent, (
                f"归一化不匹配: detail='{section_detail['id']}' -> '{norm_detail}' "
                f"vs agent='{agent_section_id}' -> '{norm_agent}'"
            )

    def test_aggregator_with_real_byd_format_no_content(self):
        """真实 BYD 场景：phase_1 agent 只有 quality_stats，无 content/data_points"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {}
        for i, section_id in enumerate(self.REAL_AGENT_SECTION_IDS):
            agent_id = f"phase_1_agent_{i}"
            agent_results[agent_id] = {
                "success": True,
                "total_sources": 70,
                "quality_stats": {"query": {"filtered_count": 5}},
                "agent_id": agent_id,
                "section_id": section_id,
                "_section_id": section_id,
                "action": "execute",
                "category": "research",
            }

        aggregator = ResultAggregator()
        result = aggregator.aggregate(
            agent_results, section_details=self.REAL_SECTION_DETAILS
        )
        result_dict = result.to_dict() if hasattr(result, "to_dict") else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) == 8, f"应有 8 个章节，实际 {len(sections)}"

        empty = []
        for s in sections:
            content = s.get("content", "") or ""
            if len(content.strip()) < 20 or "数据不足" in content:
                empty.append(s.get("title", s.get("id", "")))

        assert len(empty) == 8, (
            f"无 content 的 agent 结果应全部生成占位符，实际 {len(empty)}/8 为空"
        )

    def test_aggregator_with_real_byd_format_with_content(self):
        """真实 BYD 场景：phase_1 agent 有 content（模拟修复后的 partial output）"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        real_contents = {
            "section_0_营收构成分析": "比亚迪2024年实现营业收入7771亿元，同比增长21.04%。汽车业务占比80%，手机部件及组装占比15%。",
            "section_1_盈利能力分析": "2024年归母净利润402.54亿元，毛利率18.81%，净利率5.19%。",
            "section_2_偿债能力与资本结构分析": "资产负债率70.94%，流动比率0.98，速动比率0.72，偿债压力较大。",
            "section_3_运营效率分析": "存货周转天数58天，应收账款周转天数42天，总资产周转率0.73次。",
            "section_4_现金流分析": "经营活动现金流净额1869.94亿元，投资活动现金流净额-1520亿元。",
            "section_5_成长性分析": "营收CAGR 3年32%，净利润CAGR 3年28%，研发投入增速35%。",
            "section_6_风险分析": "主要风险：新能源补贴退坡、原材料价格波动、海外贸易壁垒。",
            "section_7_估值与投资价值分析": "PE 22倍，PB 5.2倍，DCF估值区间280-350元/股。",
        }

        agent_results = {}
        for i, section_id in enumerate(self.REAL_AGENT_SECTION_IDS):
            agent_id = f"phase_1_agent_{i}"
            agent_results[agent_id] = {
                "success": True,
                "content": real_contents.get(section_id, ""),
                "agent_id": agent_id,
                "section_id": section_id,
                "_section_id": section_id,
            }

        aggregator = ResultAggregator()
        result = aggregator.aggregate(
            agent_results, section_details=self.REAL_SECTION_DETAILS
        )
        result_dict = result.to_dict() if hasattr(result, "to_dict") else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) == 8, f"应有 8 个章节，实际 {len(sections)}"

        empty = []
        for s in sections:
            content = s.get("content", "") or ""
            if len(content.strip()) < 20 or "数据不足" in content:
                empty.append(s.get("title", s.get("id", "")))

        assert len(empty) == 0, f"以下章节内容为空: {empty}"

    def test_session_recovery_with_real_byd_data(self):
        """使用真实 registry 数据验证 session recovery"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.agents.agent_session import (
            AgentSession, AgentSessionStatus, AgentSessionRegistry,
        )

        registry_data = _load_registry("research_efbdc8ef")
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)

        registry = AgentSessionRegistry(parent_session_id="research_efbdc8ef")
        recovered_count = 0
        for sid, session_data in registry_data["child_sessions"].items():
            status_str = session_data.get("status", "")
            if status_str not in ("cancelled", "failed"):
                continue
            result_data = session_data.get("result")
            if not result_data:
                continue
            status_map = {
                "cancelled": AgentSessionStatus.CANCELLED,
                "failed": AgentSessionStatus.FAILED,
            }
            session = AgentSession(
                session_id=sid,
                agent_id=session_data.get("agent_id", ""),
                status=status_map.get(status_str, AgentSessionStatus.CANCELLED),
                result=result_data,
                context=session_data.get("context", {}),
            )
            registry.register(session)
            recovered_count += 1

        recovered = orch._recover_results_from_sessions("research_efbdc8ef", registry)

        assert len(recovered) == recovered_count, (
            f"应恢复 {recovered_count} 个结果，实际 {len(recovered)}"
        )

        for r in recovered:
            assert r["_recovered"] is True
            assert "agent_id" in r

        has_section_id = [r for r in recovered if "_section_id" in r]
        assert len(has_section_id) == recovered_count, (
            f"所有恢复结果应有 _section_id，实际 {len(has_section_id)}/{recovered_count}"
        )

    def test_cancelled_agent_result_has_no_content(self):
        """验证真实 cancelled agent 的 result 确实没有 content 字段"""
        registry_data = _load_registry("research_efbdc8ef")

        cancelled_with_content = 0
        cancelled_without_content = 0
        for sid, session_data in registry_data["child_sessions"].items():
            if session_data.get("status") != "cancelled":
                continue
            result = session_data.get("result") or {}
            has_content = bool(result.get("content"))
            has_data_points = bool(result.get("data_points"))
            if has_content or has_data_points:
                cancelled_with_content += 1
            else:
                cancelled_without_content += 1

        assert cancelled_without_content > 0, "真实数据中应有 cancelled agent 无 content"
        assert cancelled_with_content == 0, (
            f"真实 BYD 数据中 cancelled agent 不应有 content，但发现 {cancelled_with_content} 个有 content"
        )


# ============================================================
# 真实成功研究数据验证
# ============================================================

class TestRealSuccessfulResearch:
    """使用 research_01150942 真实成功数据验证端到端聚合"""

    def test_successful_research_aggregation(self):
        """真实成功研究的聚合结果应无空章节"""
        registry_data = _load_registry("research_01150942")

        agent_results = {}
        section_ids_seen = set()
        for sid, session_data in registry_data["child_sessions"].items():
            if session_data.get("status") != "completed":
                continue
            result = session_data.get("result") or {}
            if not result:
                continue
            agent_id = session_data.get("agent_id", "")
            if not agent_id:
                continue

            entry = dict(result)
            entry["agent_id"] = agent_id
            ctx = session_data.get("context") or {}
            if "section_id" in ctx:
                entry["_section_id"] = ctx["section_id"]
                section_ids_seen.add(ctx["section_id"])

            agent_results[agent_id] = entry

        if not agent_results:
            pytest.skip("No completed agents with results")

        section_details = []
        for section_id in sorted(section_ids_seen):
            from src.core.orchestrator.aggregation.result_aggregator import _normalize_key
            name = _normalize_key(section_id)
            section_details.append({"id": name, "name": name, "content": name})

        if not section_details:
            pytest.skip("No section_ids found")

        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) > 0, "应有聚合结果"

        empty = []
        for s in sections:
            content = s.get("content", "") or ""
            if len(content.strip()) < 20:
                empty.append(s.get("title", s.get("id", "")))

        assert len(empty) == 0, f"以下章节内容为空: {empty}"


# ============================================================
# 真实数据格式验证：agent result 结构
# ============================================================

class TestRealDataFormat:
    """验证真实 agent result 格式在聚合器中的正确处理"""

    def test_phase1_result_format_no_content_field(self):
        """Phase 1 agent result 只有 quality_stats，无 content/data_points"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {
            "phase_1_agent_0": {
                "success": True,
                "total_sources": 70,
                "quality_stats": {"q1": {"filtered_count": 5}},
                "agent_id": "phase_1_agent_0",
                "result": {"total_sources": 70, "quality_stats": {}},
                "action": "execute",
                "category": "research",
                "agent_type": "dynamic",
                "section_id": "section_0_营收构成分析",
                "_section_id": "section_0_营收构成分析",
            },
        }

        section_details = [
            {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) >= 1

    def test_phase2_result_format_with_content(self):
        """Phase 2 agent result 有 content 字段"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {
            "phase_2_agent_0": {
                "success": True,
                "content": "比亚迪2024年营收7771亿元，同比增长21.04%。",
                "agent_id": "phase_2_agent_0",
                "section_id": "section_0_营收构成分析",
                "_section_id": "section_0_营收构成分析",
            },
        }

        section_details = [
            {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) >= 1
        content = sections[0].get("content", "") or ""
        assert "7771" in content or "营收" in content, f"应包含真实数据: {content[:100]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

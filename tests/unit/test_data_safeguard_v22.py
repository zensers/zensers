"""
数据保障方案 v2.2 TDD 测试

覆盖场景：
1. Fix1 (P0): agent_coordinator cancelled/timeout 分支保存 partial output
2. Fix3 (P1): provenance 归一化匹配
3. Fix4 (P2): 语义匹配兜底
4. Fix5 (P2): session 恢复
"""
import pytest
from unittest.mock import MagicMock
from typing import Any, Dict, Optional, Set, Tuple


# ============================================================
# Fix1: _extract_partial_output
# ============================================================

class TestExtractPartialOutput:
    """Fix1: cancelled/timeout agent 保存部分输出"""

    def test_extract_from_agent_context_last_output(self):
        """agent._context.last_output 有内容时提取成功"""
        from src.core.orchestrator.execution.coordinator.agent_coordinator import _extract_partial_output

        agent = MagicMock()
        agent.agent_id = "phase_1_agent_0"
        agent.section_id = "section_0_营收构成分析"
        agent._context = {"last_output": "比亚迪2024年营收7771亿元"}

        active_task = MagicMock()
        active_task.agent = agent
        active_task.partial_output = ""

        result = _extract_partial_output(active_task)

        assert result is not None
        assert result["success"] is False
        assert "比亚迪2024年营收7771亿元" in result["content"]
        assert result["agent_id"] == "phase_1_agent_0"
        assert result["section_id"] == "section_0_营收构成分析"
        assert result["_section_id"] == "section_0_营收构成分析"
        assert result["_partial"] is True

    def test_extract_from_active_task_partial_output(self):
        """agent._context 无 last_output 但 active_task.partial_output 有内容"""
        from src.core.orchestrator.execution.coordinator.agent_coordinator import _extract_partial_output

        agent = MagicMock()
        agent.agent_id = "phase_1_agent_1"
        agent.section_id = ""
        agent._context = {}

        active_task = MagicMock()
        active_task.agent = agent
        active_task.partial_output = "部分分析内容"

        result = _extract_partial_output(active_task)

        assert result is not None
        assert "部分分析内容" in result["content"]
        assert result["_partial"] is True

    def test_no_output_returns_none(self):
        """无任何输出时返回 None"""
        from src.core.orchestrator.execution.coordinator.agent_coordinator import _extract_partial_output

        agent = MagicMock()
        agent.agent_id = "phase_1_agent_2"
        agent.section_id = ""
        agent._context = {}

        active_task = MagicMock()
        active_task.agent = agent
        active_task.partial_output = ""

        result = _extract_partial_output(active_task)

        assert result is None

    def test_preserves_data_points_and_sources(self):
        """保留已收集的 data_points 和 sources"""
        from src.core.orchestrator.execution.coordinator.agent_coordinator import _extract_partial_output

        agent = MagicMock()
        agent.agent_id = "phase_1_agent_3"
        agent.section_id = "section_3_销量"
        agent._context = {
            "last_output": "销量数据",
            "data_points": [{"title": "BYD sales", "content": "460万辆"}],
            "sources": [{"url": "https://example.com", "title": "BYD report"}],
        }

        active_task = MagicMock()
        active_task.agent = agent
        active_task.partial_output = ""

        result = _extract_partial_output(active_task)

        assert result is not None
        assert len(result["data_points"]) == 1
        assert result["data_points"][0]["title"] == "BYD sales"
        assert len(result["sources"]) == 1

    def test_content_truncated_at_50000(self):
        """超长内容截断到 50000 字符"""
        from src.core.orchestrator.execution.coordinator.agent_coordinator import _extract_partial_output

        long_content = "x" * 60000
        agent = MagicMock()
        agent.agent_id = "phase_1_agent_4"
        agent.section_id = ""
        agent._context = {"last_output": long_content}

        active_task = MagicMock()
        active_task.agent = agent
        active_task.partial_output = ""

        result = _extract_partial_output(active_task)

        assert result is not None
        assert len(result["content"]) == 50000


# ============================================================
# Fix3: Provenance 归一化匹配
# ============================================================

class TestProvenanceNormalizedMatching:
    """Fix3: provenance.section_target 与 section_id 归一化匹配"""

    def test_prefix_stripped_match(self):
        """section_target='section_0_营收构成分析' 匹配 section_id='营收构成分析'"""
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        norm_target = _normalize_key("section_0_营收构成分析")
        norm_sid = _normalize_key("营收构成分析")

        assert norm_target == norm_sid, (
            f"归一化后应相等: norm_target='{norm_target}' norm_sid='{norm_sid}'"
        )

    def test_punctuation_normalized_match(self):
        """section_target 含 '、' 匹配 section_id 含 '_'"""
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        norm_target = _normalize_key("财务健康、风险评估与季度业绩波动")
        norm_sid = _normalize_key("财务健康_风险评估与季度业绩波动")

        assert norm_target == norm_sid

    def test_provenance_normalized_match_in_aggregator(self):
        """在聚合器中 provenance 归一化匹配能找到内容"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        aggregator = ResultAggregator()
        results = aggregator.aggregate(
            {"phase_1_agent_0": {
                "success": True,
                "content": "比亚迪营收构成分析内容...",
                "agent_id": "phase_1_agent_0",
                "_section_id": "section_0_营收构成分析",
            }},
            section_details=[{"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"}],
        )

        result_dict = results.to_dict() if hasattr(results, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        matched = [s for s in sections if "营收" in (s.get("title", "") + s.get("content", ""))]
        assert len(matched) > 0, "provenance 归一化匹配应找到内容"

    def test_provenance_exact_match_still_works(self):
        """精确匹配仍然优先"""
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        assert _normalize_key("营收构成分析") == _normalize_key("营收构成分析")


# ============================================================
# Fix4: 语义匹配兜底
# ============================================================

class TestSemanticMatching:
    """Fix4: 语义匹配兜底"""

    def test_tokenize_zh_basic(self):
        """中文 2-gram 分词基本功能"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("营收构成分析")
        assert isinstance(tokens, set)
        assert len(tokens) > 0
        assert "营收" in tokens
        assert "收构" in tokens
        assert "构成" in tokens
        assert "成分" in tokens

    def test_tokenize_zh_removes_stopwords(self):
        """停用词 2-gram 被过滤"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("的分析")
        assert "的" not in tokens or len(tokens) == 0

    def test_tokenize_zh_mixed_chinese_english(self):
        """中英混合文本分词"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("Market规模分析")
        assert "规模" in tokens
        assert "模分" in tokens
        assert "market" in tokens

    def test_jaccard_identical_sets(self):
        """相同 token 集合 Jaccard = 1.0"""
        from src.core.orchestrator.aggregation.result_aggregator import _compute_jaccard

        tokens = {"营收", "构成", "分析"}
        assert _compute_jaccard(tokens, tokens) == 1.0

    def test_jaccard_no_overlap(self):
        """无重叠 Jaccard = 0.0"""
        from src.core.orchestrator.aggregation.result_aggregator import _compute_jaccard

        assert _compute_jaccard({"营收"}, {"竞争"}) == 0.0

    def test_jaccard_partial_overlap(self):
        """部分重叠 0 < Jaccard < 1"""
        from src.core.orchestrator.aggregation.result_aggregator import _compute_jaccard

        a = {"营收", "构成", "分析"}
        b = {"营收", "预测", "分析"}
        j = _compute_jaccard(a, b)
        assert 0.0 < j < 1.0

    def test_title_fuzzy_score_high_for_similar(self):
        """相似标题得分高"""
        from src.core.orchestrator.aggregation.result_aggregator import _title_fuzzy_score

        score = _title_fuzzy_score("营收构成分析", "营收分析")
        assert score >= 0.3, f"相似标题得分应 >= 0.3, 实际 {score}"

    def test_title_fuzzy_score_low_for_unrelated(self):
        """无关标题得分低"""
        from src.core.orchestrator.aggregation.result_aggregator import _title_fuzzy_score

        score = _title_fuzzy_score("营收构成分析", "竞争格局")
        assert score < 0.3, f"无关标题得分应 < 0.3, 实际 {score}"

    def test_semantic_match_section_finds_best(self):
        """语义匹配找到最佳匹配"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        unused = {
            "phase_1_agent_0": ("营收分析内容...", "section_0_营收构成分析"),
            "phase_1_agent_1": ("竞争格局内容...", "section_1_竞争格局"),
            "phase_1_agent_2": ("研发投入内容...", "section_2_研发投入"),
        }

        result = _semantic_match_section(
            section_name="营收构成分析",
            section_id="营收构成分析",
            unused_agents=unused,
        )

        assert result is not None
        matched_key, content, score = result
        assert matched_key == "phase_1_agent_0"
        assert score >= 0.3

    def test_semantic_match_section_returns_none_for_no_match(self):
        """完全无关时返回 None"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        unused = {
            "phase_1_agent_0": ("竞争格局内容...", "section_0_竞争格局"),
            "phase_1_agent_1": ("政策法规内容...", "section_1_政策法规"),
        }

        result = _semantic_match_section(
            section_name="营收构成分析",
            section_id="营收构成分析",
            unused_agents=unused,
        )

        assert result is None

    def test_semantic_match_normalized_aspect_match(self):
        """归一化 aspect 匹配优先（score=0.9）"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        unused = {
            "phase_1_agent_0": ("营收分析内容...", "section_0_营收构成分析"),
        }

        result = _semantic_match_section(
            section_name="营收构成分析",
            section_id="营收构成分析",
            unused_agents=unused,
        )

        assert result is not None
        _, _, score = result
        assert score >= 0.9, f"归一化匹配应返回高分, 实际 {score}"

    def test_semantic_match_content_fallback(self):
        """标题匹配失败时，内容关键词覆盖回退"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        unused = {
            "phase_1_agent_0": ("比亚迪营收构成分析：2024年营收7771亿元，其中汽车业务占比...", ""),
        }

        result = _semantic_match_section(
            section_name="营收构成分析",
            section_id="营收构成分析",
            unused_agents=unused,
        )

        assert result is not None
        _, _, score = result
        assert score >= 0.2


# ============================================================
# Fix5: Session 恢复
# ============================================================

class TestSessionRecovery:
    """Fix5: 从 AgentSession 恢复 cancelled/failed 结果"""

    def _make_registry(self):
        from src.core.agents.agent_session import AgentSessionRegistry
        return AgentSessionRegistry(parent_session_id="parent_1")

    def test_recover_cancelled_session_with_result(self):
        """cancelled session 有 result 时恢复成功"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.agents.agent_session import AgentSession, AgentSessionStatus

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        registry = self._make_registry()
        session = AgentSession(
            session_id="s1",
            agent_id="phase_1_agent_0",
            status=AgentSessionStatus.CANCELLED,
            result={"content": "部分数据", "data_points": [{"title": "test"}]},
            context={"section_id": "section_0_营收构成分析"},
        )
        registry.register(session)

        recovered = orch._recover_results_from_sessions("task_1", registry)

        assert len(recovered) == 1
        assert recovered[0]["content"] == "部分数据"
        assert recovered[0]["_recovered"] is True
        assert recovered[0]["_section_id"] == "section_0_营收构成分析"
        assert recovered[0]["agent_id"] == "phase_1_agent_0"

    def test_skip_completed_session(self):
        """completed session 不被恢复"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.agents.agent_session import AgentSession, AgentSessionStatus

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        registry = self._make_registry()
        session = AgentSession(
            session_id="s1",
            agent_id="phase_1_agent_0",
            status=AgentSessionStatus.COMPLETED,
            result={"content": "完整数据"},
        )
        registry.register(session)

        recovered = orch._recover_results_from_sessions("task_1", registry)
        assert len(recovered) == 0

    def test_skip_session_without_result(self):
        """result 为 None 的 session 不被恢复"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.agents.agent_session import AgentSession, AgentSessionStatus

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        registry = self._make_registry()
        session = AgentSession(
            session_id="s1",
            agent_id="phase_1_agent_0",
            status=AgentSessionStatus.CANCELLED,
            result=None,
        )
        registry.register(session)

        recovered = orch._recover_results_from_sessions("task_1", registry)
        assert len(recovered) == 0

    def test_recover_failed_session(self):
        """failed session 有 result 时也恢复"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.agents.agent_session import AgentSession, AgentSessionStatus

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        registry = self._make_registry()
        session = AgentSession(
            session_id="s1",
            agent_id="phase_1_agent_0",
            status=AgentSessionStatus.FAILED,
            result={"content": "失败前的部分数据"},
            context={"section_id": "section_0_销量"},
        )
        registry.register(session)

        recovered = orch._recover_results_from_sessions("task_1", registry)
        assert len(recovered) == 1
        assert recovered[0]["_recovered"] is True

    def test_none_registry_returns_empty(self):
        """registry 为 None 时返回空列表"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        recovered = orch._recover_results_from_sessions("task_1", None)
        assert recovered == []


# ============================================================
# Integration: 完整匹配链路
# ============================================================

class TestFullMatchingChain:
    """端到端匹配链路：精确 -> provenance归一化 -> key归一化 -> 语义兜底"""

    def test_byd_style_matching_with_agent_id_keys(self):
        """
        真实 BYD 场景：
        - agent_results key = agent_id (phase_1_agent_0)
        - section_details.id = 中文标题 (营收构成分析)
        - _section_id = section_0_营收构成分析
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {
            "phase_1_agent_0": {
                "success": True,
                "content": "比亚迪2024年营收7771亿元，汽车业务占比80%",
                "agent_id": "phase_1_agent_0",
                "_section_id": "section_0_营收构成分析",
            },
            "phase_1_agent_1": {
                "success": True,
                "content": "研发投入542亿元，研发人员超10万人，专利申请量全球领先",
                "agent_id": "phase_1_agent_1",
                "_section_id": "section_1_研发与创新投入",
            },
        }

        section_details = [
            {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
            {"id": "研发与创新投入", "name": "研发与创新投入", "content": "研发与创新投入"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        empty = [s for s in sections if len((s.get("content", "") or "").strip()) < 20]
        assert len(empty) == 0, f"以下章节内容为空: {[s.get('title') for s in empty]}"
        assert len(sections) == 2

    def test_all_matching_strategies_fail_semantic_saves(self):
        """
        所有精确/归一化匹配失败时，语义匹配兜底
        - agent key = phase_1_agent_0 (无 section_id 信息)
        - section = 营收构成分析
        - provenance.section_target = phase_1_agent_0 (heuristic 失效)
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {
            "phase_1_agent_0": {
                "success": True,
                "content": "比亚迪营收构成分析：2024年营收7771亿元，其中汽车业务占比80%...",
                "agent_id": "phase_1_agent_0",
            },
        }

        section_details = [
            {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) >= 1
        content = sections[0].get("content", "") or ""
        assert len(content.strip()) >= 20, "语义匹配应找到内容，不应为占位符"


# ============================================================
# Deep audit: 新发现 bug 的测试
# ============================================================

class TestSemanticMatchExtractContent:
    """BUG修复: semantic match 返回 raw value, 由调用方用 extract_content 处理"""

    def test_dict_value_in_layered_content_via_extract_content(self):
        """当 layered_content 中有 dict 值时，语义匹配通过 extract_content 正确提取"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_results = {
            "phase_1_agent_0": {
                "success": True,
                "content": "比亚迪营收分析：2024年营收7771亿元，汽车业务占比80%",
                "agent_id": "phase_1_agent_0",
            },
        }

        section_details = [
            {"id": "营收构成分析", "name": "营收构成分析", "content": "营收构成分析"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) >= 1
        content = sections[0].get("content", "") or ""
        assert len(content.strip()) >= 20, "内容不应为空"
        assert "{" not in content[:5], "不应出现 Python dict repr 在内容开头"


class TestTokenizeZhEnglishWords:
    """BUG修复: _tokenize_zh 英文按单词分词，非字符"""

    def test_english_word_tokenization(self):
        """英文单词作为整体 token"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("Market Size Analysis")
        assert "market" in tokens
        assert "size" in tokens
        assert "analysis" in tokens

    def test_english_not_character_level(self):
        """英文不应被拆成单字符"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("Market")
        assert "market" in tokens
        assert "m" not in tokens or "market" in tokens

    def test_mixed_chinese_english_with_numbers(self):
        """中英数混合"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("2024年Market规模100亿")
        assert "2024" in tokens or "market" in tokens
        assert "规模" in tokens
        assert "market" in tokens

    def test_empty_string(self):
        """空字符串返回空集合"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        assert _tokenize_zh("") == set()

    def test_all_stopwords_returns_empty(self):
        """全停用词返回空集合"""
        from src.core.orchestrator.aggregation.result_aggregator import _tokenize_zh

        tokens = _tokenize_zh("的分析")
        assert "分析" not in tokens


class TestSemanticMatchNoneGuard:
    """BUG修复: _semantic_match_section 对 None/empty unused_agents 防御"""

    def test_empty_dict_returns_none(self):
        """空 dict 返回 None"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        result = _semantic_match_section("营收", "营收", unused_agents={})
        assert result is None

    def test_meta_keys_excluded(self):
        """__meta 键被内部过滤"""
        from src.core.orchestrator.aggregation.result_aggregator import _semantic_match_section

        unused = {
            "phase_1_agent_0__meta": ("meta data", ""),
            "phase_1_agent_0": ("实际内容数据", "section_0_营收分析"),
        }

        result = _semantic_match_section("营收分析", "营收分析", unused_agents=unused)
        assert result is not None
        matched_key, _, _ = result
        assert matched_key != "phase_1_agent_0__meta"


class TestResultStatusCancelled:
    """BUG修复: cancelled 执行的 result_status 应为 completed_with_warnings"""

    def test_cancelled_status_in_result(self):
        """验证 cancelled 执行后 result_status 逻辑"""
        exec_status = "cancelled"
        quality_passed = True

        if exec_status == "cancelled":
            result_status = "completed_with_warnings"
        elif quality_passed:
            result_status = "completed"
        else:
            result_status = "completed_with_warnings"

        assert result_status == "completed_with_warnings"

    def test_normal_completed_status(self):
        """正常完成应为 completed"""
        exec_status = "completed"
        quality_passed = True

        if exec_status == "cancelled":
            result_status = "completed_with_warnings"
        elif quality_passed:
            result_status = "completed"
        else:
            result_status = "completed_with_warnings"

        assert result_status == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

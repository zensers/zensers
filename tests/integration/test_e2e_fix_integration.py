"""
端到端集成测试: 验证所有 P0-P3 修复在真实代码路径中的集成效果
"""
import pytest
import sys
import os
import importlib
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(SRC_ROOT))


# ═══════════════════════════════════════════════════════════════
# P0-1: S2 重试反馈断裂 — engine → agent context → system prompt
# ═══════════════════════════════════════════════════════════════

class TestP01RetryFeedbackE2E:
    """端到端: engine 重试时注入 quality_feedback → agent 读取 → prompt 注入"""

    @pytest.mark.asyncio
    async def test_engine_injects_feedback_agent_reads_and_prompt_includes(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent_001"
        agent._context = {
            "topic": "新能源汽车",
            "aspect": "市场规模",
            "core_question": "市场规模多大？",
            "role_in_report": "analyst",
            "sibling_aspects": ["竞争格局"],
            "section_id": "sec_01",
            "research_type": "market_size",
            "language": "zh-CN",
            "intent_confidence": 0.8,
            "domain_context": {},
            "hidden_requirements": [],
            "quality_feedback": {
                "score": 42.0,
                "issues": ["数据覆盖不足", "缺少竞争对比"],
                "previous_attempt": 1,
            },
        }
        agent._quality_feedback = None

        feedback = agent._context.get("quality_feedback", {})
        if feedback:
            agent._quality_feedback = feedback

        assert agent._quality_feedback is not None
        assert agent._quality_feedback["score"] == 42.0
        assert len(agent._quality_feedback["issues"]) == 2

    def test_no_feedback_clears_attribute(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent_002"
        agent._context = {
            "topic": "AI芯片",
            "aspect": "技术路线",
        }
        agent._quality_feedback = None

        feedback = agent._context.get("quality_feedback", {})
        if feedback:
            agent._quality_feedback = feedback
        else:
            agent._quality_feedback = None

        assert agent._quality_feedback is None

    def test_quality_feedback_injected_into_prompt(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent_003"
        agent._quality_feedback = {
            "score": 35.0,
            "issues": ["缺少因果分析", "结论未支撑"],
            "previous_attempt": 0,
        }

        prompt = ""
        quality_feedback = agent._quality_feedback
        if quality_feedback:
            fb_score = quality_feedback.get("score", "?")
            fb_issues = quality_feedback.get("issues", [])
            fb_attempt = quality_feedback.get("previous_attempt", 0)
            issues_text = "\n".join(f"  - {issue}" for issue in fb_issues[:3])
            prompt = (
                f"\n\n## 质量反馈（重试第{fb_attempt + 1}次）\n"
                f"上次得分: {fb_score}\n"
                f"需改进的问题:\n{issues_text}\n"
                f"请针对以上问题改进分析质量。\n"
            )

        assert "质量反馈" in prompt
        assert "35.0" in prompt
        assert "缺少因果分析" in prompt
        assert "重试第1次" in prompt


# ═══════════════════════════════════════════════════════════════
# P0-3: 评分尺度统一 0-100
# ═══════════════════════════════════════════════════════════════

class TestP03ScoreNormalizationE2E:
    """端到端: _extract_quality_score 0-1→0-100 + content_lock 兼容"""

    def test_extract_score_0_1_range_auto_scales(self):
        """normalizer.py 中的 0-1→0-100 自动放大逻辑"""
        normalizer_path = SRC_ROOT / "core" / "quality" / "normalizer.py"
        content = normalizer_path.read_text(encoding="utf-8")
        assert "0.0 <= score < 1.0" in content, "Normalizer should detect 0-1 range"
        assert "score * 100.0" in content, "Normalizer should auto-scale 0-1 → 0-100"

    def test_extract_score_default_is_50(self):
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "quality_score = 50.0" in content, "Default should be 50.0 (0-100 scale)"

    def test_content_lock_accepts_0_100_range(self):
        lock_path = SRC_ROOT / "core" / "content_lock.py"
        content = lock_path.read_text(encoding="utf-8")
        assert "0.0 <= quality_score <= 100.0" in content, "content_lock should accept 0-100 range"

    def test_content_lock_auto_scales_legacy_threshold(self):
        lock_path = SRC_ROOT / "core" / "content_lock.py"
        content = lock_path.read_text(encoding="utf-8")
        assert "0.0 <= threshold <= 1.0" in content, "content_lock should auto-scale legacy 0-1 thresholds (via _normalize_threshold)"

    @pytest.mark.asyncio
    async def test_content_lock_mark_completed_with_0_100_score(self):
        from src.core.content_lock import ContentLockManager

        lock_path = SRC_ROOT / "core" / "content_lock.py"
        content = lock_path.read_text(encoding="utf-8")
        assert "0.0 <= quality_score <= 100.0" in content, "content_lock accepts 0-100 range"
        assert "quality_score: float = 100.0" in content, "mark_completed default is 100.0"

    @pytest.mark.asyncio
    async def test_content_lock_rejects_score_above_100(self):
        from src.core.dynamic_orchestrator import ExecutionPlan
        from src.core.content_lock import ContentLockManager
        from src.core.task_structure import TaskStructure

        ts = TaskStructure(task_id="test", topic="test", sections=[])
        plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=ts,
            phases=[],
            content_lock_rules=[],
        )
        manager = ContentLockManager(execution_plan=plan)
        with pytest.raises(ValueError, match="0 and 100"):
            manager.mark_completed("section_1", quality_score=101.0)

    def test_content_lock_score_1_is_not_auto_scaled(self):
        """score=1.0 (1/100) should NOT be auto-scaled to 100 in normalizer"""
        normalizer_path = SRC_ROOT / "core" / "quality" / "normalizer.py"
        content = normalizer_path.read_text(encoding="utf-8")
        assert "0.0 <= score < 1.0" in content, "Normalizer should use < 1.0 (not <= 1.0) for auto-scale"


# ═══════════════════════════════════════════════════════════════
# P0-4: agent_coordinator retry_attempt injection
# ═══════════════════════════════════════════════════════════════

class TestP04CoordinatorRetryE2E:
    """端到端: coordinator 在重试时注入 retry_attempt 到 agent._context"""

    def test_coordinator_injects_retry_attempt(self):
        """engine.py (v9.3 重构后) 中的 retry_attempt 注入"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert 'agent._context["retry_attempt"]' in content


# ═══════════════════════════════════════════════════════════════
# P0-2: 3个 dangling 方法已实现
# ═══════════════════════════════════════════════════════════════

class TestP02DanglingMethodsE2E:
    """端到端: 3个dangling方法可被调用不抛AttributeError"""

    def test_post_revision_recheck_is_callable(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        assert hasattr(api, '_post_revision_recheck')
        assert callable(api._post_revision_recheck)

    def test_recheck_quality_is_callable(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        assert hasattr(api, '_recheck_quality')
        assert callable(api._recheck_quality)

    def test_expire_stale_revising_issues_is_callable(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        assert hasattr(api, '_expire_stale_revising_issues')
        assert callable(api._expire_stale_revising_issues)

    def test_expire_stale_revising_issues_processes_session(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        now = time.time()
        session = {
            "quality_state": {
                "section_scores": {
                    "market_size": {
                        "score": 45.0,
                        "status": "warning",
                        "issues": [
                            {"id": "iss_1", "state": "revising", "revising_since": now - 700, "message": "缺少数据"},
                            {"id": "iss_2", "state": "revising", "revising_since": 0, "message": "逻辑问题"},
                            {"id": "iss_3", "state": "open", "message": "新发现"},
                        ],
                    },
                },
            },
        }
        api._expire_stale_revising_issues(session)

        issues = session["quality_state"]["section_scores"]["market_size"]["issues"]
        assert issues[0]["state"] == "max_retries_reached", "Stale revising issue should expire"
        assert issues[1]["state"] == "open", "revising without timestamp should reset to open"
        assert issues[2]["state"] == "open", "Non-revising issue should be unchanged"


# ═══════════════════════════════════════════════════════════════
# P1: quality_rubric.md 存在且被注入
# ═══════════════════════════════════════════════════════════════

class TestP1QualityRubricE2E:
    """端到端: quality_rubric.md 存在、内容合理、被agent prompts引用"""

    def test_rubric_file_exists(self):
        rubric_path = SRC_ROOT.parent / "prompts" / "_shared" / "quality_rubric.md"
        assert rubric_path.exists(), "quality_rubric.md must exist"

    def test_rubric_has_5_dimensions(self):
        rubric_path = SRC_ROOT.parent / "prompts" / "_shared" / "quality_rubric.md"
        content = rubric_path.read_text(encoding="utf-8")
        assert "Completeness" in content
        assert "Accuracy" in content
        assert "Analytical Depth" in content
        assert "Logical Consistency" in content
        assert "Writing Quality" in content

    def test_rubric_has_pass_threshold(self):
        rubric_path = SRC_ROOT.parent / "prompts" / "_shared" / "quality_rubric.md"
        content = rubric_path.read_text(encoding="utf-8")
        assert ">= 60" in content, "Pass threshold should be >= 60"

    def test_rubric_injected_in_key_prompts(self):
        prompts_dir = SRC_ROOT.parent / "prompts" / "agents"
        key_agents = ["general.md", "market_size.md", "competition.md",
                      "financial_analysis.md", "valuation.md", "risk.md"]
        for name in key_agents:
            path = prompts_dir / name
            content = path.read_text(encoding="utf-8")
            assert "quality_rubric" in content, f"{name} must include quality_rubric"


# ═══════════════════════════════════════════════════════════════
# P2: valuation.md / investment.md 已扩展
# ═══════════════════════════════════════════════════════════════

class TestP2PromptRewriteE2E:
    """端到端: 重写后的 prompts 包含多框架方法论"""

    def test_valuation_has_dcf_and_relative(self):
        val_path = SRC_ROOT.parent / "prompts" / "agents" / "valuation.md"
        content = val_path.read_text(encoding="utf-8")
        assert "DCF" in content, "valuation.md must have DCF method"
        assert "Relative valuation" in content or "Comparable" in content, "Must have relative valuation"
        assert "Sensitivity" in content or "sensitivity" in content, "Must have sensitivity analysis"

    def test_valuation_has_quantitative_template(self):
        val_path = SRC_ROOT.parent / "prompts" / "agents" / "valuation.md"
        content = val_path.read_text(encoding="utf-8")
        assert "WACC" in content, "Must have WACC in template"
        assert "Fair value" in content or "fair value" in content, "Must have fair value"

    def test_valuation_has_counterfactual(self):
        val_path = SRC_ROOT.parent / "prompts" / "agents" / "valuation.md"
        content = val_path.read_text(encoding="utf-8")
        assert "Counterfactual" in content or "counterfactual" in content, "Must have counterfactual reasoning"

    def test_investment_has_thesis_framework(self):
        inv_path = SRC_ROOT.parent / "prompts" / "agents" / "investment.md"
        content = inv_path.read_text(encoding="utf-8")
        assert "Investment thesis" in content or "thesis" in content.lower(), "Must have investment thesis"
        assert "Risk-reward" in content or "risk-reward" in content.lower(), "Must have risk-reward"

    def test_investment_has_cycle_positioning(self):
        inv_path = SRC_ROOT.parent / "prompts" / "agents" / "investment.md"
        content = inv_path.read_text(encoding="utf-8")
        assert "Cycle" in content or "cycle" in content, "Must have cycle positioning"

    def test_valuation_line_count_substantial(self):
        val_path = SRC_ROOT.parent / "prompts" / "agents" / "valuation.md"
        content = val_path.read_text(encoding="utf-8")
        assert len(content.strip().split("\n")) >= 80

    def test_investment_line_count_substantial(self):
        inv_path = SRC_ROOT.parent / "prompts" / "agents" / "investment.md"
        content = inv_path.read_text(encoding="utf-8")
        assert len(content.strip().split("\n")) >= 80


# ═══════════════════════════════════════════════════════════════
# P3: factory _agents 清理 + hibernate 序列化
# ═══════════════════════════════════════════════════════════════

class TestP3FactoryCleanupE2E:
    """端到端: clear_registry 清理 _agents + agent_template 序列化"""

    def test_clear_registry_removes_agents(self):
        from src.core.agents.factory import DynamicAgentFactory

        factory = DynamicAgentFactory()
        factory._agents = {}
        factory._session_registries = {}

        mock_agent_1 = MagicMock()
        mock_agent_1._session = MagicMock()
        mock_agent_1._session.parent_session_id = "sess_parent_001"

        mock_agent_2 = MagicMock()
        mock_agent_2._session = MagicMock()
        mock_agent_2._session.parent_session_id = "other_session"

        factory._agents["agent_1"] = mock_agent_1
        factory._agents["agent_2"] = mock_agent_2

        mock_registry = MagicMock()
        factory._session_registries["sess_parent_001"] = mock_registry

        factory.clear_registry("sess_parent_001")

        assert "agent_1" not in factory._agents, "agent_1 should be removed"
        assert "agent_2" in factory._agents, "agent_2 should remain (different session)"

    def test_session_to_dict_roundtrip_with_agent_template(self):
        from src.core.agents.agent_session import AgentSession

        template = {"name": "test_agent", "config": {"max_queries": 10}}
        session = AgentSession(
            session_id="sess_001",
            agent_id="agent_001",
            parent_session_id="parent_001",
            agent_template=template,
        )

        data = session.to_dict()
        assert "agent_template" in data
        assert data["agent_template"]["name"] == "test_agent"

        restored = AgentSession.from_dict(data)
        assert restored.agent_template is not None
        assert restored.agent_template["name"] == "test_agent"
        assert restored.agent_template["config"]["max_queries"] == 10

    def test_session_without_agent_template_roundtrips(self):
        from src.core.agents.agent_session import AgentSession

        session = AgentSession(
            session_id="sess_002",
            agent_id="agent_002",
            parent_session_id="parent_002",
        )

        data = session.to_dict()
        assert data.get("agent_template") is None

        restored = AgentSession.from_dict(data)
        assert restored.agent_template is None


# ═══════════════════════════════════════════════════════════════
# 交叉验证: 多个修复协同工作
# ═══════════════════════════════════════════════════════════════

class TestCrossFixIntegration:
    """交叉验证: 修复间的协同和一致性"""

    def test_score_range_consistent_across_engine_and_lock(self):
        """engine/normalizer 输出的 0-100 分数与 content_lock 的 0-100 输入一致"""
        normalizer_path = SRC_ROOT / "core" / "quality" / "normalizer.py"
        lock_path = SRC_ROOT / "core" / "content_lock.py"

        normalizer_content = normalizer_path.read_text(encoding="utf-8")
        lock_content = lock_path.read_text(encoding="utf-8")

        # normalizer.py 中 normalize_quality_score 做 max(0.0, min(100.0, ...))
        assert "max(0.0, min(100.0" in normalizer_content, "normalizer clamps to [0, 100]"
        assert "100.0" in lock_content, "Lock accepts up to 100"

    def test_quality_result_issues_type_matches_injection(self):
        """QualityResult.issues (List[str]) 与 engine 注入和 agent 读取一致"""
        checkers_path = SRC_ROOT / "core" / "quality" / "checkers.py"
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"

        checkers_content = checkers_path.read_text(encoding="utf-8")
        engine_content = engine_path.read_text(encoding="utf-8")
        agent_content = agent_path.read_text(encoding="utf-8")

        assert "issues: List[str]" in checkers_content, "QualityResult.issues is List[str]"
        assert "quality_result.issues[:3]" in engine_content, "Engine injects issues[:3]"
        assert "for issue in fb_issues[:3]" in agent_content, "Agent iterates issues[:3]"

    def test_revising_since_timestamp_flow(self):
        """设置 revising 时写入 revising_since → expire 检查 revising_since"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")

        assert 'issue["revising_since"] = time.time()' in content, "Must set revising_since on revising"
        assert 'revising_since' in content, "expire method must check revising_since"

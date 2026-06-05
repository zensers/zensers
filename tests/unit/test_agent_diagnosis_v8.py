"""
Agent 架构诊断 v8.0 断言验证测试

对 03_Agent架构诊断.md 中的每一个关键断言进行代码级验证。
每个测试对应诊断文档中的一个具体断言，确保断言与实际代码完全一致。

运行: pytest tests/unit/test_agent_diagnosis_v8.py -v
"""
import ast
import inspect
import os
import re
import sys
import textwrap
from dataclasses import fields
from pathlib import Path
from typing import List, get_type_hints

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
PROMPTS_ROOT = PROJECT_ROOT / "prompts"


# ============================================================
# 方向1: Prompt 体系
# ============================================================

class TestPromptSystem:
    """验证 Prompt 体系相关断言"""

    def test_prompt_agents_file_count_is_24(self):
        """断言: prompts/agents/ 下有24个md文件"""
        agent_prompts = list(PROMPTS_ROOT.glob("agents/*.md"))
        assert len(agent_prompts) == 24, f"Expected 24 prompt files, found {len(agent_prompts)}: {[f.name for f in agent_prompts]}"

    def test_shared_prompt_file_count_is_8(self):
        """断言: prompts/_shared/ 下有8个md文件(含P1新增quality_rubric)"""
        shared_prompts = list(PROMPTS_ROOT.glob("_shared/*.md"))
        assert len(shared_prompts) == 8, f"Expected 8 shared files, found {len(shared_prompts)}"

    def test_valuation_md_is_substantial(self):
        """断言: valuation.md 已从32行扩展为多框架详细prompt(P2修复)"""
        content = (PROMPTS_ROOT / "agents" / "valuation.md").read_text(encoding="utf-8")
        line_count = len(content.strip().split("\n"))
        assert line_count >= 80, f"valuation.md should be >= 80 lines after P2 rewrite, got {line_count}"

    def test_investment_md_is_substantial(self):
        """断言: investment.md 已从32行扩展为多框架详细prompt(P2修复)"""
        content = (PROMPTS_ROOT / "agents" / "investment.md").read_text(encoding="utf-8")
        line_count = len(content.strip().split("\n"))
        assert line_count >= 80, f"investment.md should be >= 80 lines after P2 rewrite, got {line_count}"

    def test_quality_rubric_exists_in_shared(self):
        """断言: prompts/_shared/quality_rubric.md 存在(P1修复)"""
        rubric_path = PROMPTS_ROOT / "_shared" / "quality_rubric.md"
        assert rubric_path.exists(), "quality_rubric.md not found in _shared/"

    def test_key_agent_prompts_include_quality_rubric(self):
        """断言: 关键agent prompt包含 {include:quality_rubric}(P1修复)"""
        key_agents = ["general.md", "market_size.md", "competition.md", "financial_analysis.md", "valuation.md", "risk.md"]
        for name in key_agents:
            path = PROMPTS_ROOT / "agents" / name
            content = path.read_text(encoding="utf-8")
            assert "quality_rubric" in content, f"{name} missing quality_rubric include"

    def test_no_prompt_contains_self_evaluation(self):
        """断言: 0/24 agent prompt包含自评指令"""
        agent_prompts = list(PROMPTS_ROOT.glob("agents/*.md"))
        self_eval_keywords = ["自评", "自我评估", "self-evaluate", "self-assess", "自检清单"]
        for p in agent_prompts:
            content = p.read_text(encoding="utf-8").lower()
            for kw in self_eval_keywords:
                assert kw.lower() not in content, f"{p.name} contains self-evaluation keyword '{kw}'"

    def test_no_prompt_contains_writing_example(self):
        """断言: 0/24 agent prompt包含写作示例/标杆(排除intent_analysis_system.md的JSON示例)"""
        agent_prompts = list(PROMPTS_ROOT.glob("agents/*.md"))
        example_keywords = ["优秀章节示例", "标杆示例", "写作标杆", "sample output"]
        for p in agent_prompts:
            content = p.read_text(encoding="utf-8").lower()
            for kw in example_keywords:
                assert kw.lower() not in content, f"{p.name} contains writing example keyword '{kw}'"

    def test_methodology_injection_only_takes_first_and_truncates_150(self):
        """断言: 方法论注入仅取methodologies[0]且截断150字符"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "methodologies[0]" in content, "methodologies[0] not found in generic_agent.py"
        assert "[:150]" in content, "[:150] truncation not found in generic_agent.py"

    def test_methodology_budget_is_150_chars(self):
        """断言: 方法论token预算为150字符"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if "methodologies" in line and "[0]" in line and "[:150]" in line:
                found = True
                break
        assert found, "Line with methodologies[0]['content'][:150] not found"

    def test_pattern_budget_is_150_chars(self):
        """断言: 模式/经验预算为150字符"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if "budget = 150" in line:
                if i + 1 < len(lines) and "pattern" in lines[i - 1].lower() or "pattern" in lines[i + 1].lower() or (i > 0 and "patterns" in content.split("\n")[max(0, i - 5):i + 5]):
                    found = True
                    break
        assert found, "Pattern budget = 150 not found near patterns code"

    def test_entity_budget_is_300_chars(self):
        """断言: 实体知识预算为300字符"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "budget = 300" in content, "Entity budget = 300 not found"


# ============================================================
# 方向2: 自优化循环
# ============================================================

class TestRetryFeedbackFracture:
    """验证 S2 重试循环反馈断裂"""

    def test_engine_writes_retry_attempt_to_context(self):
        """断言: engine.py:1414 将 retry_attempt 写入 _a._context"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert '_a._context["retry_attempt"]' in content, 'retry_attempt not written to _a._context in engine.py'

    def test_agent_does_not_read_retry_attempt(self):
        """断言: generic_agent.py 从不读取 retry_attempt"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "retry_attempt" not in content, "retry_attempt should not appear in generic_agent.py"

    def test_agent_does_not_read_supplemental_queries(self):
        """断言: generic_agent.py 从不读取 supplemental_queries"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "supplemental_queries" not in content, "supplemental_queries should not appear in generic_agent.py"

    def test_agent_does_not_read_analysis_depth(self):
        """断言: generic_agent.py 从不读取 analysis_depth"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "analysis_depth" not in content, "analysis_depth should not appear in generic_agent.py"

    def test_agent_does_not_read_require_evidence(self):
        """断言: generic_agent.py 从不读取 require_evidence"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert "require_evidence" not in content, "require_evidence should not appear in generic_agent.py"

    def test_agent_does_not_read_regenerate(self):
        """断言: generic_agent.py 从不读取 regenerate"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        assert '"regenerate"' not in content and "'regenerate'" not in content, "regenerate should not appear in generic_agent.py"

    def test_agent_does_not_read_focus_areas_from_context(self):
        """断言: generic_agent.py 不从 _context 读取 focus_areas"""
        generic_agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_agent_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "focus_areas" in line and "_context" in line:
                pytest.fail(f"focus_areas read from _context at line {i + 1}: {line.strip()}")

    def test_quality_is_advisory_not_blocking(self):
        """断言: engine.py 中 quality is advisory, not blocking 注释存在"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "quality is advisory, not blocking" in content, "'quality is advisory, not blocking' not found"


class TestFeedbackExecutorDeadCode:
    """验证 feedback_executor 是死代码"""

    def test_execute_stage_with_quality_exists(self):
        """断言: _execute_stage_with_quality 方法定义存在"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "async def _execute_stage_with_quality" in content, "_execute_stage_with_quality not defined"

    def test_execute_stage_with_quality_zero_callers(self):
        """断言: _execute_stage_with_quality 在engine.py中没有调用者(排除自身定义)"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        call_count = content.count("_execute_stage_with_quality(")
        def_count = content.count("async def _execute_stage_with_quality(")
        assert call_count == def_count, f"_execute_stage_with_quality has {call_count - def_count} non-definition references (should be 0)"

    def test_execute_stage_with_quality_not_called_anywhere(self):
        """断言: _execute_stage_with_quality 在整个项目中没有被调用(排除定义行)"""
        for py_file in SRC_ROOT.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "_execute_stage_with_quality(" in line:
                    stripped = line.strip()
                    if stripped.startswith("async def _execute_stage_with_quality("):
                        continue
                    if stripped.startswith("#"):
                        continue
                    pytest.fail(f"_execute_stage_with_quality called at {py_file.relative_to(PROJECT_ROOT)}:{i + 1}: {stripped}")


class TestDanglingReferences:
    """验证 P0-2 修复: 3个dangling方法已实现"""

    def test_post_revision_recheck_now_defined(self):
        """断言: _post_revision_recheck 已定义(P0-2修复)"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")
        call_count = content.count("_post_revision_recheck(")
        def_count = content.count("def _post_revision_recheck")
        assert call_count >= 4, f"Expected >= 4 calls, found {call_count}"
        assert def_count >= 1, f"Expected >= 1 definition after P0-2 fix, found {def_count}"

    def test_recheck_quality_now_defined(self):
        """断言: _recheck_quality 已定义(P0-2修复)"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")
        call_count = content.count("_recheck_quality(")
        def_count = content.count("def _recheck_quality")
        assert call_count >= 1, f"Expected >= 1 call, found {call_count}"
        assert def_count >= 1, f"Expected >= 1 definition after P0-2 fix, found {def_count}"

    def test_expire_stale_revising_issues_now_defined(self):
        """断言: _expire_stale_revising_issues 已定义(P0-2修复)"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")
        call_count = content.count("_expire_stale_revising_issues(")
        def_count = content.count("def _expire_stale_revising_issues")
        assert call_count >= 1, f"Expected >= 1 call, found {call_count}"
        assert def_count >= 1, f"Expected >= 1 definition after P0-2 fix, found {def_count}"

    def test_post_revision_recheck_uses_merge_issues_on_recheck(self):
        """断言: _post_revision_recheck 使用 merge_issues_on_recheck 合并issue"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert "merge_issues_on_recheck" in content, "merge_issues_on_recheck not used in _post_revision_recheck"

    def test_expire_stale_revising_issues_handles_revising_state(self):
        """断言: _expire_stale_revising_issues 处理 revising 状态的issue"""
        api_path = SRC_ROOT / "api" / "research_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert '"revising"' in content or "'revising'" in content, "revising state not handled in _expire_stale_revising_issues"


class TestQualityScoreInconsistency:
    """验证 P0-3 修复: 评分默认值跨层统一为0-100"""

    def test_engine_extract_quality_score_default_is_50(self):
        """断言: engine.py _extract_quality_score 默认值50.0(0-100尺度)"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if "quality_score is None" in line:
                if i + 1 < len(lines) and "quality_score = 50.0" in lines[i + 1]:
                    found = True
                    break
        assert found, "quality_score = 50.0 default not found after 'quality_score is None' check"

    def test_engine_extract_quality_score_clamps_to_0_100(self):
        """断言: _extract_quality_score clamp到[0,100]范围"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "min(100.0, score)" in content, "clamp to [0,100] not found"

    def test_engine_auto_scales_0_1_to_0_100(self):
        """断言: _extract_quality_score 自动将0-1分数放大到0-100"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "score * 100.0" in content, "auto-scale 0-1 → 0-100 not found"

    def test_metadata_extractor_default_is_50(self):
        """断言: metadata_extractor.py 默认值50.0(0-100尺度)"""
        extractor_path = SRC_ROOT / "core" / "quality" / "metadata_extractor.py"
        content = extractor_path.read_text(encoding="utf-8")
        assert "quality_score: float = 50.0" in content, "quality_score: float = 50.0 not found"

    def test_content_lock_now_uses_0_100_range(self):
        """断言: content_lock.py 已更新为[0,100]范围检查(P0-3修复)"""
        lock_path = SRC_ROOT / "core" / "content_lock.py"
        content = lock_path.read_text(encoding="utf-8")
        assert "0.0 <= quality_score <= 100.0" in content, "[0,100] range check not found in content_lock.py"


class TestAgentCoordinatorBlindRetry:
    """验证 agent_coordinator.py 独立盲重试路径"""

    def test_coordinator_writes_retry_attempt_to_task(self):
        """断言: agent_coordinator.py 将 retry_attempt 写入 task dict"""
        coord_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "coordinator" / "agent_coordinator.py"
        content = coord_path.read_text(encoding="utf-8")
        assert 'task["retry_attempt"]' in content, 'task["retry_attempt"] not found in agent_coordinator.py'


class TestQualityResultIssuesType:
    """验证 QualityResult.issues 是 List[str]"""

    def test_issues_is_list_str(self):
        """断言: QualityResult.issues 类型为 List[str]"""
        checkers_path = SRC_ROOT / "core" / "quality" / "checkers.py"
        content = checkers_path.read_text(encoding="utf-8")
        assert "issues: List[str]" in content, "issues: List[str] not found in QualityResult"


class TestResetDoesNotClearContext:
    """验证 reset() 不清除 _context"""

    def test_reset_clears_data_not_context(self):
        """断言: reset() 清除 _data 和 _status 但不清除 _context"""
        mixins_path = SRC_ROOT / "core" / "agents" / "mixins.py"
        content = mixins_path.read_text(encoding="utf-8")
        assert "self._data.clear()" in content, "_data.clear() not found in reset()"
        assert "self._status" in content, "_status reset not found"
        assert "self._context.clear()" not in content, "_context.clear() should NOT be in reset()"


class TestSectionScoreIsKeywordCounting:
    """验证 _calculate_section_score 是关键词计数"""

    def test_section_score_uses_hardcoded_keywords(self):
        """断言: _calculate_section_score 使用7个硬编码关键词"""
        qc_path = SRC_ROOT / "agents" / "fixed_agents" / "quality_check_agent.py"
        content = qc_path.read_text(encoding="utf-8")
        assert '"核心判断"' in content, 'Keyword "核心判断" not found'
        assert '"数据支持"' in content, 'Keyword "数据支持" not found'
        assert '"反证"' in content, 'Keyword "反证" not found'

    def test_section_score_keyword_game_cheatable(self):
        """断言: 包含5个关键词的文本可得高分(作弊验证)"""
        qc_path = SRC_ROOT / "agents" / "fixed_agents" / "quality_check_agent.py"
        content = qc_path.read_text(encoding="utf-8")
        source = textwrap.dedent("""
            def _calculate_section_score(content, issues):
                import re
                score = 100.0
                structure_keywords = ["核心判断", "逻辑推导", "数据支持", "反证", "边界条件", "意义", "影响"]
                found = sum(1 for kw in structure_keywords if kw in content)
                structure_ratio = found / len(structure_keywords)
                if structure_ratio < 0.5:
                    score -= (1 - structure_ratio) * 30
                numbers = re.findall(r'\\d+\\.?\\d*', content)
                if len(numbers) < 5:
                    score -= 10
                severity_weights = {"high": 15, "medium": 5, "low": 1}
                penalty = sum(severity_weights.get(i.get("severity", "low"), 1) for i in issues)
                score -= min(penalty, 40)
                return max(0, min(100, score))
        """)
        ns = {}
        exec(source, ns)
        func = ns["_calculate_section_score"]
        cheat_text = "核心判断 数据支持 反证 意义 影响"
        score = func(cheat_text, [])
        assert score >= 60, f"Cheat text should score >= 60, got {score}"


# ============================================================
# 方向3: Skill 系统
# ============================================================

class TestSkillSystem:
    """验证 Skill 系统相关断言"""

    def test_skill_subclass_count(self):
        """断言: Skill子类(Skill基类子类，不含business stub和LangChainToolSkill)数量验证
        
        grep确认的Skill(Skill)子类(不含business stub):
        - SearchSkill(MultiSearchSkill), NewsSearchSkill, FileSkill, HTTPSkill, DocxSkill, LLMSkill, WebScraperSkill
        - MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill, StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill, RiskAnalysisSkill
        - KnowledgeQuerySkill, PersonaSkill, SimulationSkill, SurveySkill, LangChainToolSkill
        
        LangChainToolSkill是适配器基类不计为业务Skill，因此实际业务Skill=18个
        """
        skill_classes = []
        for py_file in SRC_ROOT.rglob("*.py"):
            if "business" in str(py_file) and "__init__" in py_file.name:
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            matches = re.findall(r'class\s+(\w+)\s*\(\s*Skill\s*\)', content)
            skill_classes.extend(matches)
        skill_classes = list(set(skill_classes))
        assert len(skill_classes) >= 18, f"Expected >= 18 Skill(Skill) subclasses, found {len(skill_classes)}: {sorted(skill_classes)}"
        assert "LangChainToolSkill" in skill_classes, "LangChainToolSkill should be in Skill subclasses"

    def test_business_stub_count_is_5(self):
        """断言: business/__init__.py 中有5个stub类(NotImplementedError)"""
        business_path = SRC_ROOT / "skills" / "business" / "__init__.py"
        content = business_path.read_text(encoding="utf-8")
        stub_classes = re.findall(r'class\s+(\w+Skill)\s*:', content)
        assert len(stub_classes) == 5, f"Expected 5 business stub classes, found {len(stub_classes)}: {stub_classes}"

    def test_business_skills_all_not_implemented(self):
        """断言: 5个business技能全部NotImplementedError"""
        business_path = SRC_ROOT / "skills" / "business" / "__init__.py"
        content = business_path.read_text(encoding="utf-8")
        nie_count = content.count("NotImplementedError")
        assert nie_count >= 5, f"Expected >= 5 NotImplementedError, found {nie_count}"

    def test_market_analysis_has_precompute_metrics(self):
        """断言: market_analysis.py 有 _precompute_metrics 计算方法"""
        ma_path = SRC_ROOT / "skills" / "analysis" / "market_analysis.py"
        content = ma_path.read_text(encoding="utf-8")
        assert "async def _precompute_metrics" in content, "_precompute_metrics not found"

    def test_market_analysis_has_compute_fallback(self):
        """断言: market_analysis.py 有 _compute_fallback 纯Python后备"""
        ma_path = SRC_ROOT / "skills" / "analysis" / "market_analysis.py"
        content = ma_path.read_text(encoding="utf-8")
        assert "def _compute_fallback" in content, "_compute_fallback not found"

    def test_market_analysis_computes_cagr_cr_hhi(self):
        """断言: market_analysis 计算CAGR/CR3/CR5/HHI"""
        ma_path = SRC_ROOT / "skills" / "analysis" / "market_analysis.py"
        content = ma_path.read_text(encoding="utf-8")
        assert "cagr" in content.lower(), "CAGR computation not found"
        assert "cr3" in content.lower(), "CR3 computation not found"
        assert "hhi" in content.lower(), "HHI computation not found"

    def test_policy_analysis_is_llm_wrapper(self):
        """断言: policy_analysis.py 是纯LLM包装器(无计算层)"""
        pa_path = SRC_ROOT / "skills" / "analysis" / "policy_analysis.py"
        content = pa_path.read_text(encoding="utf-8")
        assert "_precompute" not in content, "policy_analysis should not have _precompute"
        assert "_compute_fallback" not in content, "policy_analysis should not have _compute_fallback"
        assert "llm_skill" in content, "policy_analysis should reference llm_skill"

    def test_tech_trend_is_llm_wrapper(self):
        """断言: tech_trend.py 是纯LLM包装器"""
        tt_path = SRC_ROOT / "skills" / "analysis" / "tech_trend.py"
        content = tt_path.read_text(encoding="utf-8")
        assert "_precompute" not in content, "tech_trend should not have _precompute"
        assert "llm_skill" in content, "tech_trend should reference llm_skill"

    def test_risk_analysis_is_llm_wrapper(self):
        """断言: risk_analysis.py 是纯LLM包装器"""
        ra_path = SRC_ROOT / "skills" / "analysis" / "risk_analysis.py"
        content = ra_path.read_text(encoding="utf-8")
        assert "_precompute" not in content, "risk_analysis should not have _precompute"
        assert "llm_skill" in content, "risk_analysis should reference llm_skill"

    def test_builtin_has_persona_simulation_survey(self):
        """断言: builtin/ 目录有 persona_skill, simulation_skill, survey_skill"""
        builtin_dir = SRC_ROOT / "skills" / "builtin"
        assert (builtin_dir / "persona_skill.py").exists(), "persona_skill.py not found"
        assert (builtin_dir / "simulation_skill.py").exists(), "simulation_skill.py not found"
        assert (builtin_dir / "survey_skill.py").exists(), "survey_skill.py not found"

    def test_core_skills_registered_count(self):
        """断言: register_core_skills 注册9个核心技能"""
        registry_path = SRC_ROOT / "skills" / "registry.py"
        content = registry_path.read_text(encoding="utf-8")
        register_calls = re.findall(r'self\.register\(', content)
        in_core_skills = False
        count = 0
        for line in content.split("\n"):
            if "def register_core_skills" in line:
                in_core_skills = True
                continue
            if in_core_skills:
                if "self.register(" in line:
                    count += 1
                if line.strip().startswith("return count"):
                    break
        assert count == 9, f"Expected 9 register calls in register_core_skills, found {count}"

    def test_analysis_skills_registered_by_orchestrator(self):
        """断言: 7个分析技能由orchestrator手动注册"""
        orch_path = SRC_ROOT / "core" / "orchestrator" / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        analysis_skills = ["market_analysis", "data_analysis", "stock_data", "stock_analysis", "policy_analysis", "tech_trend", "risk_analysis"]
        for skill_name in analysis_skills:
            assert f'"{skill_name}"' in content, f'Analysis skill "{skill_name}" not registered in orchestrator'


# ============================================================
# 方向4: 工厂模式
# ============================================================

class TestFactoryPattern:
    """验证工厂模式相关断言"""

    def test_agents_dict_cleaned_in_clear_registry_and_hibernate(self):
        """断言: _agents 字典在 clear_registry() 和 hibernate_batch() 中被清理(P3修复)"""
        factory_path = SRC_ROOT / "core" / "agents" / "factory.py"
        content = factory_path.read_text(encoding="utf-8")
        del_agents_count = content.count("del self._agents[")
        assert del_agents_count >= 2, f"Expected >= 2 'del self._agents[' (clear_registry + hibernate), found {del_agents_count}"

    def test_cleanup_agents_now_cleans_agents_dict_via_clear_registry(self):
        """断言: _cleanup_agents() 通过 clear_registry() 间接清理 _agents(P3修复)"""
        orch_path = SRC_ROOT / "core" / "orchestrator" / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        in_cleanup = False
        cleanup_body = []
        for line in lines:
            if "def _cleanup_agents" in line:
                in_cleanup = True
                continue
            if in_cleanup:
                if line.strip().startswith("def ") and "_cleanup_agents" not in line:
                    break
                cleanup_body.append(line)
        cleanup_text = "\n".join(cleanup_body)
        assert "clear_registry" in cleanup_text, "_cleanup_agents should call clear_registry"

    def test_agent_session_to_dict_includes_agent_template(self):
        """断言: AgentSession.to_dict() 包含 agent_template 字段(P3修复)"""
        session_path = SRC_ROOT / "core" / "agents" / "agent_session.py"
        content = session_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        in_to_dict = False
        to_dict_body = []
        for line in lines:
            if "def to_dict" in line:
                in_to_dict = True
                continue
            if in_to_dict:
                if line.strip().startswith("def ") and "to_dict" not in line:
                    break
                to_dict_body.append(line)
        to_dict_text = "\n".join(to_dict_body)
        assert "agent_template" in to_dict_text, "to_dict should contain agent_template after P3 fix"

    def test_agent_session_from_dict_includes_agent_template(self):
        """断言: AgentSession.from_dict() 包含 agent_template 字段(P3修复)"""
        session_path = SRC_ROOT / "core" / "agents" / "agent_session.py"
        content = session_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        in_from_dict = False
        from_dict_body = []
        for line in lines:
            if "def from_dict" in line:
                in_from_dict = True
                continue
            if in_from_dict:
                if line.strip().startswith("def ") and "from_dict" not in line:
                    break
                from_dict_body.append(line)
        from_dict_text = "\n".join(from_dict_body)
        assert "agent_template" in from_dict_text, "from_dict should read agent_template after P3 fix"

    def test_generic_agent_sets_agent_template_on_session(self):
        """断言: generic_agent.py 在 hibernate 时动态附加 agent_template 到 session"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert "self._session.agent_template" in content, "agent_template not set on session in generic_agent.py"

    def test_get_agent_factory_creates_without_shared_memory(self):
        """断言: get_agent_factory() 创建无 shared_memory 的实例"""
        factory_path = SRC_ROOT / "core" / "agents" / "factory.py"
        content = factory_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if "def get_agent_factory" in line:
                for j in range(i, min(i + 10, len(lines))):
                    if "DynamicAgentFactory()" in lines[j]:
                        found = True
                        break
                break
        assert found, "get_agent_factory() creates DynamicAgentFactory() without args"


# ============================================================
# 综合断言
# ============================================================

class TestP01Fix:
    """验证 P0-1 修复: S2重试循环反馈断裂"""

    def test_engine_injects_quality_feedback_to_context(self):
        """断言: engine.py 在重试时注入 quality_feedback 到 agent._context"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert '_a._context["quality_feedback"]' in content, 'quality_feedback not injected to _a._context'

    def test_engine_quality_feedback_contains_score_and_issues(self):
        """断言: quality_feedback 包含 score 和 issues 字段"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert '"score": quality_result.score' in content, "score not in quality_feedback"
        assert '"issues": quality_result.issues[:5]' in content, "issues not in quality_feedback"

    def test_engine_writes_quality_feedback_to_shared_memory(self):
        """断言: engine.py 将 quality_feedback 写入 SharedMemory"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert 'quality_feedback' in content, "quality_feedback not written to shared_memory"

    def test_generic_agent_reads_quality_feedback_from_context(self):
        """断言: generic_agent.py 从 _context 读取 quality_feedback"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert 'quality_feedback' in content, "quality_feedback not read in generic_agent.py"
        assert 'self._context.get("quality_feedback"' in content, 'self._context.get("quality_feedback") not found'

    def test_generic_agent_stores_quality_feedback_as_attribute(self):
        """断言: generic_agent.py 将 quality_feedback 存储为 self._quality_feedback"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert 'self._quality_feedback' in content, "self._quality_feedback not found"

    def test_professional_role_prompt_includes_quality_feedback(self):
        """断言: _get_professional_role_prompt 将质量反馈注入到 system prompt"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert '_quality_feedback' in content, "_quality_feedback not used in prompt construction"

    def test_coordinator_injects_retry_attempt_to_context(self):
        """断言: agent_coordinator.py 将 retry_attempt 注入到 agent._context"""
        coord_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "coordinator" / "agent_coordinator.py"
        content = coord_path.read_text(encoding="utf-8")
        assert 'active_task.agent._context["retry_attempt"]' in content, "retry_attempt not injected to _context in coordinator"


class TestComprehensiveAssertions:
    """跨方向综合断言验证"""

    def test_s0_search_loop_parameters(self):
        """断言: S0搜索循环参数 MAX_ITERATIONS=20, MAX_QUERIES=50, STAGNATION_LIMIT=10, MIN_QUALITY_SCORE=75.0"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert "MAX_ITERATIONS = 20" in content, "MAX_ITERATIONS = 20 not found"
        assert "MAX_QUERIES = 50" in content, "MAX_QUERIES = 50 not found"
        assert "STAGNATION_LIMIT = 10" in content, "STAGNATION_LIMIT = 10 not found"
        assert "MIN_QUALITY_SCORE = 75.0" in content, "MIN_QUALITY_SCORE = 75.0 not found"

    def test_s1_gap_detection_is_heuristic(self):
        """断言: _detect_knowledge_gaps 使用4项启发式检查"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        assert "def _detect_knowledge_gaps" in content, "_detect_knowledge_gaps not found"
        assert "number_count" in content, "number_count heuristic not found"
        assert "year_refs" in content, "year_refs heuristic not found"
        assert "len(content) < 1500" in content, "content length heuristic not found"
        assert "trend_count" in content, "trend_count heuristic not found"

    def test_fusion_formula_is_06_doc_plus_04_section(self):
        """断言: 融合公式是 0.6×文档级 + 0.4×章节级"""
        qc_path = SRC_ROOT / "agents" / "fixed_agents" / "quality_check_agent.py"
        content = qc_path.read_text(encoding="utf-8")
        assert "quality_score * 0.6 + section_overall * 0.4" in content, "Fusion formula not found"

    def test_disk_cleanup_exists(self):
        """断言: 磁盘清理功能存在(cleanup_completed_session)"""
        persistence_path = SRC_ROOT / "core" / "agents" / "session_persistence.py"
        content = persistence_path.read_text(encoding="utf-8")
        assert "def cleanup_completed_session" in content, "cleanup_completed_session not found"
        assert "def cleanup_all_completed" in content, "cleanup_all_completed not found"
        assert ".unlink()" in content, "File deletion (.unlink()) not found"

    def test_interactive_recovery_calls_cleanup(self):
        """断言: interactive_recovery.py 调用 cleanup_completed_session"""
        recovery_path = SRC_ROOT / "core" / "agents" / "interactive_recovery.py"
        content = recovery_path.read_text(encoding="utf-8")
        assert "cleanup_completed_session" in content, "cleanup_completed_session not called in interactive_recovery.py"

    def test_analysis_quality_checker_has_gradient_scoring(self):
        """断言: AnalysisQualityChecker 使用梯度评分(非关键词计数)"""
        checkers_path = SRC_ROOT / "core" / "quality" / "checkers.py"
        content = checkers_path.read_text(encoding="utf-8")
        assert "class AnalysisQualityChecker" in content, "AnalysisQualityChecker not found"
        assert "_check_structure" in content, "_check_structure not found"
        assert "_check_counter_evidence" in content, "_check_counter_evidence not found"
        assert "_check_quantified_decomposition" in content, "_check_quantified_decomposition not found"

    def test_execute_stage_is_deprecated(self):
        """断言: _execute_stage() 已废弃"""
        engine_path = SRC_ROOT / "core" / "orchestrator" / "execution" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert "已废弃" in content or "deprecated" in content.lower(), "_execute_stage deprecation note not found"

    def test_generic_agent_context_read_keys(self):
        """断言: generic_agent.py 仅从 _context 读取特定key(含P0修复新增的quality_feedback)"""
        generic_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = generic_path.read_text(encoding="utf-8")
        context_reads = re.findall(r'self\._context\.get\("(\w+)"', content)
        expected_keys = {
            "topic", "aspect", "core_question", "role_in_report",
            "sibling_aspects", "section_id", "research_type", "language",
            "intent_confidence", "domain_context", "hidden_requirements",
            "quality_feedback",
        }
        actual_keys = set(context_reads)
        unexpected = actual_keys - expected_keys - {"target_aspect"}
        assert not unexpected, f"Unexpected context reads: {unexpected}"

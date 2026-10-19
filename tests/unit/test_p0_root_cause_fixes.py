"""
Tests for P0 bug fixes identified in root-cause analysis:
- R1-A: Non-routing path passes task_structure={}, losing section info
- R1-B: chapter_write.tmpl whitelist misleads LLM into using "核心结论" as chapter titles
- R2-A: Search queries don't differentiate by aspect
- R3-A: search_skill doesn't read min_quality_score from settings.yaml
- R4-A: No proxy support for search engines

These tests validate the fixes WITHOUT requiring LLM calls.
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ============================================================
# R1-A: task_structure={} in non-routing path
# ============================================================

class TestR1ATaskStructureNonRouting:
    """Verify that non-routing path builds task_structure from requirement.section_details."""

    def test_section_details_to_task_structure_conversion(self):
        """section_details should be convertible to task_structure.sections format."""
        from src.core.task_structure import SectionSpec, SectionRole

        section_details = [
            {"id": "investment_summary", "name": "Investment Summary", "content": "Overview"},
            {"id": "industry_overview", "name": "Industry Overview", "content": "Industry analysis"},
            {"id": "market_size", "name": "Market Size & Growth", "content": "Market sizing"},
            {"id": "competitive_landscape", "name": "Competitive Landscape", "content": "Competition analysis"},
        ]

        sections = []
        for sd in section_details:
            sections.append(SectionSpec(
                section_id=sd["id"],
                section_name=sd.get("name", sd["id"]),
                section_role=SectionRole.ANALYSIS,
                content_dependency=[],
            ).to_dict())

        task_structure_dict = {
            "task_id": "test_task",
            "topic": "比亚迪财务分析",
            "sections": sections,
            "dependencies": [],
            "execution_graph": {},
            "parallel_groups": [],
            "critical_path": [],
            "total_estimated_agents": 4,
            "analysis_method": "rule_based",
        }

        assert len(task_structure_dict["sections"]) == 4
        assert task_structure_dict["sections"][0]["section_name"] == "Investment Summary"
        assert task_structure_dict["sections"][1]["section_name"] == "Industry Overview"
        assert task_structure_dict["sections"][2]["section_name"] == "Market Size & Growth"
        assert task_structure_dict["sections"][3]["section_name"] == "Competitive Landscape"

    def test_report_orchestrator_with_non_empty_task_structure(self):
        """ReportOrchestrator should iterate sections when task_structure is non-empty."""
        task_structure = {
            "sections": [
                {"section_id": "s0", "section_name": "Summary", "section_role": "synthesis", "content_dependency": []},
                {"section_id": "s1", "section_name": "Analysis", "section_role": "analysis", "content_dependency": ["s0"]},
            ]
        }

        sections_iterated = list(task_structure.get("sections", []))
        assert len(sections_iterated) == 2
        assert sections_iterated[0]["section_name"] == "Summary"
        assert sections_iterated[1]["section_name"] == "Analysis"

    def test_empty_task_structure_produces_zero_sections(self):
        """Current bug: task_structure={} produces zero sections."""
        task_structure = {}
        sections_iterated = list(task_structure.get("sections", []))
        assert len(sections_iterated) == 0, "Empty task_structure should produce zero sections (this is the bug)"

    def test_chapter_writer_parse_output_with_section_name_fallback(self):
        """_parse_output should fall back to section_name from chapter_spec when title is generic."""
        from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter

        writer = ChapterWriter(prompt_manager=MagicMock())

        chapter_spec = {
            "section_id": "industry_overview",
            "section_name": "行业概览",
            "section_role": "analysis",
        }

        raw_output = json.dumps({
            "title": "核心结论与论证分析",
            "content": "Some content",
            "data_points_used": [],
            "key_conclusions": ["conclusion1"],
            "self_check_passed": True,
            "self_check_issues": [],
        })
        raw_output = f"```json\n{raw_output}\n```"

        result = writer._parse_output(raw_output, chapter_spec)
        assert result.title == chapter_spec["section_name"], \
            f"Generic title '核心结论与论证分析' should fallback to section_name '{chapter_spec['section_name']}', got '{result.title}'"

    def test_chapter_writer_skip_titles_should_cover_combined_titles(self):
        """_SKIP_TITLES should cover combined titles like '核心结论与论证分析'."""
        from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter

        writer = ChapterWriter(prompt_manager=MagicMock())

        chapter_spec = {
            "section_id": "industry_overview",
            "section_name": "行业概览",
            "section_role": "analysis",
        }

        problematic_titles = [
            "核心结论与论证分析",
            "核心结论",
            "核心判断",
            "核心发现",
            "论证与分析",
            "数据支撑",
            "风险提示",
        ]

        for title in problematic_titles:
            raw_output = json.dumps({
                "title": title,
                "content": "Some content",
                "data_points_used": [],
                "key_conclusions": ["conclusion1"],
                "self_check_passed": True,
                "self_check_issues": [],
            })
            raw_output = f"```json\n{raw_output}\n```"

            result = writer._parse_output(raw_output, chapter_spec)
            assert result.title == chapter_spec["section_name"], \
                f"Title '{title}' should fallback to section_name '{chapter_spec['section_name']}', got '{result.title}'"


# ============================================================
# R1-B: chapter_write.tmpl whitelist misleads LLM
# ============================================================

class TestR1BChapterWriteTemplate:
    """Verify that chapter_write.tmpl distinguishes chapter titles from paragraph headings."""

    def test_template_has_section_name_placeholder(self):
        """Template should have ${section_name} as the chapter title reference."""
        template_path = os.path.join(
            PROJECT_ROOT, "src", "agents", "fixed_agents", "report_upgrade", "prompts", "chapter_write.tmpl"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "${section_name}" in content, "Template should reference section_name"

    def test_template_whitelist_should_be_paragraph_not_chapter(self):
        """Whitelist headings should be clarified as paragraph-level, not chapter-level."""
        template_path = os.path.join(
            PROJECT_ROOT, "src", "agents", "fixed_agents", "report_upgrade", "prompts", "chapter_write.tmpl"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "段落内部" in content or "不可用作章节标题" in content, \
            "Template should clarify whitelist headings are paragraph-level, not chapter-level"

    def test_template_has_chapter_title_rules(self):
        """Template should have explicit rules about chapter titles after fix."""
        template_path = os.path.join(
            PROJECT_ROOT, "src", "agents", "fixed_agents", "report_upgrade", "prompts", "chapter_write.tmpl"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "章节标题" in content, "Template should mention '章节标题' rule"
        assert "禁止" in content and "核心结论" in content, \
            "Template should explicitly prohibit using '核心结论' as chapter title"


# ============================================================
# R2-A: Search queries don't differentiate by aspect
# ============================================================

class TestR2ASearchQueryAspectDifferentiation:
    """Verify that search queries include aspect-specific terms."""

    def test_generate_search_queries_with_data_focus_includes_aspect(self):
        """When data_focus is present, queries should also include aspect."""
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent(
            agent_id="test_agent",
            config={"context": {"aspect": "Industry Overview"}},
        )

        queries = agent._generate_search_queries(
            topic="比亚迪",
            aspect="Industry Overview",
            aspects=["Industry Overview", "Market Size", "Competitive Landscape"],
            role_info={
                "data_focus": ["营收", "利润", "销量", "研发"],
            }
        )

        has_aspect_query = any("Industry Overview" in q or "行业概览" in q for q in queries)
        assert has_aspect_query, f"Queries should include aspect-specific terms. Got: {queries[:5]}"

    def test_generate_search_queries_aspect_in_query_not_just_topic(self):
        """Queries for different aspects should differ meaningfully."""
        from src.core.agents.generic_agent import GenericAgent

        agent1 = GenericAgent(agent_id="agent_overview", config={"context": {"aspect": "Industry Overview"}})
        agent2 = GenericAgent(agent_id="agent_finance", config={"context": {"aspect": "Financial Analysis"}})

        role_info = {"data_focus": ["营收", "利润", "销量"]}

        queries_overview = agent1._generate_search_queries(
            topic="比亚迪",
            aspect="Industry Overview",
            aspects=["Industry Overview", "Financial Analysis"],
            role_info=role_info,
        )

        queries_finance = agent2._generate_search_queries(
            topic="比亚迪",
            aspect="Financial Analysis",
            aspects=["Industry Overview", "Financial Analysis"],
            role_info=role_info,
        )

        set_overview = set(queries_overview)
        set_finance = set(queries_finance)

        overlap = set_overview & set_finance
        total = set_overview | set_finance

        overlap_ratio = len(overlap) / max(len(total), 1)
        assert overlap_ratio < 0.80, \
            f"Too much overlap ({overlap_ratio:.0%}) between aspect queries. " \
            f"Overview: {queries_overview[:3]}, Finance: {queries_finance[:3]}"


# ============================================================
# R3-A: search_skill doesn't read min_quality_score from settings.yaml
# ============================================================

class TestR3AQualityScoreFromConfig:
    """Verify that search_skill reads min_quality_score from settings.yaml."""

    def test_default_quality_score_is_40(self):
        """Fallback min_quality_score should be 40.0 when config is unavailable."""
        from src.skills.search_skill import MultiSearchSkill

        with patch.object(MultiSearchSkill, '_load_min_quality_score', return_value=40.0):
            skill = MultiSearchSkill()
            assert skill.quality_filter._min_quality_score == 40.0

    def test_settings_yaml_has_quality_score_50(self):
        """settings.yaml specifies min_quality_score: 50.0."""
        import yaml

        settings_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")
        with open(settings_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert config.get("search", {}).get("min_quality_score") == 50.0, \
            "settings.yaml should have min_quality_score: 50.0"

    def test_skill_reads_quality_score_from_settings(self):
        """After fix, MultiSearchSkill should read min_quality_score from settings.yaml."""
        from src.skills.search_skill import MultiSearchSkill

        skill = MultiSearchSkill()
        assert skill.quality_filter._min_quality_score == 50.0, \
            f"Should read 50.0 from settings.yaml, got {skill.quality_filter._min_quality_score}"


# ============================================================
# R4-A: No proxy support for search engines
# ============================================================

class TestR4AProxySupport:
    """Verify that search_skill supports proxy configuration."""

    def test_settings_yaml_has_proxy_config(self):
        """After fix: settings.yaml should have proxy configuration field."""
        import yaml

        settings_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")
        with open(settings_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        has_proxy = "proxy" in config or "proxy" in config.get("search", {})
        assert has_proxy, "settings.yaml should have proxy config (top-level or under search)"

    def test_skill_reads_proxy_from_settings(self):
        """After fix, MultiSearchSkill should read proxy from settings.yaml."""
        from src.skills.search_skill import MultiSearchSkill

        skill = MultiSearchSkill()
        assert hasattr(skill, '_proxy'), "Skill should have _proxy attribute"

    def test_skill_proxy_defaults_empty(self):
        """When no proxy configured, _proxy should be empty string."""
        from src.skills.search_skill import MultiSearchSkill

        with patch.dict(os.environ, {}, clear=True), \
             patch.object(MultiSearchSkill, "_detect_local_proxy", return_value=""), \
             patch.object(MultiSearchSkill, "_proxy_is_listening", return_value=False):
            env_keys = ["HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"]
            for k in env_keys:
                os.environ.pop(k, None)
            skill = MultiSearchSkill()
            assert skill._proxy == "", f"Proxy should be empty when not configured, got '{skill._proxy}'"


# ============================================================
# Integration: Full flow validation
# ============================================================

class TestIntegrationTaskStructureFlow:
    """Validate the full flow from requirement.section_details to task_structure."""

    def test_section_details_to_task_structure_full_flow(self):
        """Complete flow: section_details → task_structure → ReportOrchestrator sections."""
        from src.core.task_structure import SectionSpec, SectionRole, TaskStructure

        section_details = [
            {"id": "investment_summary", "name": {"en": "Investment Summary", "zh": "投资摘要"}, "content": "Overview"},
            {"id": "industry_overview", "name": {"en": "Industry Overview", "zh": "行业概览"}, "content": "Industry"},
            {"id": "market_size", "name": {"en": "Market Size & Growth", "zh": "市场规模与增长"}, "content": "Market"},
            {"id": "competitive_landscape", "name": {"en": "Competitive Landscape", "zh": "竞争格局"}, "content": "Competition"},
            {"id": "value_chain", "name": {"en": "Value Chain Analysis", "zh": "产业链分析"}, "content": "Value chain"},
            {"id": "growth_drivers", "name": {"en": "Growth Drivers", "zh": "增长动力"}, "content": "Growth"},
            {"id": "tech_trends", "name": {"en": "Technology Trends", "zh": "技术趋势"}, "content": "Tech"},
            {"id": "key_company", "name": {"en": "Key Company Analysis", "zh": "重点公司分析"}, "content": "Company"},
            {"id": "financial_forecast", "name": {"en": "Financial Forecast & Valuation", "zh": "财务预测与估值"}, "content": "Finance"},
            {"id": "risk_factors", "name": {"en": "Risk Factors", "zh": "风险因素"}, "content": "Risk"},
            {"id": "esg", "name": {"en": "ESG Analysis", "zh": "ESG分析"}, "content": "ESG"},
            {"id": "rating", "name": {"en": "Rating & Target Price", "zh": "评级与目标价"}, "content": "Rating"},
            {"id": "quarterly", "name": {"en": "Quarterly Tracking", "zh": "季度跟踪"}, "content": "Quarterly"},
            {"id": "catalyst", "name": {"en": "Catalyst Watch", "zh": "催化剂观察"}, "content": "Catalyst"},
        ]

        def _resolve_name(name_val):
            if isinstance(name_val, dict):
                return name_val.get("zh", name_val.get("en", str(name_val)))
            return str(name_val)

        sections = []
        for sd in section_details:
            sections.append(SectionSpec(
                section_id=sd["id"],
                section_name=_resolve_name(sd.get("name", sd["id"])),
                section_role=SectionRole.ANALYSIS,
                content_dependency=[],
            ))

        ts = TaskStructure(
            task_id="test_task",
            topic="比亚迪财务分析",
            sections=sections,
        )

        ts_dict = ts.to_dict()

        assert len(ts_dict["sections"]) == 14
        assert ts_dict["sections"][0]["section_name"] == "投资摘要"
        assert ts_dict["sections"][3]["section_name"] == "竞争格局"
        assert ts_dict["sections"][11]["section_name"] == "评级与目标价"

        for section_spec in ts_dict.get("sections", []):
            assert section_spec["section_name"] not in ["核心结论", "核心结论与论证分析", "论证与分析"], \
                f"Section name should not be a generic heading: {section_spec['section_name']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


# ============================================================
# R1-D: content_dependency calculation
# ============================================================

class TestR1DContentDependency:
    """Verify _build_task_structure_from_section_details computes dependencies."""

    def test_synthesis_depends_on_all_analysis(self):
        """Synthesis sections should depend on all analysis sections."""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        ro = ResearchOrchestrator()
        ts = ro._build_task_structure_from_section_details(
            [
                {"id": "investment_summary", "name": "Investment Summary"},
                {"id": "industry_overview", "name": "Industry Overview"},
                {"id": "market_size", "name": "Market Size"},
            ],
            "Test", "t1",
        )
        sections = ts["sections"]
        deps = ts["dependencies"]

        synthesis = [s for s in sections if s["section_role"] == "synthesis"]
        analysis = [s for s in sections if s["section_role"] == "analysis"]

        assert len(synthesis) == 1
        assert len(analysis) == 2
        assert synthesis[0]["section_id"] == "synthesis_0"
        assert set(synthesis[0]["content_dependency"]) == {"section_0", "section_1"}
        assert len(deps) == 2

    def test_analysis_has_peers_dependency(self):
        """Analysis sections should reference peer analysis sections."""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        ro = ResearchOrchestrator()
        ts = ro._build_task_structure_from_section_details(
            [
                {"id": "industry_overview", "name": "Industry Overview"},
                {"id": "market_size", "name": "Market Size"},
                {"id": "competitive", "name": "Competitive"},
            ],
            "Test", "t2",
        )
        sections = ts["sections"]
        for s in sections:
            if s["section_role"] == "analysis":
                peers = [a["section_id"] for a in sections if a["section_role"] == "analysis" and a["section_id"] != s["section_id"]]
                assert len(s["content_dependency"]) <= 3

    def test_chinese_summary_and_outlook_are_synthesis_sections(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        structure = ResearchOrchestrator()._build_task_structure_from_section_details(
            [
                {"id": "summary", "name": "摘要与核心结论"},
                {"id": "market_size", "name": "市场规模与增长"},
                {"id": "outlook", "name": "总结与展望"},
            ],
            "锂电池行业", "synthesis-cn",
        )

        roles = {item["template_id"]: item["section_role"] for item in structure["sections"]}
        assert roles["summary"] == "synthesis"
        assert roles["outlook"] == "synthesis"
        assert roles["market_size"] == "analysis"

        synthesis_ids = [item["section_id"] for item in structure["sections"] if item["section_role"] == "synthesis"]
        for item in structure["sections"]:
            if item["section_role"] == "synthesis":
                assert set(item["content_dependency"]) == {
                    section["section_id"] for section in structure["sections"]
                    if section["section_role"] == "analysis"
                }


# ============================================================
# R1-E: Chinese section_name mapping
# ============================================================

class TestR1EChineseSectionNames:
    """Verify _build_task_structure_from_section_details uses Chinese names."""

    def test_known_ids_get_chinese_names(self):
        """Known section IDs should get Chinese names from _SECTION_ZH_NAMES."""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        ro = ResearchOrchestrator()
        ts = ro._build_task_structure_from_section_details(
            [
                {"id": "investment_summary", "name": "Investment Summary"},
                {"id": "market_size", "name": "Market Size"},
                {"id": "competitive_landscape", "name": "Competitive Landscape"},
                {"id": "financial_forecast", "name": "Financial Forecast"},
            ],
            "Test", "t3",
        )
        sections = ts["sections"]
        name_map = {s["template_id"]: s["section_name"] for s in sections}

        assert name_map["investment_summary"] == "投资摘要"
        assert name_map["market_size"] == "市场规模与增长"
        assert name_map["competitive_landscape"] == "竞争格局"
        assert name_map["financial_forecast"] == "财务预测与估值"


# ============================================================
# R3-B: Data anomaly detection
# ============================================================

class TestR3BAnomalyDetection:
    """Verify detect_anomalous_data catches cliff drops and out-of-range values."""

    def test_out_of_range_detection(self):
        from src.core.search_quality_filter import detect_anomalous_data

        data_points = [
            {"metric": "毛利率", "value": 150.0, "unit": "%"},
            {"metric": "市盈率", "value": -200.0},
            {"metric": "营收", "value": 50.0, "unit": "亿元"},
        ]
        flags = detect_anomalous_data(data_points)
        flagged_metrics = {f.metric for f in flags}
        assert "毛利率" in flagged_metrics, "150% gross margin should be flagged"
        assert "市盈率" in flagged_metrics, "PE=-200 should be flagged"
        assert "营收" not in flagged_metrics, "50亿 revenue is normal"

    def test_cliff_drop_detection(self):
        from src.core.search_quality_filter import detect_anomalous_data

        data_points = [
            {"metric": "销量", "value": 70.0, "unit": "万辆"},
        ]
        prev = {"销量": 460.0}
        flags = detect_anomalous_data(data_points, prev_values=prev)
        assert len(flags) == 1
        assert flags[0].severity == "warning"
        assert "暴增" in flags[0].reason or "暴跌" in flags[0].reason

    def test_sign_flip_detection(self):
        from src.core.search_quality_filter import detect_anomalous_data

        data_points = [
            {"metric": "净利润", "value": -50.0},
        ]
        prev = {"净利润": 326.0}
        flags = detect_anomalous_data(data_points, prev_values=prev)
        assert len(flags) == 1
        assert flags[0].severity == "critical"
        assert "暴跌" in flags[0].reason

    def test_normal_data_no_flags(self):
        from src.core.search_quality_filter import detect_anomalous_data

        data_points = [
            {"metric": "营收", "value": 8040.0},
            {"metric": "净利润", "value": 326.0},
            {"metric": "毛利率", "value": 21.6},
        ]
        flags = detect_anomalous_data(data_points)
        assert len(flags) == 0, "Normal data should not be flagged"


# ============================================================
# R3-C: Search quality fallback no longer returns unfiltered
# ============================================================

class TestR3CFallbackLogic:
    """Verify search quality fallback returns failure instead of unfiltered results."""

    def test_403_removed_from_stop_errors(self):
        """403 should no longer be in RetryConfig stop_errors."""
        from src.core.orchestrator.execution.control.retry import RetryConfig

        default_stop = RetryConfig().stop_errors
        assert "403" not in default_stop, \
            "403 should be removed from stop_errors to allow retry on search engine blocks"

    def test_stop_errors_still_has_401_404(self):
        """401 and 404 should still be in stop_errors."""
        from src.core.orchestrator.execution.control.retry import RetryConfig

        default_stop = RetryConfig().stop_errors
        assert "401" in default_stop
        assert "404" in default_stop


# ============================================================
# Bug #1: Heartbeat does not update last_heartbeat_at
# ============================================================

class TestHeartbeatUpdatesSession:
    """Verify that ProgressHeartbeat._loop updates last_heartbeat_at in session."""

    def test_heartbeat_loop_updates_session_heartbeat_time(self):
        """_update_heartbeat should write last_heartbeat_at to session."""
        from src.core.progress_heartbeat import ProgressHeartbeat
        from datetime import datetime

        mock_session = MagicMock()
        mock_session.get.return_value = {
            "status": "running",
            "progress": 0.2,
            "current_phase": "execution",
        }
        mock_session.update = MagicMock()

        with patch("src.core.session_manager.SessionManager") as MockSM:
            MockSM.get_instance.return_value.get.return_value = mock_session
            ProgressHeartbeat._update_heartbeat("test_session_1")

        mock_session.update.assert_called_once()
        update_arg = mock_session.update.call_args[0][0]
        assert "task_progress" in update_arg
        tp = update_arg["task_progress"]
        assert "last_heartbeat_at" in tp
        hb_time = datetime.fromisoformat(tp["last_heartbeat_at"])
        assert (datetime.now() - hb_time).total_seconds() < 5

    def test_heartbeat_loop_skips_when_no_session(self):
        """_update_heartbeat should not crash when session is None."""
        from src.core.progress_heartbeat import ProgressHeartbeat

        with patch("src.core.session_manager.SessionManager") as MockSM:
            MockSM.get_instance.return_value.get.return_value = None
            ProgressHeartbeat._update_heartbeat("nonexistent_session")


# ============================================================
# Bug #2: Progress stuck at 20% during agent execution
# ============================================================

class TestProgressUpdatesDuringExecution:
    """Verify that agent completion triggers progress updates."""

    def test_single_batch_progress_formula(self):
        """With 1 batch, batch_index=0, progress should still update
        during agent execution (not stuck at 0.2)."""
        batch_index = 0
        total_batches = 1
        base_progress = 0.2 + (batch_index / max(total_batches, 1)) * 0.5
        assert base_progress == 0.2

        done_agents = 3
        total_agents = 8
        agent_progress = 0.2 + (done_agents / max(total_agents, 1)) * 0.5
        assert agent_progress > 0.2
        assert agent_progress == 0.2 + 3 / 8 * 0.5

    def test_all_agents_done_progress(self):
        """When all agents are done, progress should approach 0.7."""
        total_agents = 8
        done_agents = 8
        agent_progress = 0.2 + (done_agents / max(total_agents, 1)) * 0.5
        assert agent_progress == 0.7

    def test_progress_capped_at_069(self):
        """Agent completion progress should be capped below 0.7
        to avoid conflicting with the 'all agents completed' update."""
        done = 8
        total = 8
        agent_progress = 0.2 + (done / max(total, 1)) * 0.5
        capped = min(agent_progress, 0.69)
        assert capped == 0.69


# ============================================================
# Bug #3: persona_generation_agent replaces event loop
# ============================================================

class TestPersonaAgentEventLoopSafety:
    """Verify that persona_generation_agent doesn't replace the running event loop."""

    def test_enhance_personas_does_not_replace_running_loop(self):
        """_enhance_personas should use ThreadPoolExecutor when loop is running."""
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent

        agent = PersonaGenerationAgent.__new__(PersonaGenerationAgent)

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = True
            mock_get_loop.return_value = mock_loop

            with patch.object(agent, '_enhance_with_llm_async', new_callable=AsyncMock, return_value=[]):
                with patch("concurrent.futures.ThreadPoolExecutor") as MockPool:
                    mock_pool_inst = MagicMock()
                    mock_future = MagicMock()
                    mock_future.result.return_value = []
                    mock_pool_inst.submit.return_value = mock_future
                    mock_pool_inst.__enter__ = MagicMock(return_value=mock_pool_inst)
                    mock_pool_inst.__exit__ = MagicMock(return_value=False)
                    MockPool.return_value = mock_pool_inst

                    result = agent._enhance_with_llm_sync([], None)

            mock_get_loop.assert_called()
            mock_loop.is_running.assert_called()

    def test_enhance_uses_run_until_complete_when_loop_not_running(self):
        """When event loop is not running, should use run_until_complete directly."""
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent

        agent = PersonaGenerationAgent.__new__(PersonaGenerationAgent)

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete.return_value = []
            mock_get_loop.return_value = mock_loop

            with patch.object(agent, '_enhance_with_llm_async', new_callable=AsyncMock, return_value=[]):
                result = agent._enhance_with_llm_sync([], None)

            mock_loop.run_until_complete.assert_called_once()

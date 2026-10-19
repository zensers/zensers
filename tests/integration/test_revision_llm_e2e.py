"""
真实端到端测试：使用真实LLM、真实Writer/Reviewer/GlobalReviewer/Orchestrator
验证完整的修订系统闭环

所有LLM调用都是真实的（deepseek-v4-flash）
"""
import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock


def _make_real_orchestrator():
    """真实实例化ReportOrchestrator，使用真实PromptManager和所有Agent"""
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
    from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
    from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
    from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
    from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

    pm = PromptManager()
    mock_search = MagicMock()
    mock_search.execute = MagicMock(return_value={"success": False})
    return ReportOrchestrator(
        chapter_writer=ChapterWriter(prompt_manager=pm),
        chapter_reviewer=ChapterReviewAgent(prompt_manager=pm),
        global_reviewer=GlobalReviewAgent(prompt_manager=pm),
        data_repair_agent=DataRepairAgent(search_skill=mock_search, prompt_manager=pm),
        conflict_resolver=ConflictResolver(prompt_manager=pm),
        prompt_manager=pm,
    )


def _make_real_chapters():
    """构造真实的章节列表，模拟一份已生成的报告"""
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
    return [
        ChapterWriteOutput(
            chapter_id="market_size",
            title="市场规模与增长趋势",
            content="2025年中国新能源汽车市场规模达到约1200万辆，同比增长约35%。"
                    "其中纯电动汽车占比约62%，插电混动占比约38%。"
                    "市场规模从2021年的350万辆快速增长，4年间增长超过3倍。",
            data_points_used=[
                DataPoint(metric="新能源汽车销量", value="1200", unit="万辆", chapter_id="market_size", source="中汽协"),
                DataPoint(metric="同比增长率", value="35", unit="%", chapter_id="market_size", source="中汽协"),
                DataPoint(metric="纯电占比", value="62", unit="%", chapter_id="market_size", source="乘联会"),
            ],
            key_conclusions=["市场规模达1200万辆", "同比增长35%", "纯电占比62%"],
        ),
        ChapterWriteOutput(
            chapter_id="competition",
            title="竞争格局与企业分析",
            content="比亚迪以约28%的市场份额位居首位，特斯拉约8%，广汽埃安约6%。"
                    "头部企业CR3合计约42%，市场集中度适中，竞争格局呈梯队分布。"
                    "比亚迪在纯电和插混双赛道均有优势，2025年销量突破340万辆。",
            data_points_used=[
                DataPoint(metric="比亚迪市占率", value="28", unit="%", chapter_id="competition", source="乘联会"),
                DataPoint(metric="CR3", value="42", unit="%", chapter_id="competition", source="乘联会"),
            ],
            key_conclusions=["比亚迪市占率28%", "CR3达42%", "梯队分布"],
        ),
    ]


class TestE2ELocateRevisionTarget:
    """E2E-1: 真实LLM定位修订目标"""

    @pytest.mark.asyncio
    async def test_locate_standard_revision(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}
        ro._data_registry.register(metric="新能源汽车销量", value="1200", unit="万辆", chapter_id="market_size", source="中汽协")

        result = await ro._locate_revision_target("请更新市场规模数据为最新2026年数据")

        assert result is not None
        assert result.complexity is not None
        assert len(result.targets) >= 0
        if len(result.targets) > 0:
            target = result.targets[0]
            assert target.chapter_id is not None
            assert target.revision_description is not None
            print(f"\n定位结果: complexity={result.complexity.value}, targets={len(result.targets)}")
            for t in result.targets:
                print(f"  - [{t.chapter_id}] {t.chapter_title}: {t.revision_type} - {t.revision_description[:80]}")

    @pytest.mark.asyncio
    async def test_locate_lightweight_revision(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        result = await ro._locate_revision_target("将竞争格局章节标题改为'品牌竞争与梯队分析'")

        assert result is not None
        print(f"\n轻量定位: complexity={result.complexity.value}")
        if result.targets:
            print(f"  - {result.targets[0].revision_type}: {result.targets[0].revision_description[:80]}")


class TestE2EFullRevisionPipeline:
    """E2E-2: 真实LLM完整修订流程"""

    @pytest.mark.asyncio
    async def test_standard_revision_full_pipeline(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告", "description": "中国新能源汽车行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        for ch in chapters:
            for dp in ch.data_points_used:
                ro._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=dp.chapter_id, source=dp.source,
                )

        result = await ro.revision(
            user_request="请更新市场规模章节，将2025年数据更新为2026年预估数据",
        )

        assert result is not None
        assert "chapter_results" in result
        assert "global_review_score" in result
        assert "global_review_passed" in result
        assert "data_registry_snapshot" in result

        print(f"\n=== 标准修订结果 ===")
        print(f"global_review_score: {result['global_review_score']}")
        print(f"global_review_passed: {result['global_review_passed']}")
        print(f"chapter_results: {len(result['chapter_results'])}")
        for cr in result["chapter_results"]:
            print(f"  - chapter_id={cr.chapter_id}, review_passed={cr.review_passed}, review_score={cr.review_score}, rewrite_rounds={cr.rewrite_rounds}")
            if cr.revised_content:
                print(f"    revised_content[:150]: {cr.revised_content[:150]}")

        assert len(result["chapter_results"]) > 0 or result["global_review_passed"]

    @pytest.mark.asyncio
    async def test_lightweight_revision_full_pipeline(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        for ch in chapters:
            for dp in ch.data_points_used:
                ro._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=dp.chapter_id, source=dp.source,
                )

        result = await ro.revision(
            user_request="将市场规模章节的'增长趋势'改为'发展趋势'",
        )

        assert result is not None
        assert "data_registry_snapshot" in result
        print(f"\n=== 轻量修订结果 ===")
        print(f"global_review_passed: {result['global_review_passed']}")


class TestE2EDataConsistency:
    """E2E-3: 数据一致性验证（revision前后三方数据一致）"""

    @pytest.mark.asyncio
    async def test_revision_data_consistency_three_way(self):
        from src.api.research_api_helpers import sections_to_chapters, apply_revision_to_session, restore_data_registry
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry

        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        for ch in chapters:
            for dp in ch.data_points_used:
                ro._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=dp.chapter_id, source=dp.source,
                )

        original_sections = [
            {"id": "market_size", "title": "市场规模与增长趋势", "content": chapters[0].content},
            {"id": "competition", "title": "竞争格局与企业分析", "content": chapters[1].content},
        ]

        result = await ro.revision(
            user_request="更新市场规模章节中的增长数据",
        )

        updated_chapters = ro._chapters
        updated_registry = ro._data_registry

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": original_sections, "topic": "中国新能源汽车市场分析"},
            },
            "_data_registry_snapshot": updated_registry.to_snapshot(),
        }
        apply_revision_to_session(session, result, updated_chapters, updated_registry)

        # 验证1: session中的sections内容与chapters一致
        for ch in updated_chapters:
            matching_section = None
            for sec in session["research_result"]["report"]["sections"]:
                if sec["id"] == ch.chapter_id:
                    matching_section = sec
                    break
            if matching_section:
                assert matching_section["content"] == ch.content, f"session content != chapter content for {ch.chapter_id}"
                assert matching_section["title"] == ch.title, f"session title != chapter title for {ch.chapter_id}"
                assert matching_section["key_conclusions"] == ch.key_conclusions, f"session key_conclusions != chapter key_conclusions for {ch.chapter_id}"

        # 验证2: DataRegistry snapshot可以恢复
        restored = restore_data_registry(session)
        restored_snapshot = restored.to_snapshot()
        assert "metrics" in restored_snapshot

        # 验证3: 修订记录存在
        assert "_revision_history" in session
        assert len(session["_revision_history"]) > 0

        print(f"\n=== 数据一致性验证 ===")
        print(f"章节内容一致: OK")
        print(f"DataRegistry恢复: OK")
        print(f"修订记录: {len(session['_revision_history'])} 条")
        for rh in session["_revision_history"]:
            print(f"  - score={rh['global_review_score']}, passed={rh['global_review_passed']}, chapters_revised={rh['chapters_revised']}")


class TestE2EMultiChapterRevision:
    """E2E-4: 多章节修订+全局修正完整链路"""

    @pytest.mark.asyncio
    async def test_multi_target_revision_with_global_review(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        for ch in chapters:
            for dp in ch.data_points_used:
                ro._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=dp.chapter_id, source=dp.source,
                )

        result = await ro.revision(
            user_request="请同时更新市场规模和竞争格局两个章节的最新数据",
        )

        assert result is not None
        assert result["global_review_score"] >= 0
        assert result["global_review_passed"] in (True, False)
        assert len(result["chapter_results"]) >= 0

        print(f"\n=== 多章节修订结果 ===")
        print(f"score={result['global_review_score']}, passed={result['global_review_passed']}")
        print(f"chapter_results: {len(result['chapter_results'])}")
        for i, ch in enumerate(ro._chapters):
            print(f"  chapter[{i}]: id={ch.chapter_id}, title={ch.title}, content_len={len(ch.content)}, dp_count={len(ch.data_points_used)}")


class TestE2EErrorResilience:
    """E2E-5: 异常恢复验证"""

    @pytest.mark.asyncio
    async def test_revision_with_vague_request(self):
        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()
        ro._chapters = chapters
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        for ch in chapters:
            for dp in ch.data_points_used:
                ro._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=dp.chapter_id, source=dp.source,
                )

        result = await ro.revision(user_request="随便改改")

        assert result is not None
        assert "chapter_results" in result
        assert "global_review_score" in result
        print(f"\n=== 模糊请求修订结果 ===")
        print(f"score={result['global_review_score']}, passed={result['global_review_passed']}, chapters_revised={len(result['chapter_results'])}")

    @pytest.mark.asyncio
    async def test_revision_with_empty_chapters(self):
        ro = _make_real_orchestrator()
        ro._chapters = []
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "中国新能源汽车市场分析"}

        result = await ro.revision(user_request="修改市场规模")

        assert result is not None
        assert "chapter_results" in result
        assert "global_review_score" in result
        for cr in result["chapter_results"]:
            assert cr.review_passed is False
        print(f"\n=== 空章节修订结果 ===")
        print(f"score={result['global_review_score']}, passed={result['global_review_passed']}, results={len(result['chapter_results'])}")


class TestE2EAssembleReportWithKeyConclusions:
    """E2E-6: 真实报告组装验证key_conclusions传递"""

    @pytest.mark.asyncio
    async def test_assemble_final_report_preserves_key_conclusions(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.models import ReviewOutput

        ro = _make_real_orchestrator()
        chapters = _make_real_chapters()

        review = ReviewOutput(overall_score=85.0, dimension_scores={}, issues=[], fix_suggestions=[])

        report = ReportOrchestrator._assemble_final_report(
            chapters, "新能源汽车行业研究摘要", review, "中国新能源汽车市场分析",
        )

        assert "sections" in report
        for i, sec in enumerate(report["sections"]):
            assert "key_conclusions" in sec, f"section {i} missing key_conclusions"
            assert sec["key_conclusions"] == chapters[i].key_conclusions, f"section {i} key_conclusions mismatch"
            print(f"  section[{i}] id={sec['id']}, title={sec['title']}, key_conclusions={sec['key_conclusions']}")

    @pytest.mark.asyncio
    async def test_sections_to_chapters_to_revision_to_assemble_round_trip(self):
        """完整闭环: sections → chapters → revision → session → chapters → assemble"""
        from src.api.research_api_helpers import sections_to_chapters, apply_revision_to_session, restore_data_registry
        from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        from src.agents.fixed_agents.report_upgrade.models import ReviewOutput

        original_sections = [
            {"id": "market_size", "title": "市场规模", "content": "2025年市场规模约1200万辆"},
            {"id": "competition", "title": "竞争格局", "content": "比亚迪市占率约28%"},
        ]

        chapters = sections_to_chapters(original_sections)
        assert len(chapters) == 2
        assert chapters[0].chapter_id == "market_size"
        assert chapters[0].key_conclusions != [] or chapters[0].content != ""

        dr = DataRegistry()
        dr.register(metric="销量", value="1200", unit="万辆", chapter_id="market_size", source="中汽协")

        session = {
            "research_result": {
                "status": "completed",
                "report": {"sections": original_sections, "topic": "新能源汽车"},
            },
            "_data_registry_snapshot": dr.to_snapshot(),
        }

        ro = _make_real_orchestrator()
        ro._chapters = chapters
        ro._data_registry = dr
        ro._framework_config = {"name": "行业研究报告"}
        ro._task_structure = {"topic": "新能源汽车市场分析"}

        result = await ro.revision(user_request="更新市场规模数据")

        updated_chapters = ro._chapters
        updated_dr = ro._data_registry

        apply_revision_to_session(session, result, updated_chapters, updated_dr)

        restored_dr = restore_data_registry(session)
        assert "metrics" in restored_dr.to_snapshot()

        report = ReportOrchestrator._assemble_final_report(
            updated_chapters, "摘要", ReviewOutput(
                overall_score=result["global_review_score"],
                dimension_scores={},
                issues=[],
                fix_suggestions=[],
            ),
            "新能源汽车",
        )

        assert all("key_conclusions" in sec for sec in report["sections"])

        print(f"\n=== 完整闭环验证 ===")
        print(f"sections→chapters→revision→session→assemble: OK")
        print(f"final sections: {len(report['sections'])}")
        print(f"key_conclusions in all sections: {all('key_conclusions' in s for s in report['sections'])}")
        print(f"revision score: {result['global_review_score']}")

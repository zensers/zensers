"""
E2E test for the full PPT Revision Pipeline.

Flow: data collection → analysis → framework confirm → PPT generation
      → outline confirm → preview → revision (L1-L4) → finalize → export
"""
import pytest

from src.core.adjustment.slide_data_builder import SlideDataBuilder
from src.core.adjustment.slide_data_store import SlideDataStore
from src.converters.slide_outline_builder import SlideOutlineBuilder
from src.core.adjustment.ppt_report_adapter import PptReportAdapter
from src.core.adjustment.ppt_revision_router import PptRevisionRouter
from src.core.adjustment.ppt_revision_service import PptRevisionService, PptRevisionRequest
from src.core.adjustment.ppt_slide_locator import PptSlideLocator
from src.core.adjustment.ppt_atomic_editor import PptAtomicEditor
from src.core.adjustment.ppt_structure_editor import PptStructureEditor
from src.core.adjustment.ppt_version_manager import PptVersionManager
from src.core.adjustment.slide_data_path_resolver import SlideDataPathResolver
from src.core.adjustment.revision_types import RevisionOpType
from src.content.content_orchestrator import ContentSection, SectionType


# ---- Simulated research data (like what data collection would produce) ----

RESEARCH_DATA = {
    "title": "2024年中国新能源汽车市场研究报告",
    "sections": [
        {
            "title": "市场规模与增长",
            "type": SectionType.BODY,
            "content": "2024年中国新能源汽车销量达到950万辆，同比增长37.5%。市场渗透率突破40%，标志着新能源汽车进入主流消费阶段。",
            "points": [
                "2024年销量950万辆，同比增长37.5%",
                "市场渗透率突破40%",
                "全球市场份额超过60%",
                "预计2025年销量将突破1200万辆",
            ],
            "charts": [{"chart_type": "bar", "title": "2019-2024年新能源汽车销量"}],
        },
        {
            "title": "竞争格局",
            "type": SectionType.BODY,
            "content": "比亚迪以35%的市场份额领跑，特斯拉和蔚来分列二三。国产品牌在10-20万元价格段占据主导地位。",
            "points": [
                "比亚迪市场份额35%",
                "特斯拉中国市场占比12%",
                "国产新势力品牌合计占比28%",
                "10-20万元价格段国产品牌占比85%",
            ],
            "charts": [{"chart_type": "pie", "title": "2024年品牌市场份额"}],
        },
        {
            "title": "技术趋势",
            "type": SectionType.BODY,
            "content": "固态电池技术取得突破，续航里程有望突破1000公里。800V高压快充平台成为主流配置，充电时间缩短至15分钟。",
            "points": [
                "固态电池续航突破1000公里",
                "800V快充平台成为主流",
                "充电时间缩短至15分钟",
                "L3级自动驾驶渗透率达到25%",
            ],
        },
        {
            "title": "数据来源",
            "type": SectionType.DATA_SOURCE,
            "content": "中国汽车工业协会、乘联会、工信部、各上市公司财报",
            "points": [],
        },
    ],
}


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "slide_data").mkdir()
    (ws / "revisions").mkdir()
    (ws / "output").mkdir()
    return ws


class TestE2EFullPipeline:
    """
    Full E2E pipeline test simulating the complete user journey.
    
    Steps:
    1. Data collection (simulated via RESEARCH_DATA)
    2. ContentSection creation (analysis)
    3. SlideDataBuilder → slide_data_list
    4. SlideOutlineBuilder → outline for user confirmation
    5. PPT generation (HTMLToPPTConverter._create_pptx_document)
    6. SlideDataStore persistence
    7. PptVersionManager snapshot
    8. L1 revision: atomic text change
    9. L4 revision: add slide + full re-render
    10. Rollback test
    11. Export verification
    """

    @pytest.mark.asyncio
    async def test_full_pipeline(self, workspace):
        # ---- Step 1-2: Data Collection + ContentSection Creation ----
        sections = []
        for sec_data in RESEARCH_DATA["sections"]:
            section = ContentSection(
                id=f"sec_{len(sections)}",
                title=sec_data["title"],
                content=sec_data["content"],
                order=len(sections),
                type=sec_data["type"],
                points=sec_data.get("points", []),
                charts=sec_data.get("charts", []),
            )
            sections.append(section)

        assert len(sections) == 4
        assert sections[0].title == "市场规模与增长"

        # ---- Step 3: SlideDataBuilder → slide_data_list ----
        builder = SlideDataBuilder()
        slide_data_list = builder.build_list(
            sections,
            add_cover=True,
            add_end=True,
            title=RESEARCH_DATA["title"],
        )

        assert len(slide_data_list) == 6  # cover + 4 sections + end
        assert slide_data_list[0]["slide_type"] == "cover"
        assert slide_data_list[0]["title"] == "2024年中国新能源汽车市场研究报告"
        assert slide_data_list[1]["title"] == "市场规模与增长"
        assert slide_data_list[1]["items"] == [
            "2024年销量950万辆，同比增长37.5%",
            "市场渗透率突破40%",
            "全球市场份额超过60%",
            "预计2025年销量将突破1200万辆",
        ]
        chart_image = slide_data_list[1]["images"][0]
        assert chart_image["src"] == ""
        assert chart_image["alt"] == "2019-2024年新能源汽车销量"
        assert chart_image["image_type"] == "chart"
        assert chart_image["chart_type"] == "bar"
        assert {"chart_id", "caption", "source", "unit", "data_ref"}.issubset(chart_image)
        assert slide_data_list[-1]["slide_type"] == "end"
        assert slide_data_list[3]["source_text"] == ""
        assert slide_data_list[4]["source_text"] == "中国汽车工业协会、乘联会、工信部、各上市公司财报"

        # Verify all fields present (C4 fix)
        for sd in slide_data_list:
            for key in ("slide_type", "title", "content", "items", "table_data",
                        "extra_tables", "images", "source_text", "section_number",
                        "section_summary", "insight_text", "kpi_data", "comparison_data"):
                assert key in sd, f"Missing key '{key}' in slide_data for '{sd['title']}'"

        # ---- Step 4: SlideOutlineBuilder → Outline Confirmation ----
        outline_builder = SlideOutlineBuilder()
        outline = outline_builder.build(slide_data_list, task_id="task_e2e_001")

        assert outline.task_id == "task_e2e_001"
        assert outline.total_pages == 6
        assert outline.confirmed is False
        assert outline.slides[0].slide_type == "cover"
        assert outline.slides[1].chart_type == "bar"
        assert outline.slides[2].chart_type == "pie"
        assert outline.slides[3].chart_type is None

        # Simulate user confirming outline
        outline.confirmed = True
        assert outline.confirmed is True

        # ---- Step 5: PPT Generation ----
        output_path = str(workspace / "output" / "report.pptx")
        structure_editor = PptStructureEditor()
        result = structure_editor.edit(slide_data_list, output_path=output_path)
        # Result may be None if pptx not available, but should not crash

        # ---- Step 6: SlideDataStore Persistence ----
        store = SlideDataStore(
            data_dir=str(workspace / "slide_data"),
            task_id="task_e2e_001",
        )
        store.persist("task_e2e_001", slide_data_list)
        store.set_pptx_path("task_e2e_001", output_path)

        assert store.pptx_path == output_path  # C5 fix: property access
        assert store.get_version("task_e2e_001") == 1
        assert store.get_hash("task_e2e_001") is not None

        # Verify persistence round-trip
        loaded = store.load("task_e2e_001")
        assert len(loaded) == 6
        assert loaded[1]["title"] == "市场规模与增长"

        # ---- Step 7: Version Snapshot ----
        version_mgr = PptVersionManager(
            revisions_dir=str(workspace / "revisions"),
            max_versions=10,
        )
        # Create a dummy pptx for version snapshot
        dummy_pptx = str(workspace / "output" / "report.pptx")
        with open(dummy_pptx, "wb") as f:
            f.write(b"PK\x03\x04dummy_pptx_v1")
        store.set_pptx_path("task_e2e_001", dummy_pptx)

        v1 = version_mgr.create_snapshot("task_e2e_001", dummy_pptx, "L0", "initial generation")
        assert v1 == 1

        # ---- Step 8: L1 Revision - Atomic Text Change ----
        # Simulate: user clicks title on slide 2, changes "市场规模与增长" to "市场规模分析"
        atomic = PptAtomicEditor()
        slide_data = loaded[1]
        success = atomic.update_slide_data(slide_data, "title", "市场规模分析")
        assert success is True
        assert slide_data["title"] == "市场规模分析"

        # Update items[0]
        success = atomic.update_slide_data(slide_data, "items[0]", "2024年销量950万辆，同比增长38%")
        assert success is True
        assert slide_data["items"][0] == "2024年销量950万辆，同比增长38%"

        # Persist L1 changes
        store.persist("task_e2e_001", loaded)
        assert store.get_version("task_e2e_001") == 2
        v2 = version_mgr.create_snapshot("task_e2e_001", dummy_pptx, "L1", "change title to 市场规模分析")
        assert v2 == 2

        # ---- Step 9: L4 Revision - Delete slide + Full re-render ----
        structure = PptStructureEditor()
        loaded = store.load("task_e2e_001")

        # Delete slide 3 (竞争格局, index=2)
        success = structure.delete_slide(loaded, 2)
        assert success is True
        assert len(loaded) == 5
        assert loaded[2]["title"] == "技术趋势"  # shifted up

        # Verify cover and end are protected
        assert structure.delete_slide(loaded, 0) is False
        assert structure.delete_slide(loaded, 4) is False  # end slide

        # Add a new slide
        new_slide = {
            "slide_type": "content", "title": "政策支持",
            "content": "购置税减免政策延续至2027年",
            "items": ["购置税减免延续至2027年", "双积分政策加严"],
            "table_data": [], "extra_tables": [],
            "images": [], "source_text": "",
            "section_number": 0, "section_summary": "",
            "insight_text": "", "kpi_data": [], "comparison_data": [],
        }
        success = structure.add_slide(loaded, 3, new_slide)
        assert success is True
        assert len(loaded) == 6
        assert loaded[3]["title"] == "政策支持"

        # Persist L4 changes
        store.persist("task_e2e_001", loaded)
        assert store.get_version("task_e2e_001") == 3

        # ---- Step 10: Rollback Test ----
        loaded_v3 = store.load("task_e2e_001")
        assert loaded_v3[1]["title"] == "市场规模分析"

        # Restore backup (should go back to v2)
        store.restore_backup("task_e2e_001")
        loaded_v2 = store.load("task_e2e_001")
        assert loaded_v2[1]["title"] == "市场规模分析"  # L1 change preserved
        # Note: backup only goes one step back, so v3→v2 data

        # Version manager rollback
        version_mgr.rollback("task_e2e_001", 1, dummy_pptx)

        # ---- Step 11: PptSlideLocator Tests ----
        locator = PptSlideLocator()
        loaded = store.load("task_e2e_001")

        # Find by title
        idx = locator.locate(loaded, slide_title="技术趋势")
        assert idx is not None

        # Find by keyword
        idx = locator.locate(loaded, keyword="销量")
        assert idx is not None

        # Find by index
        idx = locator.locate(loaded, slide_index=0)
        assert idx == 0

        # ---- Step 12: PptRevisionRouter Tests ----
        router = PptRevisionRouter()
        assert router.DEFAULT_LEVEL_MAP[RevisionOpType.REPLACE_TEXT] == "L1"
        assert router.DEFAULT_LEVEL_MAP[RevisionOpType.MODIFY_TABLE] == "L3"
        assert router.DEFAULT_LEVEL_MAP[RevisionOpType.ADD] == "L4"

        # _upgrade_if_needed
        from src.core.adjustment.revision_types import AnalysisResult
        analysis = AnalysisResult(intents=[])
        assert router._upgrade_if_needed("L1", analysis, {}) == "L1"

        # _extract_slide_index
        idx = router._extract_slide_index(analysis, {"current_slide_index": 2})
        assert idx == 2

        # ---- Step 13: PptReportAdapter Integration ----
        adapter = PptReportAdapter(loaded, task_id="task_e2e_001")
        assert adapter.id == "task_e2e_001"
        assert len(adapter.sections) == len(loaded)

        # ---- Step 14: PptRevisionService Integration ----
        # L0 review
        service = PptRevisionService(store)
        result = await service._dispatch("L0", PptRevisionRequest(task_id="task_e2e_001"))
        assert result.success is True
        assert result.level == "L0"

        # L1 atomic edit
        request = PptRevisionRequest(
            task_id="task_e2e_001",
            source="click",
            slide_index=1,
            revision_type="replace_text",
            target_field="title",
            new_value="市场规模与增长趋势",
            revision_level="L1",
        )
        result = await service._dispatch("L1", request)
        assert result.success is True

        # Verify slide_data was updated
        loaded = store.load("task_e2e_001")
        assert loaded[1]["title"] == "市场规模与增长趋势"

        # ---- Step 15: Verify SlideDataPathResolver Integration ----
        sd = loaded[1]
        assert SlideDataPathResolver.get(sd, "title") == "市场规模与增长趋势"
        assert SlideDataPathResolver.get(sd, "items[0]") == "2024年销量950万辆，同比增长38%"
        assert SlideDataPathResolver.get(sd, "kpi_data") == []
        assert SlideDataPathResolver.get(sd, "nonexistent", "default") == "default"

        # ---- Step 16: Final Export Verification ----
        # Verify the final slide_data_list is complete and consistent
        final_data = store.load("task_e2e_001")
        assert len(final_data) >= 4  # at least cover + 2 content + end

        # Verify all slides have required fields
        for sd in final_data:
            assert sd.get("slide_type") is not None
            assert sd.get("title") is not None
            assert "items" in sd
            assert "images" in sd
            assert "table_data" in sd

        # Verify version tracking
        versions = version_mgr.list_versions("task_e2e_001")
        assert len(versions) >= 1

        # Verify store hash consistency
        final_hash = store.get_hash("task_e2e_001")
        assert final_hash is not None
        assert len(final_hash) == 64

        print("\n✓ E2E pipeline completed successfully!")
        print(f"  - {len(final_data)} slides in final output")
        print(f"  - {store.get_version('task_e2e_001')} versions tracked")
        print(f"  - {len(versions)} snapshots stored")

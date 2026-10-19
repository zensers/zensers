import pytest
from src.core.adjustment.ppt_data_supplementer import DataGap, PptDataSupplementer
from src.core.adjustment.extraction_types import ExtractionResult
from src.core.adjustment.ppt_requirement_extractor import PptRequirement
from src.content.content_orchestrator import ContentSection, SectionType
from src.core.search import SearchGateway, SearchRequest


def _make_extraction(title="Report", sections=None, key_topics=None):
    return ExtractionResult(
        title=title,
        sections=sections or [],
        tables=[],
        key_topics=key_topics or [],
        metadata={},
        summary=None,
    )


def _make_requirement(topic="Market", focus=None):
    return PptRequirement(
        topic=topic,
        focus=focus or ["market size", "competition"],
    )


class TestDataGap:
    def test_create_with_defaults(self):
        gap = DataGap(topic="Market Size", priority="critical", search_queries=["market size data"])
        assert gap.topic == "Market Size"
        assert gap.priority == "critical"
        assert gap.search_queries == ["market size data"]
        assert gap.search_results == []
        assert gap.filled is False

    def test_create_filled(self):
        gap = DataGap(
            topic="Revenue", priority="optional",
            search_queries=["revenue data"],
            search_results=["Revenue is $10B"],
            filled=True,
        )
        assert gap.filled is True


class TestPptDataSupplementerAnalyzeGaps:
    def test_identifies_missing_focus_areas(self):
        extraction = _make_extraction(key_topics=["market size"])
        requirement = _make_requirement(focus=["market size", "competition", "technology"])
        supplementer = PptDataSupplementer()
        gaps = supplementer.analyze_gaps(extraction, requirement)
        gap_topics = [g.topic for g in gaps]
        assert "competition" in gap_topics
        assert "technology" in gap_topics
        assert "market size" not in gap_topics

    def test_no_gaps_when_all_covered(self):
        extraction = _make_extraction(key_topics=["market size", "competition"])
        requirement = _make_requirement(focus=["market size", "competition"])
        supplementer = PptDataSupplementer()
        gaps = supplementer.analyze_gaps(extraction, requirement)
        assert gaps == []

    def test_gaps_have_search_queries(self):
        extraction = _make_extraction(key_topics=[])
        requirement = _make_requirement(focus=["market size"])
        supplementer = PptDataSupplementer()
        gaps = supplementer.analyze_gaps(extraction, requirement)
        assert len(gaps) == 1
        assert len(gaps[0].search_queries) > 0


class TestPptDataSupplementerSupplement:
    @pytest.mark.anyio
    async def test_supplement_async_uses_gateway_and_preserves_structured_results(self):
        class Provider:
            async def search(self, request: SearchRequest):
                return {"results": [{
                    "title": "来源",
                    "url": "https://source.example/ppt",
                    "snippet": "补充数据",
                    "source": "official",
                    "quality_score": 90,
                }]}

        gateway = SearchGateway(
            task_id="ppt-task",
            providers={"fake": Provider()},
            primary_provider="fake",
            task_max_searches=1,
            default_scope_max_searches=1,
            quality_threshold=70,
        )
        gaps = [DataGap("Market Size", "critical", ["market size"])]

        result = await PptDataSupplementer().supplement_async(gaps, gateway=gateway)

        assert result[0].filled is True
        assert result[0].search_results[0]["url"] == "https://source.example/ppt"
        assert gateway.get_stats()["scope_used_searches"] == {"ppt_supplement": 1}

    def test_supplement_fills_gaps_with_search_skill(self):
        gaps = [
            DataGap(topic="Market Size", priority="critical",
                    search_queries=["market size 2024"]),
        ]
        mock_skill = _MockSearchSkill(results={"market size 2024": "Market is $10B"})
        supplementer = PptDataSupplementer()
        result = supplementer.supplement(gaps, search_skill=mock_skill)
        assert result[0].filled is True
        assert len(result[0].search_results) > 0

    def test_supplement_skips_already_filled(self):
        gaps = [
            DataGap(topic="Market Size", priority="critical",
                    search_queries=["market size"], search_results=["data"],
                    filled=True),
        ]
        supplementer = PptDataSupplementer()
        result = supplementer.supplement(gaps, search_skill=None)
        assert result[0].filled is True
        assert len(result[0].search_results) == 1

    def test_supplement_without_search_skill(self):
        gaps = [
            DataGap(topic="Market Size", priority="critical",
                    search_queries=["market size"]),
        ]
        supplementer = PptDataSupplementer()
        result = supplementer.supplement(gaps, search_skill=None)
        assert result[0].filled is False


class _MockSearchSkill:
    def __init__(self, results):
        self._results = results

    def execute(self, **kwargs):
        query = kwargs.get("query", "")
        if query in self._results:
            return {"success": True, "data": {"results": [self._results[query]]}}
        return {"success": False, "data": {"results": []}}

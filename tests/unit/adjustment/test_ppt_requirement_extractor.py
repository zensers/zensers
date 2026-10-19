import pytest
from src.core.adjustment.ppt_requirement_extractor import PptRequirement, PptRequirementExtractor
from src.core.adjustment.extraction_types import ExtractionResult
from src.content.content_orchestrator import ContentSection, SectionType


def _make_extraction(title="Test Report", sections=None, key_topics=None):
    return ExtractionResult(
        title=title,
        sections=sections or [],
        tables=[],
        key_topics=key_topics or [],
        metadata={},
        summary=None,
    )


class TestPptRequirement:
    def test_create_with_defaults(self):
        req = PptRequirement(topic="Market Analysis")
        assert req.topic == "Market Analysis"
        assert req.audience == "business_professional"
        assert req.focus == []
        assert req.page_count is None
        assert req.style == "professional"
        assert req.confirmed is False

    def test_create_with_all_fields(self):
        req = PptRequirement(
            topic="AI Trends",
            audience="technical",
            focus=["LLM", "Agents"],
            page_count=15,
            style="modern",
            confirmed=True,
        )
        assert req.audience == "technical"
        assert req.page_count == 15
        assert req.confirmed is True


class TestPptRequirementExtractorFromData:
    def test_extracts_topic_from_title(self):
        extraction = _make_extraction(title="2024 Market Report")
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert req.topic == "2024 Market Report"

    def test_extracts_topic_from_key_topics_when_no_title(self):
        extraction = _make_extraction(title="", key_topics=["AI", "Cloud"])
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert req.topic == "AI"

    def test_default_topic_when_empty(self):
        extraction = _make_extraction(title="", key_topics=[])
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert req.topic == "未命名主题"

    def test_focus_from_key_topics_capped_at_5(self):
        extraction = _make_extraction(key_topics=["A", "B", "C", "D", "E", "F", "G"])
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert len(req.focus) == 5

    def test_page_count_from_sections(self):
        sections = [
            ContentSection(id=f"s{i}", title=f"Sec{i}", content="x", order=i, type=SectionType.BODY)
            for i in range(5)
        ]
        extraction = _make_extraction(sections=sections)
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert req.page_count == 10

    def test_page_count_minimum_3(self):
        extraction = _make_extraction(sections=[])
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction)
        assert req.page_count == 3


class TestPptRequirementExtractorFromDescription:
    def test_extracts_topic_from_description(self):
        extraction = _make_extraction(title="Report")
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction, user_description="做一个关于新能源汽车的PPT")
        assert "新能源" in req.topic

    def test_description_overrides_data_topic(self):
        extraction = _make_extraction(title="Old Title")
        extractor = PptRequirementExtractor()
        req = extractor.extract(extraction, user_description="做一个关于AI趋势的汇报PPT")
        assert "AI" in req.topic

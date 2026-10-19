import pytest
from src.core.adjustment.extraction_types import (
    ExtractionResult, ExtractionSummary, SectionSummary, DataParser,
)


class TestSectionSummary:
    def test_create_with_defaults(self):
        s = SectionSummary(title="Intro", page_range="1-3")
        assert s.title == "Intro"
        assert s.page_range == "1-3"
        assert s.content_preview == ""
        assert s.has_table is False
        assert s.has_chart is False

    def test_create_with_all_fields(self):
        s = SectionSummary(
            title="Market", page_range="4-10",
            content_preview="The market is growing...",
            has_table=True, has_chart=True,
        )
        assert s.has_table is True
        assert s.has_chart is True


class TestExtractionSummary:
    def test_create_with_defaults(self):
        es = ExtractionSummary(
            file_count=1, total_pages=10,
            format_types=["docx"], title="Report",
        )
        assert es.file_count == 1
        assert es.sections == []
        assert es.tables_count == 0
        assert es.charts_count == 0
        assert es.key_topics == []
        assert es.word_count == 0
        assert es.languages == []
        assert es.extraction_status == "success"
        assert es.warnings == []

    def test_create_with_all_fields(self):
        es = ExtractionSummary(
            file_count=2, total_pages=50,
            format_types=["docx", "pdf"], title="Annual Report",
            sections=[SectionSummary(title="Intro", page_range="1-5")],
            tables_count=3, charts_count=2,
            key_topics=["market", "revenue"], word_count=10000,
            languages=["zh", "en"],
            extraction_status="partial",
            warnings=["Table on page 12 could not be parsed"],
        )
        assert es.file_count == 2
        assert len(es.sections) == 1
        assert es.extraction_status == "partial"


class TestExtractionResult:
    def test_create_with_required_fields(self):
        er = ExtractionResult(
            title="Test Report",
            sections=[],
            tables=[],
            key_topics=[],
            metadata={},
            summary=None,
        )
        assert er.title == "Test Report"
        assert er.sections == []
        assert er.tables == []
        assert er.key_topics == []
        assert er.metadata == {}
        assert er.summary is None

    def test_create_with_all_fields(self):
        from src.content.content_orchestrator import ContentSection, SectionType
        section = ContentSection(
            id="sec_0", title="Overview", content="text",
            order=0, type=SectionType.BODY,
        )
        er = ExtractionResult(
            title="Report",
            sections=[section],
            tables=[[["A", "B"], ["1", "2"]]],
            key_topics=["market"],
            metadata={"format": "docx", "page_count": 10},
            summary=ExtractionSummary(
                file_count=1, total_pages=10,
                format_types=["docx"], title="Report",
            ),
        )
        assert len(er.sections) == 1
        assert len(er.tables) == 1
        assert er.metadata["format"] == "docx"
        assert er.summary is not None


class TestDataParserABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            DataParser()

    def test_subclass_must_implement_parse(self):
        class IncompleteParser(DataParser):
            pass

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_subclass_with_parse_works(self):
        class ConcreteParser(DataParser):
            def parse(self, file_path: str) -> ExtractionResult:
                return ExtractionResult(
                    title="", sections=[], tables=[],
                    key_topics=[], metadata={}, summary=None,
                )

        parser = ConcreteParser()
        result = parser.parse("test.docx")
        assert isinstance(result, ExtractionResult)

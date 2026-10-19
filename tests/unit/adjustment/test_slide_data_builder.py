import pytest
from src.core.adjustment.slide_data_builder import SlideDataBuilder
from src.content.content_orchestrator import ContentSection, SectionType


def _make_content_section(title="Market Size", content="The market is growing.",
                          section_type=SectionType.BODY, points=None, charts=None):
    return ContentSection(
        id="sec_1",
        title=title,
        content=content,
        order=1,
        type=section_type,
        points=points or ["TAM $10B", "CAGR 5%"],
        charts=charts or [],
    )


class TestBuildSlideData:
    def test_build_from_body_section(self):
        builder = SlideDataBuilder()
        section = _make_content_section()
        sd = builder.build(section)
        assert sd["slide_type"] == "content"
        assert sd["title"] == "Market Size"
        assert sd["content"] == "The market is growing."
        assert sd["items"] == ["TAM $10B", "CAGR 5%"]

    def test_build_from_exec_summary(self):
        builder = SlideDataBuilder()
        section = _make_content_section(
            title="Executive Summary",
            section_type=SectionType.EXECUTIVE_SUMMARY,
        )
        sd = builder.build(section)
        assert sd["slide_type"] == "content"

    def test_build_from_conclusion(self):
        builder = SlideDataBuilder()
        section = _make_content_section(
            title="Conclusion",
            section_type=SectionType.CONCLUSION,
        )
        sd = builder.build(section)
        assert sd["slide_type"] == "content"

    def test_build_from_data_source(self):
        builder = SlideDataBuilder()
        section = _make_content_section(
            title="Data Sources",
            content="National Bureau of Statistics",
            section_type=SectionType.DATA_SOURCE,
        )
        sd = builder.build(section)
        assert sd["source_text"] == "National Bureau of Statistics"

    def test_build_with_charts(self):
        builder = SlideDataBuilder()
        section = _make_content_section(
            charts=[{"chart_type": "bar", "title": "Revenue Chart"}],
        )
        sd = builder.build(section)
        assert len(sd.get("images", [])) == 1

    def test_build_with_empty_points(self):
        builder = SlideDataBuilder()
        section = ContentSection(
            id="sec_1", title="Test", content="text", order=1,
            type=SectionType.BODY, points=[], charts=[],
        )
        sd = builder.build(section)
        assert sd["items"] == []


class TestBuildSlideDataList:
    def test_build_list_from_sections(self):
        builder = SlideDataBuilder()
        sections = [
            _make_content_section(title="Overview", points=["point1"]),
            _make_content_section(title="Revenue", points=["point2"]),
        ]
        sdl = builder.build_list(sections)
        assert len(sdl) == 2
        assert sdl[0]["title"] == "Overview"
        assert sdl[1]["title"] == "Revenue"

    def test_build_list_with_cover_and_end(self):
        builder = SlideDataBuilder()
        sections = [_make_content_section()]
        sdl = builder.build_list(sections, add_cover=True, add_end=True)
        assert sdl[0]["slide_type"] == "cover"
        assert sdl[-1]["slide_type"] == "end"
        assert len(sdl) == 3

    def test_build_list_empty(self):
        builder = SlideDataBuilder()
        sdl = builder.build_list([])
        assert sdl == []

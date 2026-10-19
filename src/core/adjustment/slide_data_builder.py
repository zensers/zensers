from typing import Any, Dict, List

from src.content.content_orchestrator import ContentSection, SectionType


class SlideDataBuilder:

    def build_from_research_result(self, research_result: Dict[str, Any]) -> List[Dict]:
        """Project report sections into the canonical slide-data form.

        The projection is persisted alongside PPTX output so later revisions
        do not have to reverse-engineer slide content from binary XML.
        """
        from src.content.content_orchestrator import ContentOrchestrator

        sections = ContentOrchestrator()._parse_sections(
            research_result.get("sections", []) if isinstance(research_result, dict) else []
        )
        return self.build_list(
            sections,
            add_cover=True,
            add_end=True,
            title=(research_result or {}).get("title")
                   or (research_result or {}).get("topic")
                   or "Research Report",
        )

    def build(self, section: ContentSection,
              section_index: int = 0) -> Dict:
        sd: Dict[str, Any] = {
            "slide_type": self._map_type(section.type),
            "title": section.title,
            "content": section.content,
            "items": list(section.points) if section.points else [],
            "table_data": [],
            "extra_tables": [],
            "images": [],
            "source_text": "",
            "section_number": section_index,
            "section_summary": "",
            "insight_text": "",
            "kpi_data": [],
            "comparison_data": [],
        }
        if section.charts:
            sd["images"] = [
                {
                    "src": c.get("src", c.get("path", "")),
                    "alt": c.get("title", c.get("caption", c.get("chart_type", "Chart"))),
                    "image_type": "chart",
                    "chart_id": c.get("chart_id", ""),
                    "chart_type": c.get("chart_type", "chart"),
                    "caption": c.get("caption", ""),
                    "source": c.get("source", ""),
                    "unit": c.get("unit", ""),
                    "data_ref": c.get("data_ref", ""),
                }
                for c in section.charts
            ]
        if section.type == SectionType.DATA_SOURCE:
            sd["source_text"] = section.content
        return sd

    def build_list(self, sections: List[ContentSection],
                   add_cover: bool = False,
                   add_end: bool = False,
                   title: str = "Report Title") -> List[Dict]:
        result: List[Dict] = []
        if add_cover:
            result.append(self._make_cover(title))
        for i, section in enumerate(sections):
            result.append(self.build(section, section_index=i))
        if add_end:
            result.append(self._make_end())
        return result

    @staticmethod
    def _make_cover(title: str) -> Dict:
        return {
            "slide_type": "cover", "title": title, "content": "",
            "items": [], "table_data": [], "extra_tables": [],
            "images": [], "source_text": "", "section_number": 0,
            "section_summary": "", "insight_text": "",
            "kpi_data": [], "comparison_data": [],
        }

    @staticmethod
    def _make_end() -> Dict:
        return {
            "slide_type": "end", "title": "Thank You", "content": "",
            "items": [], "table_data": [], "extra_tables": [],
            "images": [], "source_text": "", "section_number": 0,
            "section_summary": "", "insight_text": "",
            "kpi_data": [], "comparison_data": [],
        }

    @staticmethod
    def _map_type(section_type: SectionType) -> str:
        mapping = {
            SectionType.EXECUTIVE_SUMMARY: "content",
            SectionType.CONCLUSION: "content",
            SectionType.APPENDIX: "content",
            SectionType.DATA_SOURCE: "content",
            SectionType.BODY: "content",
            SectionType.UNKNOWN: "content",
        }
        return mapping.get(section_type, "content")

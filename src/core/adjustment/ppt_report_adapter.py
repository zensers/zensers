from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ReportSection:
    id: str
    title: str
    content: str
    type: str


class PptReportAdapter:

    def __init__(self, slide_data_list: List[Dict], task_id: str):
        self.id = task_id
        self.sections = [
            ReportSection(
                id=f"slide_{i}",
                title=sd.get("title", "") or f"Slide {i+1}",
                content=self._build_content_text(sd),
                type=self._map_type(sd["slide_type"]),
            )
            for i, sd in enumerate(slide_data_list)
        ]

    def _build_content_text(self, sd: Dict) -> str:
        parts = []
        if sd.get("title"):
            parts.append(sd["title"])
        if sd.get("content"):
            parts.append(sd["content"])
        if sd.get("items"):
            parts.extend(sd["items"])
        if sd.get("table_data"):
            for row in sd.get("table_data", [])[:3]:
                parts.append(" | ".join(str(c) for c in row))
        return "\n".join(parts)

    def _map_type(self, slide_type: str) -> str:
        mapping = {
            "cover": "cover",
            "toc": "toc",
            "section_title": "section_title",
            "section-title": "section_title",
            "content": "content",
            "data": "data",
            "findings": "findings",
            "end": "end",
        }
        return mapping.get(slide_type, "content")

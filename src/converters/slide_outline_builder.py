from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SlideOutlineItem:
    page: int
    slide_type: str
    title: str
    data_summary: str
    chart_type: Optional[str]
    key_points: List[str]
    data_source: Optional[str]


@dataclass
class SlideOutline:
    task_id: str
    total_pages: int
    slides: List[SlideOutlineItem]
    confirmed: bool = False


class SlideOutlineBuilder:

    def build(self, slide_data_list: List[Dict], task_id: str = "") -> SlideOutline:
        items = []
        for i, sd in enumerate(slide_data_list):
            items.append(SlideOutlineItem(
                page=i + 1,
                slide_type=sd.get("slide_type", "content"),
                title=sd.get("title", ""),
                data_summary=self._summarize_data(sd),
                chart_type=self._detect_chart_type(sd),
                key_points=self._extract_key_points(sd),
                data_source=sd.get("source_text"),
            ))
        return SlideOutline(task_id=task_id, total_pages=len(items), slides=items)

    def _detect_chart_type(self, sd: Dict) -> Optional[str]:
        images = sd.get("images", [])
        for img in images:
            if img.get("image_type") == "chart":
                explicit_type = img.get("chart_type")
                if explicit_type and explicit_type != "chart":
                    return explicit_type
                src = img.get("src", "").lower()
                result = self._match_chart_type_from_src(src)
                if result:
                    return result
                return "chart"
            src = img.get("src", "")
            src_lower = src.lower()
            if any(kw in src_lower for kw in (
                "chart", "pie", "bar", "line", "radar",
                "scatter", "bubble", "waterfall", "quadrant", "hbar",
            )):
                result = self._match_chart_type_from_src(src_lower)
                if result:
                    return result
        return None

    @staticmethod
    def _match_chart_type_from_src(src_lower: str) -> Optional[str]:
        if "pie" in src_lower:
            return "pie"
        if "hbar" in src_lower:
            return "hbar"
        if "bar_line" in src_lower:
            return "bar_line"
        if "bar" in src_lower:
            return "bar"
        if "line" in src_lower:
            return "line"
        if "radar" in src_lower:
            return "radar"
        if "scatter" in src_lower:
            return "scatter"
        if "bubble" in src_lower:
            return "bubble"
        if "waterfall" in src_lower:
            return "waterfall"
        if "quadrant" in src_lower:
            return "quadrant"
        return None

    def _extract_key_points(self, sd: Dict) -> List[str]:
        items = sd.get("items", [])
        if items:
            return items[:5]
        content = sd.get("content", "")
        if content:
            sentences = [s.strip() for s in content.split("\u3002") if s.strip()]
            return sentences[:5]
        return []

    def _summarize_data(self, sd: Dict) -> str:
        parts = []
        table = sd.get("table_data", [])
        if table:
            parts.append(f"{len(table)-1}-row table")
        images = sd.get("images", [])
        chart_count = sum(1 for img in images if img.get("image_type") == "chart")
        if chart_count:
            suffix = "s" if chart_count > 1 else ""
            parts.append(f"{chart_count} chart{suffix}")
        items = sd.get("items", [])
        if items:
            parts.append(f"{len(items)} bullet points")
        return " + ".join(parts) if parts else "text only"

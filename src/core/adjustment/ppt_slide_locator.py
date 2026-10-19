from typing import Dict, List, Optional


class PptSlideLocator:

    def locate(self, slide_data_list: List[Dict],
               slide_index: Optional[int] = None,
               slide_title: Optional[str] = None,
               keyword: Optional[str] = None) -> Optional[int]:
        if slide_index is not None:
            if 0 <= slide_index < len(slide_data_list):
                return slide_index
            return None
        if slide_title is not None:
            return self._match_by_title(slide_data_list, slide_title)
        if keyword is not None:
            return self._match_by_keyword(slide_data_list, keyword)
        return None

    def _match_by_title(self, slide_data_list: List[Dict],
                        title: str) -> Optional[int]:
        title_lower = title.lower()
        for i, sd in enumerate(slide_data_list):
            if title_lower in sd.get("title", "").lower():
                return i
        return None

    def _match_by_keyword(self, slide_data_list: List[Dict],
                          keyword: str) -> Optional[int]:
        kw_lower = keyword.lower()
        for i, sd in enumerate(slide_data_list):
            if kw_lower in sd.get("title", "").lower():
                return i
            for item in sd.get("items", []):
                if kw_lower in str(item).lower():
                    return i
            for row in sd.get("table_data", []):
                for cell in row:
                    if kw_lower in str(cell).lower():
                        return i
            if kw_lower in sd.get("content", "").lower():
                return i
        return None

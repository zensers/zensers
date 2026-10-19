import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.500

LAYOUT_TOKENS = {
    "margin.left": 0.8,
    "margin.right": 0.8,
    "margin.top": 0.3,
    "content.top": 1.1,
    "content.width": 11.7,
    "content.height": 5.8,
    "footer.top": 6.9,
    "footer.height": 0.6,
    "gap.element": 0.3,
    "gap.section": 0.5,
    "gap.card": 0.4,
    "chart.center_width": 8.0,
    "chart.max_height": 2.5,
    "chart.min_height": 1.8,
    "kpi.max_cards": 4,
    "kpi.lr_width": 5.5,
    "table.lr_width": 5.6,
    "photo.width": 5.5,
    "items.width_chart": 5.0,
    "items.width_photo": 5.5,
}

NO_CHART_TEMPLATES = {"cover", "toc", "section_title", "end", "comparison"}

TYPO_BOUNDS = {
    "font.min": 10,
    "font.max_items": 36,
    "font.max_table": 16,
    "font.max_toc": 32,
    "font.min_table": 11,
    "row_height.min": 0.35,
    "row_height.max": 0.95,
    "line_spacing.min": 6,
    "line_spacing.max": 48,
    "kpi.number_max": 40,
    "kpi.number_min": 18,
    "kpi.label_max": 16,
    "kpi.label_min": 9,
}


class LayoutEngine:
    def __init__(self, tokens: Dict = None):
        self.T = {**LAYOUT_TOKENS, **(tokens or {})}

    def compute(self, slide_data: Dict, template: Dict) -> Dict[str, Dict]:
        profile = self._profile(slide_data)
        scenario = self._classify(profile)
        layout = self._layout(scenario, profile, slide_data, template)
        if not layout:
            return {}
        valid, issues = self._validate(layout, profile)
        if not valid:
            logger.warning("Layout validation failed for '%s': %s", scenario, issues)
            return self._fallback_layout(profile, slide_data, template)
        return layout

    def can_accommodate_chart(self, slide_data: Dict, template_name: str) -> bool:
        if template_name in NO_CHART_TEMPLATES:
            return False
        profile = self._profile(slide_data)
        if profile["kpi_count"] >= 4 and profile["has_table"]:
            return False
        if profile["table_rows"] > 8 and profile["has_items"] and profile["item_count"] > 5:
            return False
        return True

    def _profile(self, slide_data) -> Dict:
        kpi_data = slide_data.get("kpi_data", [])
        images = slide_data.get("images", [])
        table_data = slide_data.get("table_data", [])
        items = slide_data.get("items", [])
        insight_text = slide_data.get("insight_text", "")
        return {
            "has_kpis": bool(kpi_data) and len(kpi_data) >= 2,
            "kpi_count": min(len(kpi_data), 4),
            "has_chart": any(img.get("image_type") == "chart" for img in images),
            "has_photo": bool(images) and any(
                img.get("image_type") in ("product", "technology", "illustration")
                for img in images
            ),
            "chart_count": sum(1 for img in images if img.get("image_type") == "chart"),
            "has_table": bool(table_data) and len(table_data) >= 2,
            "table_rows": len(table_data) if table_data else 0,
            "has_items": bool(items),
            "item_count": len(items),
            "has_insight": bool(insight_text),
        }

    def _classify(self, profile) -> str:
        if profile["has_kpis"]:
            if profile["has_photo"]:
                return "kpi_with_photo"
            if profile["has_chart"]:
                return "kpi_with_chart"
            return "kpi_solo"
        if profile["has_table"]:
            if profile["has_photo"]:
                return "table_with_photo"
            if profile["has_chart"]:
                return "table_with_chart"
            return "table_solo"
        if profile["has_items"]:
            if profile["has_photo"]:
                return "items_with_photo"
            if profile["has_chart"]:
                return "items_with_chart"
            return "items_solo"
        if profile["chart_count"] >= 2 and profile["has_chart"] and not profile["has_items"]:
            return "dual_chart"
        return "text_only"

    def _typo_items(self, count: int, available_h: float, is_toc: bool = False,
                    available_w: float = 11.7, avg_item_chars: int = 20) -> Dict:
        B = TYPO_BOUNDS
        if count <= 0:
            count = 1
        if is_toc:
            font_max = B["font.max_toc"]
            font_min = 14
        else:
            font_max = B["font.max_items"]
            font_min = B["font.min"]
        if count <= 2:
            line_ratio = 2.0
        elif count <= 4:
            line_ratio = 1.5
        elif count <= 6:
            line_ratio = 1.2
        else:
            line_ratio = 0.9
        max_lines_per_item = max(1, int(avg_item_chars / max(4, available_w * 72 / (font_max * 1.2))) + 1)
        per_line_h = available_h / (count * max_lines_per_item)
        target_font = per_line_h * 72 / (line_ratio + 0.3)
        font_size = max(font_min, min(font_max, target_font))
        chars_per_line = max(4, available_w * 72 / (font_size * 1.2))
        actual_lines = max(1, (avg_item_chars + chars_per_line - 1) // chars_per_line)
        if count * actual_lines * font_size * (line_ratio + 0.3) / 72 > available_h:
            target_font = available_h * 72 / (count * actual_lines * (line_ratio + 0.3))
            font_size = max(font_min, min(font_max, target_font))
        line_spacing = font_size * line_ratio
        line_spacing = max(B["line_spacing.min"], line_spacing)
        bullet_font_size = min(font_size + 4, font_max + 4)
        return {
            "font_size": round(font_size),
            "line_spacing": round(line_spacing),
            "bullet_font_size": round(bullet_font_size),
            "space_before": round(line_spacing / 3),
        }

    def _typo_table(self, rows: int, available_h: float) -> Dict:
        B = TYPO_BOUNDS
        if rows <= 0:
            rows = 1
        row_height = available_h / rows
        row_height = max(B["row_height.min"], min(B["row_height.max"], row_height))
        actual_h = available_h
        if row_height * rows < available_h:
            row_height = available_h / rows
        font_ratio = (row_height - B["row_height.min"]) / max(0.01, B["row_height.max"] - B["row_height.min"])
        font_ratio = max(0.0, min(1.0, font_ratio))
        font_size = B["font.min_table"] + font_ratio * (B["font.max_table"] - B["font.min_table"])
        header_font_size = font_size + 2
        cell_padding = max(2, round(row_height * 5))
        return {
            "row_height": round(row_height, 3),
            "height": round(actual_h, 2),
            "font_size": round(font_size),
            "header_font_size": round(header_font_size),
            "cell_padding": cell_padding,
        }

    def _typo_kpi(self, card_height: float, card_width: float, kpi_count: int) -> Dict:
        B = TYPO_BOUNDS
        size_ratio = min(card_height, card_width) / 3.5
        size_ratio = max(0.4, min(1.2, size_ratio))
        number_size = B["kpi.number_min"] + size_ratio * (B["kpi.number_max"] - B["kpi.number_min"])
        number_size = max(B["kpi.number_min"], min(B["kpi.number_max"], number_size))
        label_size = B["kpi.label_min"] + size_ratio * (B["kpi.label_max"] - B["kpi.label_min"])
        label_size = max(B["kpi.label_min"], min(B["kpi.label_max"], label_size))
        layout_mode = "grid"
        grid_cols = 2 if kpi_count <= 2 or card_height > card_width * 0.8 else 2
        return {
            "number_size": round(number_size),
            "label_size": round(label_size),
            "layout_mode": layout_mode,
            "grid_cols": grid_cols,
        }

    def _layout(self, scenario, profile, slide_data, template) -> Dict:
        dispatch = {
            "kpi_solo": self._layout_kpi_solo,
            "kpi_with_chart": self._layout_kpi_with_chart,
            "kpi_with_photo": self._layout_kpi_with_photo,
            "table_with_chart": self._layout_table_with_chart,
            "table_with_photo": self._layout_table_with_photo,
            "table_solo": self._layout_table_solo,
            "items_with_chart": self._layout_items_with_chart,
            "items_with_photo": self._layout_items_with_photo,
            "items_solo": self._layout_items_solo,
        }
        handler = dispatch.get(scenario)
        if handler:
            return handler(profile, slide_data, template)
        return {}

    def _content_h(self) -> float:
        return self.T["footer.top"] - self.T["content.top"]

    def _layout_kpi_solo(self, profile, slide_data, template) -> Dict:
        T = self.T
        kpi_count = profile["kpi_count"]
        full_h = T["footer.top"] - T["content.top"]
        gap = T["gap.card"]
        if kpi_count <= 2:
            card_h = min(2.8, full_h * 0.55)
        else:
            card_h = min(2.0, full_h * 0.45)
        card_w = (T["content.width"] - gap * (kpi_count - 1)) / kpi_count
        typo = self._typo_kpi(card_h, card_w, kpi_count)
        return {
            "kpi_row": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": T["content.width"],
                "height": card_h,
                "_style_delta": typo,
            },
        }

    def _layout_kpi_with_chart(self, profile, slide_data, template) -> Dict:
        T = self.T
        kpi_w = T["kpi.lr_width"]
        chart_w = T["content.width"] - kpi_w - T["gap.section"]
        content_h = self._content_h()
        gap = T["gap.card"]
        kpi_count = profile["kpi_count"]
        grid_cols = 2
        grid_rows = (kpi_count + grid_cols - 1) // grid_cols
        card_w = (kpi_w - gap * (grid_cols - 1)) / grid_cols
        card_h = (content_h - gap * (grid_rows - 1)) / grid_rows
        typo = self._typo_kpi(card_h, card_w, kpi_count)
        return {
            "kpi_row": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": kpi_w,
                "height": content_h,
                "_style_delta": typo,
            },
            "chart": {
                "left": T["margin.left"] + kpi_w + T["gap.section"],
                "top": T["content.top"],
                "width": chart_w,
                "height": content_h,
            },
        }

    def _layout_kpi_with_photo(self, profile, slide_data, template) -> Dict:
        T = self.T
        photo_w = T["photo.width"]
        kpi_w = T["content.width"] - photo_w - T["gap.section"]
        content_h = self._content_h()
        gap = T["gap.card"]
        kpi_count = profile["kpi_count"]
        grid_cols = 2
        grid_rows = (kpi_count + grid_cols - 1) // grid_cols
        card_w = (kpi_w - gap * (grid_cols - 1)) / grid_cols
        card_h = (content_h - gap * (grid_rows - 1)) / grid_rows
        typo = self._typo_kpi(card_h, card_w, kpi_count)
        return {
            "kpi_row": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": kpi_w,
                "height": content_h,
                "_style_delta": typo,
            },
            "chart": {
                "left": T["margin.left"] + kpi_w + T["gap.section"],
                "top": T["content.top"],
                "width": photo_w,
                "height": content_h,
            },
        }

    def _layout_table_with_chart(self, profile, slide_data, template) -> Dict:
        T = self.T
        table_w = T["table.lr_width"]
        chart_w = T["content.width"] - table_w - T["gap.section"]
        content_h = self._content_h()
        table_rows = profile["table_rows"]
        typo = self._typo_table(table_rows, content_h)
        table_h = typo["height"]
        return {
            "data_table": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": table_w,
                "height": table_h,
                "_style_delta": {
                    "row_height": typo["row_height"],
                    "row_font_size": typo["font_size"],
                    "header_font_size": typo["header_font_size"],
                    "cell_padding": typo["cell_padding"],
                },
            },
            "chart": {
                "left": T["margin.left"] + table_w + T["gap.section"],
                "top": T["content.top"],
                "width": chart_w,
                "height": table_h,
            },
        }

    def _layout_table_with_photo(self, profile, slide_data, template) -> Dict:
        T = self.T
        table_w = T["table.lr_width"]
        photo_w = T["content.width"] - table_w - T["gap.section"]
        content_h = self._content_h()
        table_rows = profile["table_rows"]
        typo = self._typo_table(table_rows, content_h)
        table_h = typo["height"]
        return {
            "data_table": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": table_w,
                "height": table_h,
                "_style_delta": {
                    "row_height": typo["row_height"],
                    "row_font_size": typo["font_size"],
                    "header_font_size": typo["header_font_size"],
                    "cell_padding": typo["cell_padding"],
                },
            },
            "chart": {
                "left": T["margin.left"] + table_w + T["gap.section"],
                "top": T["content.top"],
                "width": photo_w,
                "height": table_h,
            },
        }

    def _layout_table_solo(self, profile, slide_data, template) -> Dict:
        T = self.T
        content_h = self._content_h()
        table_rows = profile["table_rows"]
        typo = self._typo_table(table_rows, content_h)
        return {
            "data_table": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": T["content.width"],
                "height": typo["height"],
                "_style_delta": {
                    "row_height": typo["row_height"],
                    "row_font_size": typo["font_size"],
                    "header_font_size": typo["header_font_size"],
                    "cell_padding": typo["cell_padding"],
                },
            },
        }

    def _avg_item_chars(self, slide_data: Dict) -> int:
        items = slide_data.get("items", [])
        if not items:
            return 20
        total = sum(len(item) for item in items)
        return max(5, total // len(items))

    def _layout_items_with_chart(self, profile, slide_data, template) -> Dict:
        T = self.T
        items_w = T["items.width_chart"]
        chart_w = T["content.width"] - items_w - T["gap.section"]
        content_h = self._content_h()
        item_count = profile["item_count"]
        typo = self._typo_items(item_count, content_h, available_w=items_w, avg_item_chars=self._avg_item_chars(slide_data))
        return {
            "bullet_items": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": items_w,
                "height": content_h,
                "_style_delta": typo,
            },
            "chart": {
                "left": T["margin.left"] + items_w + T["gap.section"],
                "top": T["content.top"],
                "width": chart_w,
                "height": content_h,
            },
        }

    def _layout_items_with_photo(self, profile, slide_data, template) -> Dict:
        T = self.T
        items_w = T["items.width_photo"]
        photo_w = T["content.width"] - items_w - T["gap.section"]
        content_h = self._content_h()
        item_count = profile["item_count"]
        typo = self._typo_items(item_count, content_h, available_w=items_w, avg_item_chars=self._avg_item_chars(slide_data))
        return {
            "bullet_items": {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": items_w,
                "height": content_h,
                "_style_delta": typo,
            },
            "chart": {
                "left": T["margin.left"] + items_w + T["gap.section"],
                "top": T["content.top"],
                "width": photo_w,
                "height": content_h,
            },
        }

    def _layout_items_solo(self, profile, slide_data, template) -> Dict:
        T = self.T
        content_h = self._content_h()
        item_count = profile["item_count"]
        is_toc = slide_data.get("slide_type") in ("toc",)
        items_w = T["content.width"]
        typo = self._typo_items(item_count, content_h, is_toc=is_toc, available_w=items_w, avg_item_chars=self._avg_item_chars(slide_data))
        slot_id = "toc_items" if is_toc else "bullet_items"
        return {
            slot_id: {
                "left": T["margin.left"],
                "top": T["content.top"],
                "width": T["content.width"],
                "height": content_h,
                "_style_delta": typo,
            },
        }

    def _validate(self, layout: Dict, profile: Dict) -> Tuple[bool, List[str]]:
        T = self.T
        issues = []
        available = T["footer.top"] - T["content.top"]

        for slot_id, pos in layout.items():
            w, h = pos.get("width"), pos.get("height")
            if w is not None and h is not None and h > 0:
                ratio = w / h
                is_full_width = w >= T["content.width"] * 0.95
                is_full_height = h >= available * 0.95
                if not is_full_width and not is_full_height:
                    if slot_id == "chart":
                        max_ratio = 4.5
                    elif slot_id == "data_table":
                        max_ratio = 6.0
                    else:
                        max_ratio = 4.5
                    if ratio < 0.8 or ratio > max_ratio:
                        issues.append(
                            f"{slot_id}: aspect ratio {ratio:.1f} out of [0.8, {max_ratio}]"
                        )

        content_area = T["content.width"] * (T["footer.top"] - T["content.top"])
        used_area = sum(
            pos.get("width", 0) * pos.get("height", 0)
            for pos in layout.values()
            if isinstance(pos.get("width"), (int, float))
            and isinstance(pos.get("height"), (int, float))
        )
        utilization = used_area / content_area if content_area > 0 else 0
        if utilization < 0.5:
            issues.append(f"Content utilization {utilization:.0%} < 50%")

        rects = [
            (sid, pos)
            for sid, pos in layout.items()
            if isinstance(pos.get("width"), (int, float))
            and isinstance(pos.get("height"), (int, float))
        ]
        for i, (sid_a, a) in enumerate(rects):
            for sid_b, b in rects[i + 1 :]:
                if self._overlaps(a, b):
                    issues.append(f"{sid_a} overlaps {sid_b}")

        weighted = [
            (
                pos.get("left", 0) + pos.get("width", 0) / 2,
                pos.get("width", 0) * pos.get("height", 0),
            )
            for pos in layout.values()
            if isinstance(pos.get("left"), (int, float))
            and isinstance(pos.get("width"), (int, float))
            and isinstance(pos.get("height"), (int, float))
        ]
        if weighted:
            total_area = sum(w for _, w in weighted)
            if total_area > 0:
                cx = sum(x * w for x, w in weighted) / total_area
            else:
                cx = sum(x for x, _ in weighted) / len(weighted)
            page_center = T["margin.left"] + T["content.width"] / 2
            offset = abs(cx - page_center) / (T["content.width"] / 2)
            if offset > 0.3:
                issues.append(f"Visual imbalance: center offset {offset:.0%}")

        return len(issues) == 0, issues

    def _fallback_layout(self, profile, slide_data, template) -> Dict:
        T = self.T
        content_h = self._content_h()
        if profile["has_kpis"]:
            kpi_count = profile.get("kpi_count", 2)
            typo = self._typo_kpi(content_h * 0.45, T["content.width"] / kpi_count, kpi_count)
            return {
                "kpi_row": {
                    "left": T["margin.left"],
                    "top": T["content.top"],
                    "width": T["content.width"],
                    "height": content_h,
                    "_style_delta": typo,
                },
            }
        if profile["has_table"]:
            table_rows = profile.get("table_rows", 3)
            typo = self._typo_table(table_rows, content_h)
            return {
                "data_table": {
                    "left": T["margin.left"],
                    "top": T["content.top"],
                    "width": T["content.width"],
                    "height": typo["height"],
                    "_style_delta": {
                        "row_height": typo["row_height"],
                        "row_font_size": typo["font_size"],
                        "header_font_size": typo["header_font_size"],
                        "cell_padding": typo["cell_padding"],
                    },
                },
            }
        return {}

    def _overlaps(self, a: Dict, b: Dict) -> bool:
        a_l = a.get("left", 0)
        a_t = a.get("top", 0)
        a_r = a_l + a.get("width", 0)
        a_b = a_t + a.get("height", 0)
        b_l = b.get("left", 0)
        b_t = b.get("top", 0)
        b_r = b_l + b.get("width", 0)
        b_b = b_t + b.get("height", 0)
        return a_l < b_r and a_r > b_l and a_t < b_b and a_b > b_t

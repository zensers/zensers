import pytest
from src.converters.layout_engine import LayoutEngine, LAYOUT_TOKENS, TYPO_BOUNDS


class TestProfile:
    def test_empty_slide(self):
        engine = LayoutEngine()
        p = engine._profile({})
        assert p["has_kpis"] is False
        assert p["kpi_count"] == 0
        assert p["has_chart"] is False
        assert p["has_photo"] is False
        assert p["chart_count"] == 0
        assert p["has_table"] is False
        assert p["table_rows"] == 0
        assert p["has_items"] is False
        assert p["item_count"] == 0
        assert p["has_insight"] is False

    def test_kpi_data_with_two_kpis(self):
        engine = LayoutEngine()
        p = engine._profile({"kpi_data": [{"number": "100", "label": "A"}, {"number": "200", "label": "B"}]})
        assert p["has_kpis"] is True
        assert p["kpi_count"] == 2

    def test_kpi_data_with_one_kpi_is_not_has_kpis(self):
        engine = LayoutEngine()
        p = engine._profile({"kpi_data": [{"number": "100", "label": "A"}]})
        assert p["has_kpis"] is False
        assert p["kpi_count"] == 1

    def test_kpi_data_capped_at_four(self):
        engine = LayoutEngine()
        p = engine._profile({"kpi_data": [{"number": str(i)} for i in range(6)]})
        assert p["kpi_count"] == 4

    def test_chart_images_only(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [{"src": "a.png", "image_type": "chart"}]})
        assert p["has_chart"] is True
        assert p["has_photo"] is False
        assert p["chart_count"] == 1

    def test_photo_images(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [{"src": "a.png", "image_type": "product"}]})
        assert p["has_chart"] is False
        assert p["has_photo"] is True
        assert p["chart_count"] == 0

    def test_mixed_chart_and_photo(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [
            {"src": "a.png", "image_type": "chart"},
            {"src": "b.png", "image_type": "product"},
        ]})
        assert p["has_chart"] is True
        assert p["has_photo"] is True
        assert p["chart_count"] == 1

    def test_images_default_to_chart(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [{"src": "a.png"}]})
        assert p["has_chart"] is False
        assert p["has_photo"] is False

    def test_technology_counts_as_photo(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [{"src": "a.png", "image_type": "technology"}]})
        assert p["has_chart"] is False
        assert p["has_photo"] is True

    def test_illustration_counts_as_photo(self):
        engine = LayoutEngine()
        p = engine._profile({"images": [{"src": "a.png", "image_type": "illustration"}]})
        assert p["has_chart"] is False
        assert p["has_photo"] is True

    def test_table_data_with_two_rows(self):
        engine = LayoutEngine()
        p = engine._profile({"table_data": [["A", "B"], ["1", "2"]]})
        assert p["has_table"] is True
        assert p["table_rows"] == 2

    def test_table_data_with_one_row_is_not_has_table(self):
        engine = LayoutEngine()
        p = engine._profile({"table_data": [["A", "B"]]})
        assert p["has_table"] is False
        assert p["table_rows"] == 1

    def test_items(self):
        engine = LayoutEngine()
        p = engine._profile({"items": ["point 1", "point 2"]})
        assert p["has_items"] is True
        assert p["item_count"] == 2

    def test_insight_text(self):
        engine = LayoutEngine()
        p = engine._profile({"insight_text": "Key insight"})
        assert p["has_insight"] is True

    def test_empty_insight_text(self):
        engine = LayoutEngine()
        p = engine._profile({"insight_text": ""})
        assert p["has_insight"] is False


class TestClassify:
    def test_kpi_solo(self):
        engine = LayoutEngine()
        p = {"has_kpis": True, "has_photo": False, "has_chart": False}
        assert engine._classify(p) == "kpi_solo"

    def test_kpi_with_chart(self):
        engine = LayoutEngine()
        p = {"has_kpis": True, "has_photo": False, "has_chart": True}
        assert engine._classify(p) == "kpi_with_chart"

    def test_kpi_with_photo(self):
        engine = LayoutEngine()
        p = {"has_kpis": True, "has_photo": True, "has_chart": False}
        assert engine._classify(p) == "kpi_with_photo"

    def test_kpi_with_photo_takes_priority_over_chart(self):
        engine = LayoutEngine()
        p = {"has_kpis": True, "has_photo": True, "has_chart": True}
        assert engine._classify(p) == "kpi_with_photo"

    def test_table_solo(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": True, "has_chart": False, "has_photo": False}
        assert engine._classify(p) == "table_solo"

    def test_table_with_chart(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": True, "has_chart": True, "has_photo": False}
        assert engine._classify(p) == "table_with_chart"

    def test_table_with_photo(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": True, "has_chart": False, "has_photo": True}
        assert engine._classify(p) == "table_with_photo"

    def test_items_with_chart(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": False, "has_items": True,
             "has_chart": True, "has_photo": False, "chart_count": 1}
        assert engine._classify(p) == "items_with_chart"

    def test_items_with_photo(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": False, "has_items": True,
             "has_chart": False, "has_photo": True, "chart_count": 1}
        assert engine._classify(p) == "items_with_photo"

    def test_dual_chart(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": False, "has_items": False,
             "has_chart": True, "has_photo": False, "chart_count": 2}
        assert engine._classify(p) == "dual_chart"

    def test_dual_chart_not_triggered_by_photos(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": False, "has_items": False,
             "has_chart": False, "has_photo": True, "chart_count": 2}
        assert engine._classify(p) == "text_only"

    def test_text_only(self):
        engine = LayoutEngine()
        p = {"has_kpis": False, "has_table": False, "has_items": False,
             "has_chart": False, "has_photo": False, "chart_count": 0}
        assert engine._classify(p) == "text_only"


class TestTypoItems:
    def test_few_items_larger_font(self):
        engine = LayoutEngine()
        t = engine._typo_items(3, 4.7)
        assert t["font_size"] >= 18
        assert t["line_spacing"] >= 10

    def test_many_items_smaller_font(self):
        engine = LayoutEngine()
        t_few = engine._typo_items(3, 4.7)
        t_many = engine._typo_items(7, 4.7)
        assert t_many["font_size"] <= t_few["font_size"]
        assert t_many["font_size"] >= TYPO_BOUNDS["font.min"]

    def test_toc_larger_font(self):
        engine = LayoutEngine()
        t = engine._typo_items(4, 4.7, is_toc=True)
        t_normal = engine._typo_items(4, 4.7, is_toc=False)
        assert t["font_size"] >= TYPO_BOUNDS["font.min"]

    def test_font_within_bounds(self):
        engine = LayoutEngine()
        for count in [1, 3, 5, 7, 10]:
            t = engine._typo_items(count, 4.7)
            assert TYPO_BOUNDS["font.min"] <= t["font_size"] <= TYPO_BOUNDS["font.max_items"]


class TestTypoTable:
    def test_few_rows_taller(self):
        engine = LayoutEngine()
        t = engine._typo_table(3, 4.7)
        assert t["row_height"] > 0.5
        assert t["height"] == pytest.approx(4.7)

    def test_many_rows_shorter(self):
        engine = LayoutEngine()
        t = engine._typo_table(8, 4.7)
        assert t["row_height"] <= 0.6
        assert t["font_size"] >= TYPO_BOUNDS["font.min_table"]

    def test_row_height_capped(self):
        engine = LayoutEngine()
        t = engine._typo_table(2, 4.7)
        assert t["row_height"] >= TYPO_BOUNDS["row_height.min"]


class TestTypoKpi:
    def test_large_card_large_font(self):
        engine = LayoutEngine()
        t = engine._typo_kpi(3.0, 3.0, 4)
        assert t["number_size"] >= 25
        assert t["label_size"] >= 11

    def test_small_card_smaller_font(self):
        engine = LayoutEngine()
        t = engine._typo_kpi(1.5, 1.5, 4)
        assert t["number_size"] < 30


class TestLayoutKpiSolo:
    def test_full_width_dynamic_height(self):
        engine = LayoutEngine()
        result = engine._layout_kpi_solo({"kpi_count": 4}, {}, {})
        assert result["kpi_row"]["left"] == 0.8
        assert result["kpi_row"]["width"] == 11.7
        assert result["kpi_row"]["height"] > 0
        assert "_style_delta" in result["kpi_row"]
        delta = result["kpi_row"]["_style_delta"]
        assert "number_size" in delta
        assert "label_size" in delta

    def test_2_kpis_taller_cards(self):
        engine = LayoutEngine()
        r2 = engine._layout_kpi_solo({"kpi_count": 2}, {}, {})
        r4 = engine._layout_kpi_solo({"kpi_count": 4}, {}, {})
        assert r2["kpi_row"]["height"] >= r4["kpi_row"]["height"]


class TestLayoutKpiWithChart:
    def test_kpi_left_chart_right(self):
        engine = LayoutEngine()
        result = engine._layout_kpi_with_chart({"kpi_count": 4}, {}, {})
        kpi = result["kpi_row"]
        assert kpi["left"] == 0.8
        assert kpi["width"] == pytest.approx(5.5)
        delta = kpi["_style_delta"]
        assert "number_size" in delta
        assert "label_size" in delta
        assert delta["layout_mode"] == "grid"
        chart = result["chart"]
        assert chart["left"] == pytest.approx(0.8 + 5.5 + 0.5)
        assert kpi["height"] == chart["height"]


class TestLayoutTableWithChart:
    def test_3_rows_left_right(self):
        engine = LayoutEngine()
        result = engine._layout_table_with_chart({"table_rows": 3}, {}, {})
        tbl = result["data_table"]
        chart = result["chart"]
        assert tbl["left"] == 0.8
        assert tbl["width"] == 5.6
        assert tbl["height"] > 0
        assert chart["width"] == pytest.approx(5.6)
        assert "_style_delta" in tbl
        assert "row_height" in tbl["_style_delta"]
        assert "row_font_size" in tbl["_style_delta"]

    def test_more_rows_smaller_row_height(self):
        engine = LayoutEngine()
        r3 = engine._layout_table_with_chart({"table_rows": 3}, {}, {})
        r7 = engine._layout_table_with_chart({"table_rows": 7}, {}, {})
        assert r3["data_table"]["_style_delta"]["row_height"] >= r7["data_table"]["_style_delta"]["row_height"]


class TestLayoutItemsWithChart:
    def test_left_right_layout(self):
        engine = LayoutEngine()
        result = engine._layout_items_with_chart({"item_count": 5}, {}, {})
        items = result["bullet_items"]
        chart = result["chart"]
        assert items["left"] == 0.8
        assert items["width"] == 5.0
        assert chart["width"] == pytest.approx(11.7 - 5.0 - 0.5)
        assert "_style_delta" in items
        assert "font_size" in items["_style_delta"]

    def test_more_items_smaller_font(self):
        engine = LayoutEngine()
        r3 = engine._layout_items_with_chart({"item_count": 3}, {}, {})
        r7 = engine._layout_items_with_chart({"item_count": 7}, {}, {})
        assert r3["bullet_items"]["_style_delta"]["font_size"] >= r7["bullet_items"]["_style_delta"]["font_size"]


class TestLayoutKpiWithPhoto:
    def test_left_right_grid_layout(self):
        engine = LayoutEngine()
        result = engine._layout_kpi_with_photo({"kpi_count": 4}, {}, {})
        kpi = result["kpi_row"]
        photo = result["chart"]
        assert kpi["width"] == pytest.approx(5.7)
        assert photo["width"] == pytest.approx(5.5)
        assert kpi["height"] == photo["height"]
        assert kpi["_style_delta"]["layout_mode"] == "grid"


class TestLayoutItemsWithPhoto:
    def test_left_right_layout(self):
        engine = LayoutEngine()
        result = engine._layout_items_with_photo({"item_count": 4}, {}, {})
        items = result["bullet_items"]
        photo = result["chart"]
        assert items["width"] == 5.5
        total = items["width"] + 0.5 + photo["width"]
        assert total == pytest.approx(11.7)


class TestLayoutTableWithPhoto:
    def test_left_right_layout_5_rows(self):
        engine = LayoutEngine()
        result = engine._layout_table_with_photo({"table_rows": 5}, {}, {})
        tbl = result["data_table"]
        photo = result["chart"]
        assert tbl["width"] == 5.6
        total = tbl["width"] + 0.5 + photo["width"]
        assert total == pytest.approx(11.7)

    def test_left_right_layout_3_rows(self):
        engine = LayoutEngine()
        result = engine._layout_table_with_photo({"table_rows": 3}, {}, {})
        assert result["data_table"]["width"] == 5.6


class TestValidate:
    def test_no_overlap_passes(self):
        engine = LayoutEngine()
        layout = {
            "a": {"left": 0.8, "top": 1.1, "width": 5.0, "height": 4.0},
            "b": {"left": 6.3, "top": 1.1, "width": 5.0, "height": 4.0},
        }
        ok, issues = engine._validate(layout, {})
        assert ok is True
        assert issues == []

    def test_overlap_fails(self):
        engine = LayoutEngine()
        layout = {
            "a": {"left": 0.8, "top": 1.1, "width": 5.0, "height": 4.0},
            "b": {"left": 3.0, "top": 1.1, "width": 5.0, "height": 4.0},
        }
        ok, issues = engine._validate(layout, {})
        assert ok is False
        assert any("overlap" in i.lower() for i in issues)

    def test_low_utilization_fails(self):
        engine = LayoutEngine()
        layout = {
            "a": {"left": 0.8, "top": 1.1, "width": 2.0, "height": 1.0},
        }
        ok, issues = engine._validate(layout, {})
        assert ok is False
        assert any("utilization" in i.lower() for i in issues)

    def test_full_width_exempt_from_ratio(self):
        engine = LayoutEngine()
        layout = {
            "kpi_row": {"left": 0.8, "top": 1.1, "width": 11.7, "height": 3.5},
        }
        ok, issues = engine._validate(layout, {})
        assert ok is True

    def test_full_height_exempt_from_ratio(self):
        engine = LayoutEngine()
        layout = {
            "items": {"left": 0.8, "top": 1.1, "width": 5.0, "height": 4.5},
            "chart": {"left": 6.3, "top": 1.1, "width": 5.7, "height": 4.5},
        }
        ok, _ = engine._validate(layout, {})
        assert ok is True

    def test_table_ratio_up_to_6(self):
        engine = LayoutEngine()
        layout = {
            "data_table": {"left": 0.8, "top": 1.1, "width": 5.6, "height": 2.0},
            "chart": {"left": 6.9, "top": 1.1, "width": 5.6, "height": 4.5},
        }
        ok, _ = engine._validate(layout, {})
        assert ok is True


class TestFallbackLayout:
    def test_kpi_fallback(self):
        engine = LayoutEngine()
        result = engine._fallback_layout({"has_kpis": True, "has_table": False, "kpi_count": 2}, {}, {})
        assert "kpi_row" in result
        assert result["kpi_row"]["width"] == 11.7

    def test_table_fallback(self):
        engine = LayoutEngine()
        result = engine._fallback_layout({"has_kpis": False, "has_table": True, "table_rows": 4}, {}, {})
        assert "data_table" in result
        assert result["data_table"]["width"] == 11.7

    def test_text_fallback_empty(self):
        engine = LayoutEngine()
        result = engine._fallback_layout({"has_kpis": False, "has_table": False}, {}, {})
        assert result == {}


class TestCanAccommodateChart:
    def test_cover_template_rejected(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({}, "cover") is False

    def test_toc_template_rejected(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({}, "toc") is False

    def test_section_title_rejected(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({}, "section_title") is False

    def test_end_template_rejected(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({}, "end") is False

    def test_comparison_rejected(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({}, "comparison") is False

    def test_kpi_highlight_allowed(self):
        engine = LayoutEngine()
        assert engine.can_accommodate_chart({"kpi_data": [{"n": "1"}, {"n": "2"}]}, "kpi_highlight") is True

    def test_full_kpi_plus_table_rejected(self):
        engine = LayoutEngine()
        sd = {"kpi_data": [{"n": str(i)} for i in range(4)], "table_data": [["A"], ["B"]]}
        assert engine.can_accommodate_chart(sd, "kpi_highlight") is False

    def test_dense_table_plus_items_rejected(self):
        engine = LayoutEngine()
        sd = {
            "table_data": [["A"]] * 9,
            "items": ["x"] * 6,
        }
        assert engine.can_accommodate_chart(sd, "data_table") is False


class TestCompute:
    def test_kpi_solo_returns_layout(self):
        engine = LayoutEngine()
        sd = {"kpi_data": [{"number": "100"}, {"number": "200"}]}
        template = {"slots": [{"id": "kpi_row", "type": "kpi_cards"}]}
        result = engine.compute(sd, template)
        assert "kpi_row" in result
        assert result["kpi_row"]["width"] == 11.7

    def test_kpi_with_chart_returns_layout(self):
        engine = LayoutEngine()
        sd = {
            "kpi_data": [{"number": "100"}, {"number": "200"}],
            "images": [{"src": "chart.png", "image_type": "chart"}],
        }
        template = {"slots": [{"id": "kpi_row"}, {"id": "chart"}]}
        result = engine.compute(sd, template)
        assert "kpi_row" in result
        assert "chart" in result

    def test_empty_slide_returns_empty(self):
        engine = LayoutEngine()
        result = engine.compute({}, {"slots": []})
        assert result == {}

    def test_validation_failure_triggers_fallback(self):
        engine = LayoutEngine(tokens={"content.width": 2.0, "kpi.lr_width": 1.0})
        sd = {
            "kpi_data": [{"number": "100"}, {"number": "200"}],
            "images": [{"src": "chart.png", "image_type": "chart"}],
        }
        template = {"slots": [{"id": "kpi_row"}, {"id": "chart"}]}
        result = engine.compute(sd, template)
        assert "kpi_row" in result


class TestOverlaps:
    def test_no_overlap(self):
        engine = LayoutEngine()
        a = {"left": 0, "top": 0, "width": 5, "height": 5}
        b = {"left": 6, "top": 0, "width": 5, "height": 5}
        assert engine._overlaps(a, b) is False

    def test_overlap(self):
        engine = LayoutEngine()
        a = {"left": 0, "top": 0, "width": 5, "height": 5}
        b = {"left": 3, "top": 0, "width": 5, "height": 5}
        assert engine._overlaps(a, b) is True

    def test_touching_edge_no_overlap(self):
        engine = LayoutEngine()
        a = {"left": 0, "top": 0, "width": 5, "height": 5}
        b = {"left": 5, "top": 0, "width": 5, "height": 5}
        assert engine._overlaps(a, b) is False

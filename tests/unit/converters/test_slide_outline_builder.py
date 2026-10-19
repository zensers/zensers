from src.converters.slide_outline_builder import SlideOutlineBuilder, SlideOutlineItem, SlideOutline


def _make_slide_data(slide_type="content", title="Test", items=None, 
                     table_data=None, images=None, source_text=None):
    sd = {"slide_type": slide_type, "title": title}
    if items is not None:
        sd["items"] = items
    if table_data is not None:
        sd["table_data"] = table_data
    if images is not None:
        sd["images"] = images
    if source_text is not None:
        sd["source_text"] = source_text
    return sd


class TestSlideOutlineItem:
    def test_defaults(self):
        item = SlideOutlineItem(page=1, slide_type="content", title="Test",
                                data_summary="", chart_type=None, 
                                key_points=[], data_source=None)
        assert item.page == 1
        assert item.chart_type is None


class TestSlideOutline:
    def test_confirmed_default_false(self):
        outline = SlideOutline(task_id="t1", total_pages=3, slides=[])
        assert outline.confirmed is False


class TestSlideOutlineBuilder:
    def test_build_basic_content_slide(self):
        sd = _make_slide_data("content", "Market Size", items=["CAGR 5%", "TAM $10B"])
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.task_id == "t1"
        assert outline.total_pages == 1
        assert len(outline.slides) == 1
        assert outline.slides[0].slide_type == "content"
        assert outline.slides[0].title == "Market Size"
        assert outline.slides[0].key_points == ["CAGR 5%", "TAM $10B"]

    def test_build_multiple_slides(self):
        s1 = _make_slide_data("cover", "Report Title")
        s2 = _make_slide_data("content", "Market Size", items=["point1"])
        s3 = _make_slide_data("end", "Thank You")
        outline = SlideOutlineBuilder().build([s1, s2, s3], task_id="t1")
        assert outline.total_pages == 3
        assert outline.slides[0].page == 1
        assert outline.slides[1].page == 2
        assert outline.slides[2].page == 3

    def test_chart_type_from_image_type_chart(self):
        sd = _make_slide_data("data", "Revenue", 
                              images=[{"src": "/charts/pie_revenue.png", "alt": "Revenue", "image_type": "chart"}])
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].chart_type == "pie"

    def test_chart_type_from_src_path(self):
        sd = _make_slide_data("data", "Revenue",
                              images=[{"src": "/charts/bar_revenue.png", "alt": "Revenue"}])
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].chart_type == "bar"

    def test_explicit_chart_type_wins_over_filename_inference(self):
        sd = _make_slide_data(
            "data",
            "Revenue",
            images=[{
                "src": "/artifacts/opaque-image-name.png",
                "alt": "Revenue",
                "image_type": "chart",
                "chart_type": "waterfall",
            }],
        )
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].chart_type == "waterfall"

    def test_no_chart_returns_none(self):
        sd = _make_slide_data("content", "Overview")
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].chart_type is None

    def test_data_summary_with_table(self):
        sd = _make_slide_data("data", "Revenue", 
                              table_data=[["Year", "Revenue"], ["2024", "$10B"], ["2025", "$12B"]])
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert "2-row table" in outline.slides[0].data_summary

    def test_data_summary_text_only(self):
        sd = _make_slide_data("content", "Overview")
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].data_summary == "text only"

    def test_source_text_extracted(self):
        sd = _make_slide_data("content", "Overview", source_text="National Bureau of Statistics")
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].data_source == "National Bureau of Statistics"

    def test_key_points_from_content_when_no_items(self):
        sd = _make_slide_data("content", "Overview")
        sd["content"] = "The market is growing\u3002Competition is fierce\u3002Innovation drives change\u3002"
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert len(outline.slides[0].key_points) >= 2

    def test_section_title_hyphenated_variant(self):
        sd = _make_slide_data("section-title", "Chapter 1")
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].slide_type == "section-title"

    def test_hbar_chart_type_order(self):
        sd = _make_slide_data("data", "Revenue",
                              images=[{"src": "/charts/hbar_revenue.png", "alt": "Revenue", "image_type": "chart"}])
        outline = SlideOutlineBuilder().build([sd], task_id="t1")
        assert outline.slides[0].chart_type == "hbar"

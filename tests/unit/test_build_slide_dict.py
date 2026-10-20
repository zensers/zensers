import pytest
from src.converters.base_parser import SlideElementParser


@pytest.fixture
def parser():
    return SlideElementParser()


class TestBuildSlideDictExtraTables:
    def test_multiple_tables_produce_extra_tables(self, parser):
        elements = [
            {"type": "table", "headers": ["H1", "H2"], "rows": [["a1", "a2"]]},
            {"type": "table", "headers": ["H3", "H4"], "rows": [["b1", "b2"]]},
        ]
        result = parser._build_slide_dict(elements)
        assert "table_data" in result
        assert result["table_data"] == [["H1", "H2"], ["a1", "a2"]]
        assert "extra_tables" in result
        assert len(result["extra_tables"]) == 1
        assert result["extra_tables"][0] == [["H3", "H4"], ["b1", "b2"]]

    def test_single_table_no_extra_tables(self, parser):
        elements = [
            {"type": "table", "headers": ["H1", "H2"], "rows": [["a1", "a2"]]},
        ]
        result = parser._build_slide_dict(elements)
        assert "table_data" in result
        assert "extra_tables" not in result

    def test_three_tables_produce_two_extra(self, parser):
        elements = [
            {"type": "table", "headers": ["A"], "rows": [["1"]]},
            {"type": "table", "headers": ["B"], "rows": [["2"]]},
            {"type": "table", "headers": ["C"], "rows": [["3"]]},
        ]
        result = parser._build_slide_dict(elements)
        assert "table_data" in result
        assert "extra_tables" in result
        assert len(result["extra_tables"]) == 2

    def test_source_text_from_data_source_attr(self, parser):
        elements = [{"type": "paragraph", "text": "hello"}]
        attrs = {"data-type": "content", "data-source": "Internal Research 2024"}
        result = parser._build_slide_dict(elements, attrs=attrs)
        assert result.get("source_text") == "Internal Research 2024"

    def test_no_source_text_without_attr(self, parser):
        elements = [{"type": "paragraph", "text": "hello"}]
        result = parser._build_slide_dict(elements)
        assert "source_text" not in result


class TestDashBulletSplitting:
    def test_dash_lines_become_items_and_prose_stays_content(self, parser):
        text = "上游核心零部件占整机成本 60% 以上。\n- 执行器总成价值量占比 35%\n- 传感器与 IMU 占比 12%"
        result = parser._build_slide_dict([{"type": "paragraph", "text": text}])
        assert result["items"] == ["执行器总成价值量占比 35%", "传感器与 IMU 占比 12%"]
        assert result["content"] == "上游核心零部件占整机成本 60% 以上。"

    def test_plain_paragraph_not_split(self, parser):
        result = parser._build_slide_dict([{"type": "paragraph", "text": "单一正文段落，无破折号行"}])
        assert result["content"] == "单一正文段落，无破折号行"
        assert "items" not in result

    def test_blank_lines_skipped(self, parser):
        text = "导语。\n\n- 要点一\n\n- 要点二"
        result = parser._build_slide_dict([{"type": "paragraph", "text": text}])
        assert result["items"] == ["要点一", "要点二"]
        assert result["content"] == "导语。"

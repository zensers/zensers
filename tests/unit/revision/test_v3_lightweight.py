"""Unit tests for V3 lightweight revision operations.

These tests run without LLM calls, without network, and without a running server.
"""

import json
from unittest.mock import MagicMock, patch


class TestIsLightweight:
    """Test _is_lightweight detection logic"""

    def make_analysis(self, action_type_str, confidence=1.0, needs_clarification=False):
        """Create a mock AnalysisResult with a single intent."""
        from src.core.adjustment.revision_types import (
            AnalysisResult, RevisionAction, RevisionOpType, RevisionTarget,
            LocationStrategy, SectionRef, RefType,
        )
        target = RevisionTarget(
            raw_text="test", section_refs=[], location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False,
        )
        action = RevisionAction(
            action_id="test",
            action_type=RevisionOpType(action_type_str),
            target=target,
            confidence=confidence,
        )
        return AnalysisResult(
            intents=[action],
            needs_clarification=needs_clarification,
        )

    def make_empty_analysis(self):
        return MagicMock(intents=[], needs_clarification=False)

    def test_lightweight_ops_allowed(self):
        """UPDATE_TITLE, REPLACE_TEXT, CHANGE_CASE, FIX_PUNCTUATION should be lightweight."""
        from src.core.adjustment.revision_executor import RevisionExecutor
        from src.core.adjustment.report_lock_manager import ReportLockManager

        executor = RevisionExecutor(ReportLockManager())
        for op in ("update_title", "replace_text", "change_case", "fix_punctuation"):
            analysis = self.make_analysis(op, confidence=0.9)
            assert executor._is_lightweight(analysis), f"{op} should be lightweight"

    def test_heavy_ops_not_allowed(self):
        """MODIFY, DELETE, ADD etc should NOT be lightweight."""
        from src.core.adjustment.revision_executor import RevisionExecutor
        from src.core.adjustment.report_lock_manager import ReportLockManager

        executor = RevisionExecutor(ReportLockManager())
        for op in ("modify", "delete", "add", "copy", "merge", "split",
                   "swap", "reorder", "dedup", "style", "modify_table",
                   "modify_chart", "translate"):
            analysis = self.make_analysis(op, confidence=0.9)
            assert not executor._is_lightweight(analysis), f"{op} should NOT be lightweight"

    def test_empty_analysis_not_lightweight(self):
        from src.core.adjustment.revision_executor import RevisionExecutor
        from src.core.adjustment.report_lock_manager import ReportLockManager

        executor = RevisionExecutor(ReportLockManager())
        analysis = MagicMock(intents=[], needs_clarification=False)
        assert not executor._is_lightweight(analysis)

    def test_none_not_lightweight(self):
        from src.core.adjustment.revision_executor import RevisionExecutor
        from src.core.adjustment.report_lock_manager import ReportLockManager

        executor = RevisionExecutor(ReportLockManager())
        assert not executor._is_lightweight(None)


class TestApplyLightweight:
    """Test _apply_lightweight session data modification."""

    def make_session(self):
        return {
            "_report_version": 0,
            "research_result": {
                "topic": "旧标题",
                "report": {
                    "sections": [
                        {
                            "id": "sec1",
                            "title": "第一章",
                            "content": "2026年玉米市场分析报告指出，玉米价格波动较大。",
                            "subsections": [
                                {"title": "1.1", "content": "玉米的供需关系正在发生变化，玉米库存增加。"}
                            ]
                        },
                        {
                            "id": "sec2",
                            "title": "第二章",
                            "content": "大豆市场同样受到影响，价格平稳。",
                        }
                    ]
                }
            }
        }

    def make_action(self, op_type, content=None, **params):
        from unittest.mock import MagicMock
        action = MagicMock()
        action.action_type = MagicMock()
        action.action_type.value = op_type
        action.content = content
        action.parameters = params
        return action

    def test_update_title(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("update_title", content="玉米价格趋势研究")
        api._apply_lightweight(session, action)
        assert session["research_result"]["topic"] == "玉米价格趋势研究"
        assert session["research_result"]["report"]["topic"] == "玉米价格趋势研究"
        assert session["_report_version"] == 1

    def test_update_title_empty_content(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("update_title", content=None)
        api._apply_lightweight(session, action)
        assert session["research_result"]["topic"] == "旧标题"

    def test_replace_text(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("replace_text", content="大豆", old_text="玉米")
        api._apply_lightweight(session, action)
        sec0 = session["research_result"]["report"]["sections"][0]
        assert "大豆" in sec0["content"]
        assert "玉米" not in sec0["content"]
        assert "大豆" in sec0["subsections"][0]["content"]
        assert "玉米" not in sec0["subsections"][0]["content"]

    def test_change_case_upper(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("change_case", case_style="upper")
        api._apply_lightweight(session, action)
        content = session["research_result"]["report"]["sections"][0]["content"]
        assert content == "2026年玉米市场分析报告指出，玉米价格波动较大。".upper()

    def test_change_case_lower(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("change_case", case_style="lower")
        api._apply_lightweight(session, action)
        content = session["research_result"]["report"]["sections"][0]["content"]
        assert content == "2026年玉米市场分析报告指出，玉米价格波动较大。".lower()

    def test_fix_punctuation_cn2en(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        action = self.make_action("fix_punctuation", punct_rule="cn2en")
        api._apply_lightweight(session, action)
        content = session["research_result"]["report"]["sections"][0]["content"]
        assert "，" not in content
        assert "," in content
        assert "。" not in content
        assert "." in content

    def test_version_increment(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = self.make_session()
        assert session["_report_version"] == 0
        action = self.make_action("replace_text", content="大豆", old_text="玉米")
        api._apply_lightweight(session, action)
        assert session["_report_version"] == 1
        api._apply_lightweight(session, action)
        assert session["_report_version"] == 2


class TestRecursiveTraverse:
    """Test _recursive_traverse_sections"""

    def test_all_levels_visited(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        visited = []

        def collect(sec):
            visited.append(sec.get("content", ""))

        sections = [
            {"content": "L1", "subsections": [
                {"content": "L2", "subsections": [
                    {"content": "L3"}
                ]}
            ]},
        ]
        api._recursive_traverse_sections(sections, collect)
        assert visited == ["L1", "L2", "L3"], f"got {visited}"

    def test_empty_sections(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        visited = []
        api._recursive_traverse_sections([], lambda s: visited.append(1))
        assert visited == []

    def test_non_dict_entries_skipped(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        visited = []
        sections = ["string", 42, {"content": "valid"}]
        api._recursive_traverse_sections(sections, lambda s: visited.append(s["content"]))
        assert visited == ["valid"]


class TestLightweightMessage:
    """Test _lightweight_message output"""

    def make_action(self, op_type, content=None, **params):
        from unittest.mock import MagicMock
        action = MagicMock()
        action.action_type = MagicMock()
        action.action_type.value = op_type
        action.content = content
        action.parameters = params
        return action

    def test_update_title_message(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        action = self.make_action("update_title", content="新标题")
        msg = api._lightweight_message(action)
        assert "新标题" in msg

    def test_replace_text_message(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        action = self.make_action("replace_text", content="大豆", old_text="玉米")
        msg = api._lightweight_message(action)
        assert "玉米" in msg
        assert "大豆" in msg

    def test_change_case_message(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        action = self.make_action("change_case", case_style="upper")
        msg = api._lightweight_message(action)
        assert "大写" in msg

    def test_fix_punctuation_message(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        action = self.make_action("fix_punctuation", punct_rule="cn2en")
        msg = api._lightweight_message(action)
        assert "标点" in msg

    def test_unknown_op_type(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        action = self.make_action("unknown_op")
        msg = api._lightweight_message(action)
        assert msg == "修订已应用。"


class TestMarkdownTableParser:
    """Test MarkdownTableParser"""

    def test_find_tables(self):
        from src.core.adjustment.markdown_table_parser import MarkdownTableParser
        content = (
            "| 年份 | 产量 |\n"
            "|------|------|\n"
            "| 2024 | 1500 |\n"
            "| 2025 | 1800 |\n"
        )
        tables = MarkdownTableParser.find_tables(content)
        assert len(tables) == 1
        assert tables[0]["header"] == ["年份", "产量"]
        assert len(tables[0]["rows"]) == 2
        assert tables[0]["rows"][0]["cells"] == ["2024", "1500"]

    def test_find_no_tables(self):
        from src.core.adjustment.markdown_table_parser import MarkdownTableParser
        tables = MarkdownTableParser.find_tables("纯文本内容，没有表格")
        assert tables == []

    def test_set_cell(self):
        from src.core.adjustment.markdown_table_parser import MarkdownTableParser
        content = (
            "| 年份 | 产量 |\n"
            "|------|------|\n"
            "| 2024 | 1500 |\n"
        )
        result = MarkdownTableParser.set_cell(content, 0, 0, 1, "1600")
        assert "1600" in result
        # _cells() 做 strip，所以分隔符 | 之间的空格会被去掉
        assert "|2024|1600|" in result

    def test_multiple_tables(self):
        from src.core.adjustment.markdown_table_parser import MarkdownTableParser
        # 两个表格之间必须空行分隔才能被 regex 识别为两个独立的表格块
        content = (
            "前文\n"
            "\n"
            "| A | B |\n"
            "|---|---|\n"
            "| a | b |\n"
            "\n"
            "| C | D |\n"
            "|---|---|\n"
            "| c | d |\n"
        )
        tables = MarkdownTableParser.find_tables(content)
        assert len(tables) == 2

    def test_table_with_alignments(self):
        from src.core.adjustment.markdown_table_parser import MarkdownTableParser
        content = (
            "| 左 | 中 | 右 |\n"
            "|:---|:---:|---:|\n"
            "| 1  | 2  | 3  |\n"
        )
        tables = MarkdownTableParser.find_tables(content)
        assert len(tables) == 1
        assert tables[0]["header"] == ["左", "中", "右"]
        assert tables[0]["rows"][0]["cells"] == ["1", "2", "3"]


class TestImageParser:
    """Test ImageParser"""

    def test_find_images(self):
        from src.core.adjustment.markdown_table_parser import ImageParser
        content = "前文 ![价格趋势图](chart.png) 后文"
        images = ImageParser.find_images(content)
        assert len(images) == 1
        assert images[0]["alt"] == "价格趋势图"
        assert images[0]["src"] == "chart.png"

    def test_find_no_images(self):
        from src.core.adjustment.markdown_table_parser import ImageParser
        images = ImageParser.find_images("纯文本，没有图片")
        assert images == []

    def test_multiple_images(self):
        from src.core.adjustment.markdown_table_parser import ImageParser
        content = "![图1](a.png) 文字 ![图2](b.png)"
        images = ImageParser.find_images(content)
        assert len(images) == 2
        assert images[0]["src"] == "a.png"
        assert images[1]["src"] == "b.png"

    def test_image_without_alt(self):
        from src.core.adjustment.markdown_table_parser import ImageParser
        images = ImageParser.find_images("![](img.png)")
        assert len(images) == 1
        assert images[0]["alt"] == ""

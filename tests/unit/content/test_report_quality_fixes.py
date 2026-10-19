# -*- coding: utf-8 -*-
"""
报告质量修复测试
================

针对 report_quality_analysis_and_fix_plan.md 中列出的 P0-P3 问题编写测试。
测试先于修复编写（TDD），确保修复后所有测试通过。

覆盖问题：
P0-1: Markdown语法未转换（####, 列表-, 有序列表1., 引用>）
P0-2: 围栏代码块 ``` 不识别（含JSON代码块提取）
P0-3: 标题解析误判（数字+粗体被误判为标题）+ 无意义标题
P1-1: 模板变量 labels 缺失
P1-3: 数据表格双重渲染
P3-2: HTML实体二次转义
"""

import pytest
from src.content.content_orchestrator import ContentOrchestrator


class TestContentToHtml_MarkdownList:
    """P0-1: 无序列表解析"""

    def test_unordered_list_dash(self):
        """- item 格式应转为 <ul><li>"""
        content = "- 第一项\n- 第二项\n- 第三项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" in html
        assert "<li>" in html
        assert "第一项" in html
        assert "第二项" in html
        assert "- 第一项" not in html

    def test_unordered_list_asterisk(self):
        """* item 格式应转为 <ul><li>"""
        content = "* 第一项\n* 第二项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" in html
        assert "<li>" in html
        assert "第一项" in html

    def test_unordered_list_with_bold(self):
        """- **粗体** 内容"""
        content = "- **中低端市场**（客单价<200元）：描述文字"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" in html
        assert "<li>" in html
        assert "<strong>" in html
        assert "- **" not in html


class TestContentToHtml_OrderedList:
    """P0-1: 有序列表解析"""

    def test_ordered_list(self):
        """1. item 格式应转为 <ol><li>"""
        content = "1. 第一项\n2. 第二项\n3. 第三项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert "<li>" in html
        assert "第一项" in html
        assert "1. 第一项" not in html

    def test_ordered_list_with_bold(self):
        """1. **风险**：描述 不应被误判为标题"""
        content = "1. **市场规模测算假设风险**：当前市场规模估算依赖于行业公开报告\n2. **消费者行为变化风险**：儿童乐园属于非刚性消费"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert "<li>" in html
        assert "<strong>" in html
        assert "1. **" not in html


class TestContentToHtml_Blockquote:
    """P0-1: 引用块解析"""

    def test_blockquote(self):
        """> text 格式应转为 <blockquote>"""
        content = "> **注：** 上表所列数据为多源交叉验证后的参考区间。"
        html = ContentOrchestrator._content_to_html(content)
        assert "<blockquote" in html
        assert "注：" in html
        assert "&gt;" not in html

    def test_multiline_blockquote(self):
        """多行引用"""
        content = "> 第一行\n> 第二行"
        html = ContentOrchestrator._content_to_html(content)
        assert "<blockquote" in html
        assert "第一行" in html
        assert "第二行" in html


class TestContentToHtml_HeadingLevels:
    """P0-1: 四级及以上标题"""

    def test_h4_heading(self):
        """#### 标题 应转为 <h5>（在章节内 # → h2, ## → h3, ### → h4, #### → h5）"""
        content = "#### 论证与分析"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h5" in html
        assert "论证与分析" in html
        assert "####" not in html

    def test_h5_heading(self):
        """##### 标题"""
        content = "##### 子标题"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h6" in html
        assert "#####" not in html


class TestContentToHtml_FencedCodeBlock:
    """P0-2: 围栏代码块"""

    def test_json_code_block_extract_content(self):
        """```json 包含 content 字段时应提取内容"""
        content = '```json\n{"title": "测试", "content": "这是实际内容"}\n```'
        html = ContentOrchestrator._content_to_html(content)
        assert "这是实际内容" in html
        assert "```" not in html
        assert '"title"' not in html

    def test_json_code_block_without_content(self):
        """```json 不含 content 字段时应渲染为代码块"""
        content = '```json\n{"key": "value"}\n```'
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html or "<code>" in html
        assert "```" not in html

    def test_plain_code_block(self):
        """``` 不带语言标识应渲染为代码块"""
        content = '```\nsome code\n```'
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html
        assert "```" not in html

    def test_json_with_self_check_fields(self):
        """JSON含 self_check_passed 等调试字段时应提取content而非原样输出"""
        json_content = (
            '```json\n'
            '{"title": "画像分析", "content": "家长决策以安全为首要因素", '
            '"self_check_passed": true, "self_check_issues": []}\n'
            '```'
        )
        html = ContentOrchestrator._content_to_html(json_content)
        assert "家长决策以安全为首要因素" in html
        assert "self_check_passed" not in html


class TestParseMarkdownTitle_NumberedBold:
    """P0-3: 数字编号+粗体不应被误判为标题"""

    def test_numbered_bold_not_title(self):
        """1. **xxx** 不应被识别为标题"""
        content = "1. **市场规模测算假设风险**：当前市场规模估算依赖于行业公开报告\n\n后续段落。"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is None
        assert "1. **市场规模" in result["body"]

    def test_numbered_plain_is_title(self):
        """1. 纯文字标题 仍应被识别为标题"""
        content = "1. 市场规模\n\n后续段落。"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] == "市场规模"


class TestContentCleaner_BlacklistTitle:
    """P0-3: 无意义标题应被清洗"""

    def test_blacklist_title_cleaned(self):
        """'章节内容' 等无意义标题应被清空"""
        from src.content.content_cleaner import clean_section
        data = {"title": "章节内容", "content": "实际内容"}
        cleaned = clean_section(data)
        assert cleaned["title"] == ""

    def test_normal_title_preserved(self):
        """正常标题应保留"""
        from src.content.content_cleaner import clean_section
        data = {"title": "市场规模分析", "content": "实际内容"}
        cleaned = clean_section(data)
        assert cleaned["title"] == "市场规模分析"

    def test_json_content_extracted(self):
        """JSON代码块中的content字段应被提取"""
        from src.content.content_cleaner import clean_section
        data = {
            "title": "画像分析",
            "content": '```json\n{"content": "实际分析内容"}\n```'
        }
        cleaned = clean_section(data)
        assert "实际分析内容" in cleaned["content"]
        assert "```" not in cleaned["content"]


class TestTemplateVariables_Labels:
    """P1-1: 模板变量 labels 应被设置"""

    def test_labels_in_variables(self):
        """_prepare_template_variables 应包含 labels.toc"""
        orchestrator = ContentOrchestrator()
        research_result = {
            "title": "测试报告",
            "sections": [
                {"id": "s1", "title": "第一章", "content": "内容", "order": 0}
            ]
        }
        variables = orchestrator._prepare_template_variables(
            title="测试报告",
            sections=orchestrator._parse_sections(research_result["sections"]),
            key_findings=[],
            data_points=[],
            research_result=research_result,
            output_format="html"
        )
        assert "labels" in variables
        assert variables["labels"].get("toc") not in ("", None)


class TestDoubleTableRendering:
    """P1-3: 数据表格不应双重渲染"""

    def test_no_section_tables_when_content_has_table(self):
        """当 section.content 已包含 <table 时，不应再生成 section_tables"""
        orchestrator = ContentOrchestrator()
        research_result = {
            "title": "测试",
            "sections": [
                {
                    "id": "s1",
                    "title": "数据分析",
                    "content": "| 指标 | 数值 |\n|------|------|\n| 营收 | 100 |",
                    "order": 0,
                    "data_points": [
                        {"metric": "营收", "value": "100", "unit": "亿元"}
                    ]
                }
            ]
        }
        sections = orchestrator._parse_sections(research_result["sections"])
        variables = orchestrator._prepare_template_variables(
            title="测试",
            sections=sections,
            key_findings=[],
            data_points=[],
            research_result=research_result,
            output_format="docx"
        )
        section_data = variables["sections"][0]
        if "<table" in section_data.get("content", ""):
            assert section_data.get("tables") == [] or section_data.get("tables") is None


class TestInlineMarkdown_EntityEscape:
    """P3-2: HTML实体不应二次转义"""

    def test_existing_html_entity_preserved(self):
        """已有的 HTML 实体 &lt; 应保留，不变成 &amp;lt;"""
        text = "客单价&lt;200元"
        result = ContentOrchestrator._inline_markdown(text)
        assert "&lt;" in result
        assert "&amp;lt;" not in result

    def test_less_than_in_plain_text_escaped(self):
        """纯文本的 < 应被转义为 &lt;"""
        text = "HHI<1000"
        result = ContentOrchestrator._inline_markdown(text)
        assert "&lt;" in result

    def test_amp_entity_preserved(self):
        """&amp; 实体应保留"""
        text = "A &amp; B"
        result = ContentOrchestrator._inline_markdown(text)
        assert "&amp;" in result
        assert "&amp;amp;" not in result


class TestContentToHtml_Regression:
    """回归测试：确保已有功能不受影响"""

    def test_markdown_table_still_works(self):
        """Markdown 表格仍应正常转换"""
        content = "| 指标 | 数值 |\n|------|------|\n| 营收 | 100 |"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html
        assert "营收" in html

    def test_heading_h1_h2_h3_still_works(self):
        """# / ## / ### 仍应正常转换"""
        content = "# 一级标题\n## 二级标题\n### 三级标题"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h2" in html
        assert "<h3" in html
        assert "<h4" in html

    def test_html_table_preserved(self):
        """HTML <table> 块应保留"""
        content = "<table>\n<tr><td>数据</td></tr>\n</table>"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table>" in html
        assert "数据" in html

    def test_inline_bold_italic(self):
        """粗体和斜体仍应正常"""
        content = "**粗体** 和 *斜体*"
        html = ContentOrchestrator._content_to_html(content)
        assert "<strong>粗体</strong>" in html
        assert "<em>斜体</em>" in html

    def test_chinese_numbered_heading(self):
        """中文编号标题仍应正常"""
        content = "一、市场规模分析\n\n后续内容"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h3" in html
        assert "市场规模分析" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

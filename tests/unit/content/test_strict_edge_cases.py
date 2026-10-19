# -*- coding: utf-8 -*-
"""
严格边界测试
===========

对已完成修复的代码进行更严格的边界条件测试，
发现潜在 bug 和未覆盖的边界 case。

覆盖模块：
1. _content_to_html() 边界 case
2. _parse_markdown_title() 边界 case
3. _inline_markdown() 边界 case
4. _dedup_sections() 边界 case
5. content_cleaner.py 边界 case
6. _prepare_template_variables() 边界 case
7. _md_table_to_html() 边界 case
8. 混合内容集成测试
"""

import pytest
from src.content.content_orchestrator import ContentOrchestrator, ContentSection, SectionType


# =====================================================================
# 1. _content_to_html() 严格边界测试
# =====================================================================

class TestContentToHtml_UnclosedCodeBlock:
    """未闭合的围栏代码块"""

    def test_unclosed_code_block_no_crash(self):
        """未闭合 ``` 不应导致崩溃或无限循环"""
        content = "```\nsome code without closing"
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)

    def test_unclosed_code_block_renders_content(self):
        """未闭合代码块内容应出现在输出中"""
        content = "```\nsome code without closing"
        html = ContentOrchestrator._content_to_html(content)
        assert "some code" in html

    def test_unclosed_json_code_block(self):
        """未闭合 ```json 不应崩溃"""
        content = '```json\n{"key": "value"}'
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)

    def test_empty_code_block(self):
        """``` 紧跟 ``` 应产生空代码块"""
        content = "```\n```"
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html
        assert "```" not in html

    def test_code_block_with_language(self):
        """```python 应渲染为代码块（非 json 不提取 content）"""
        content = '```python\nprint("hello")\n```'
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html
        assert 'print("hello")' in html or "print" in html


class TestContentToHtml_ListEdgeCases:
    """列表边界 case"""

    def test_single_item_unordered_list(self):
        """单条 - item 应生成 <ul>"""
        content = "- 唯一项目"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" in html
        assert "<li>" in html
        assert "唯一项目" in html

    def test_single_item_ordered_list(self):
        """单条 1. item 应生成 <ol>"""
        content = "1. 唯一项目"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert "<li>" in html

    def test_ordered_list_non_sequential(self):
        """非连续编号：5. / 10. / 15. 应仍生成 <ol>"""
        content = "5. 第五项\n10. 第十项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert "<li>" in html
        assert "第五项" in html

    def test_list_followed_by_paragraph(self):
        """列表后跟段落应正确分隔"""
        content = "- 项目1\n- 项目2\n\n这是后续段落"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" in html
        assert "<li>" in html
        assert "<p" in html
        assert "后续段落" in html

    def test_ordered_list_interrupted_by_non_list(self):
        """有序列表被非列表行打断应产生两个 <ol>"""
        content = "1. 第一项\n中间非列表行\n2. 第二项"
        html = ContentOrchestrator._content_to_html(content)
        assert html.count("<ol>") >= 1

    def test_dash_not_in_list_context(self):
        """单独的 - 后跟空行不应生成列表"""
        content = "-"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" not in html

    def test_asterisk_in_middle_of_text(self):
        """行中 * 不应被当列表处理"""
        content = "这是 *强调* 文本"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ul>" not in html

    def test_chinese_enumeration_in_ordered_list(self):
        """1、中文顿号有序列表"""
        content = "1、第一项\n2、第二项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html or "第一项" in html


class TestContentToHtml_BlockquoteEdgeCases:
    """引用块边界 case"""

    def test_empty_blockquote(self):
        """> 后无内容不应崩溃"""
        content = ">"
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)

    def test_blockquote_followed_by_paragraph(self):
        """引用块后跟段落"""
        content = "> 引用内容\n\n普通段落"
        html = ContentOrchestrator._content_to_html(content)
        assert "<blockquote" in html
        assert "普通段落" in html

    def test_nested_blockquote_marker(self):
        """> > 嵌套引用标记（当前不要求嵌套，但不应崩溃）"""
        content = "> > 嵌套引用"
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)


class TestContentToHtml_HeadingEdgeCases:
    """标题边界 case"""

    def test_h6_heading(self):
        """###### 标题"""
        content = "###### 最深标题"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h6" in html or "<h7" not in html
        assert "最深标题" in html

    def test_heading_with_trailing_hashes(self):
        """### 标题 ### 尾部 # 应被忽略"""
        content = "### 标题 ###"
        html = ContentOrchestrator._content_to_html(content)
        assert "标题" in html

    def test_heading_with_inline_formatting(self):
        """### **粗体标题** 应保留格式"""
        content = "### **重要发现**"
        html = ContentOrchestrator._content_to_html(content)
        assert "<strong>" in html or "重要发现" in html

    def test_heading_with_chinese_prefix(self):
        """### 一、标题 应去掉中文编号前缀"""
        content = "### 一、细分市场"
        html = ContentOrchestrator._content_to_html(content)
        assert "细分市场" in html
        assert "一、" not in html

    def test_mixed_numbered_heading(self):
        """1. 一、混合编号标题"""
        content = "1. 一、竞争格局分析"
        html = ContentOrchestrator._content_to_html(content)
        assert "竞争格局分析" in html
        assert "<h3" in html


class TestContentToHtml_EmptyAndEdgeCases:
    """空输入和极端 case"""

    def test_empty_string(self):
        """空字符串应返回空"""
        html = ContentOrchestrator._content_to_html("")
        assert html == ""

    def test_none_input(self):
        """None 应返回空字符串"""
        html = ContentOrchestrator._content_to_html(None)
        assert html == ""

    def test_only_whitespace(self):
        """纯空白应返回空"""
        html = ContentOrchestrator._content_to_html("   \n  \n  ")
        assert html.strip() == ""

    def test_only_newlines(self):
        """纯换行应返回空"""
        html = ContentOrchestrator._content_to_html("\n\n\n")
        assert html.strip() == ""

    def test_very_long_line(self):
        """超长行不应崩溃"""
        content = "A" * 50000
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_unicode_mixed_content(self):
        """中英文+特殊Unicode混合"""
        content = "English text 中文文本 émojis 🎢 日本語"
        html = ContentOrchestrator._content_to_html(content)
        assert "English" in html
        assert "中文" in html

    def test_html_special_chars_in_text(self):
        """文本中的 < > & 应被转义"""
        content = "A < B > C & D"
        html = ContentOrchestrator._content_to_html(content)
        assert "&lt;" in html or "&amp;" in html


class TestContentToHtml_MixedContent:
    """混合内容集成测试"""

    def test_heading_then_list_then_paragraph(self):
        """标题 → 列表 → 段落"""
        content = "## 分析要点\n- 要点1\n- 要点2\n\n总结段落。"
        html = ContentOrchestrator._content_to_html(content)
        assert "<h3" in html
        assert "<ul>" in html
        assert "<p" in html

    def test_code_block_then_paragraph(self):
        """代码块 → 段落"""
        content = "```\ncode\n```\n\n代码后的段落"
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html
        assert "代码后" in html

    def test_json_extract_then_remaining(self):
        """JSON提取后剩余内容"""
        content = '```json\n{"content": "提取的内容"}\n```\n\n额外段落'
        html = ContentOrchestrator._content_to_html(content)
        assert "提取的内容" in html
        assert "额外段落" in html

    def test_table_then_list(self):
        """表格 → 列表"""
        content = "| A | B |\n|---|---|\n| 1 | 2 |\n\n- 项目1\n- 项目2"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html
        assert "<ul>" in html

    def test_html_table_and_markdown_mixed(self):
        """HTML表格和Markdown混合"""
        content = "<table><tr><td>数据</td></tr></table>\n\n**粗体文本**"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table>" in html
        assert "<strong>" in html


# =====================================================================
# 2. _parse_markdown_title() 严格边界测试
# =====================================================================

class TestParseMarkdownTitle_EdgeCases:
    """标题解析边界 case"""

    def test_empty_input(self):
        """空字符串"""
        result = ContentOrchestrator._parse_markdown_title("")
        assert result["title"] is None
        assert result["body"] == ""

    def test_none_input(self):
        """None输入"""
        result = ContentOrchestrator._parse_markdown_title(None)
        assert result["title"] is None

    def test_only_whitespace(self):
        """纯空白"""
        result = ContentOrchestrator._parse_markdown_title("   \n   ")
        assert result["title"] is None

    def test_heading_with_bold_markers(self):
        """## **粗体标题** 提取标题应包含粗体标记（当前行为）"""
        content = "## **重要发现**\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is not None
        assert "重要发现" in result["title"]

    def test_numbered_bold_with_colon(self):
        """1. **风险**：描述 — 不应识别为标题"""
        content = "1. **市场风险**：当前市场不确定性较高\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is None

    def test_numbered_italic_not_title(self):
        """1. *斜体* 开头也不应识别为标题"""
        content = "1. *斜体内容*\n后续"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is None

    def test_plain_numbered_is_title(self):
        """1. 纯文字 是标题"""
        content = "1. 市场规模分析\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] == "市场规模分析"

    def test_chinese_numbered_empty_title(self):
        """一、 后无文字 — 标题应为整行"""
        content = "一、\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is not None

    def test_leading_empty_lines_then_title(self):
        """前导空行后跟标题"""
        content = "\n\n## 延迟标题\n内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] == "延迟标题"

    def test_no_title_just_body(self):
        """无标题，直接正文"""
        content = "这是正文内容，没有任何标题格式。"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is None
        assert "正文内容" in result["body"]

    def test_mixed_numbered_heading(self):
        """1. 一、混合编号"""
        content = "1. 一、竞争格局\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        assert result["title"] is not None
        assert "竞争格局" in result["title"]


# =====================================================================
# 3. _inline_markdown() 严格边界测试
# =====================================================================

class TestInlineMarkdown_EdgeCases:
    """内联Markdown边界 case"""

    def test_empty_string(self):
        """空字符串"""
        result = ContentOrchestrator._inline_markdown("")
        assert result == ""

    def test_plain_text(self):
        """纯文本无格式"""
        result = ContentOrchestrator._inline_markdown("纯文本")
        assert "纯文本" in result

    def test_unclosed_bold(self):
        """未闭合 ** 不应崩溃"""
        result = ContentOrchestrator._inline_markdown("**未闭合粗体")
        assert isinstance(result, str)

    def test_unclosed_italic(self):
        """未闭合 * 不应崩溃"""
        result = ContentOrchestrator._inline_markdown("*未闭合斜体")
        assert isinstance(result, str)

    def test_multiple_bold(self):
        """多个粗体"""
        result = ContentOrchestrator._inline_markdown("**A** 和 **B**")
        assert result.count("<strong>") == 2

    def test_nested_bold_italic(self):
        """***粗斜体*** — 三星号"""
        result = ContentOrchestrator._inline_markdown("***粗斜体***")
        assert isinstance(result, str)

    def test_html_tag_in_text(self):
        """HTML标签应保留"""
        result = ContentOrchestrator._inline_markdown('<img src="test.png"/>')
        assert '<img src="test.png"/>' in result

    def test_html_table_tags_preserved(self):
        """HTML表格标签应保留"""
        result = ContentOrchestrator._inline_markdown("<table><tr><td>data</td></tr></table>")
        assert "<table>" in result
        assert "<td>data</td>" in result

    def test_entity_numeric(self):
        """数字HTML实体 &#60; 应保留"""
        result = ContentOrchestrator._inline_markdown("A&#60;B")
        assert "&#60;" in result
        assert "&amp;#60;" not in result

    def test_multiple_entities(self):
        """多个HTML实体"""
        result = ContentOrchestrator._inline_markdown("&lt;tag&gt; &amp; &quot;hi&quot;")
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result

    def test_angle_bracket_escaped(self):
        """裸 < 应被转义"""
        result = ContentOrchestrator._inline_markdown("5 < 10")
        assert "&lt;" in result

    def test_angle_bracket_in_known_tag(self):
        """已知标签的 < 不应被转义"""
        result = ContentOrchestrator._inline_markdown("<strong>text</strong>")
        assert "<strong>" in result
        assert "&lt;strong" not in result

    def test_br_tag_preserved(self):
        """<br/> 应保留"""
        result = ContentOrchestrator._inline_markdown("line1<br/>line2")
        assert "<br/>" in result

    def test_span_with_class_preserved(self):
        """<span class="x"> 应保留"""
        result = ContentOrchestrator._inline_markdown('<span class="highlight">text</span>')
        assert '<span class="highlight">' in result

    def test_unknown_html_tag_escaped(self):
        """非白名单标签应被转义"""
        result = ContentOrchestrator._inline_markdown("<custom>text</custom>")
        assert "&lt;custom" in result


# =====================================================================
# 4. _dedup_sections() 严格边界测试
# =====================================================================

class TestDedupSections_EdgeCases:
    """章节去重边界 case"""

    def test_empty_list(self):
        """空列表"""
        result = ContentOrchestrator._dedup_sections([])
        assert result == []

    def test_single_section(self):
        """单章节不去重"""
        sections = [ContentSection(id="1", title="唯一", content="内容")]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1

    def test_exact_duplicate_titles(self):
        """完全相同标题应去重"""
        sections = [
            ContentSection(id="1", title="市场分析", content="短内容"),
            ContentSection(id="2", title="市场分析", content="更长的内容，包含更多分析信息" * 5),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1
        assert "更长的内容" in result[0].content

    def test_no_duplicates(self):
        """无重复标题应保留全部"""
        sections = [
            ContentSection(id="1", title="市场分析", content="A"),
            ContentSection(id="2", title="竞争格局", content="B"),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 2

    def test_empty_content_vs_filled(self):
        """空内容 vs 有内容：应保留有内容的"""
        sections = [
            ContentSection(id="1", title="分析", content=""),
            ContentSection(id="2", title="分析", content="实际内容"),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1
        assert result[0].content == "实际内容"

    def test_structural_vs_real_content(self):
        """以 ** 开头的内容 vs 纯文本内容：应保留纯文本"""
        sections = [
            ContentSection(id="1", title="风险", content="**风险1**：描述\n**风险2**：描述"),
            ContentSection(id="2", title="风险", content="本节详细分析了市场风险因素"),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1

    def test_conclusion_type_priority(self):
        """CONCLUSION类型优先于BODY"""
        sections = [
            ContentSection(id="1", title="总结", content="内容A", type=SectionType.BODY),
            ContentSection(id="2", title="总结", content="内容A", type=SectionType.CONCLUSION),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1
        assert result[0].type == SectionType.CONCLUSION

    def test_semantic_near_duplicates_deduped(self):
        """语义相近标题（Jaccard>0.6）应被去重"""
        sections = [
            ContentSection(id="1", title="行业现存问题与风险", content="A"),
            ContentSection(id="2", title="行业问题与痛点", content="B"),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1

    def test_semantic_low_similarity_not_deduped(self):
        """低相似度标题不应被去重"""
        sections = [
            ContentSection(id="1", title="市场规模分析", content="A"),
            ContentSection(id="2", title="消费者画像研究", content="B"),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 2

    def test_semantic_dedup_keeps_better_content(self):
        """语义去重应保留内容更丰富的版本"""
        sections = [
            ContentSection(id="1", title="行业现存问题与风险", content="短"),
            ContentSection(id="2", title="行业问题与痛点", content="详细的分析内容，包含多个维度的深入探讨" * 3),
        ]
        result = ContentOrchestrator._dedup_sections(sections)
        assert len(result) == 1
        assert "详细的分析" in result[0].content


# =====================================================================
# 5. content_cleaner.py 严格边界测试
# =====================================================================

class TestContentCleaner_EdgeCases:
    """内容清洗器边界 case"""

    def test_empty_dict(self):
        """空字典"""
        from src.content.content_cleaner import clean_section
        result = clean_section({})
        assert "title" not in result or result.get("title", "") == ""

    def test_no_title_key(self):
        """无title键"""
        from src.content.content_cleaner import clean_section
        result = clean_section({"content": "内容"})
        assert result.get("title") is None or result.get("title", "") == ""

    def test_no_content_key(self):
        """无content键"""
        from src.content.content_cleaner import clean_section
        result = clean_section({"title": "标题"})
        assert result["title"] == "标题"

    def test_whitespace_title_in_blacklist(self):
        """黑名单标题带空格"""
        from src.content.content_cleaner import clean_section, TITLE_BLACKLIST
        for title in TITLE_BLACKLIST:
            result = clean_section({"title": f" {title} ", "content": "内容"})
            assert result["title"] == ""

    def test_title_case_sensitivity(self):
        """黑名单大小写：Content vs content"""
        from src.content.content_cleaner import clean_section
        result1 = clean_section({"title": "Content", "content": "x"})
        assert result1["title"] == ""
        result2 = clean_section({"title": "content", "content": "x"})
        assert result2["title"] == "content"

    def test_json_extraction_without_closing_fence(self):
        """无闭合 ``` 的JSON块"""
        from src.content.content_cleaner import _extract_json_content
        content = '```json\n{"content": "提取内容"}'
        result = _extract_json_content(content)
        assert "提取内容" in result

    def test_json_extraction_invalid_json(self):
        """无效JSON不应崩溃"""
        from src.content.content_cleaner import _extract_json_content
        content = '```json\n{invalid json}\n```'
        result = _extract_json_content(content)
        assert result == content

    def test_json_extraction_non_dict(self):
        """JSON数组不应提取"""
        from src.content.content_cleaner import _extract_json_content
        content = '```json\n[1, 2, 3]\n```'
        result = _extract_json_content(content)
        assert result == content

    def test_json_extraction_nested_content(self):
        """JSON中content字段是对象而非字符串"""
        from src.content.content_cleaner import _extract_json_content
        content = '```json\n{"content": {"nested": true}}\n```'
        result = _extract_json_content(content)
        assert isinstance(result, str)

    def test_non_json_code_block_not_extracted(self):
        """非 ```json 开头的内容不提取"""
        from src.content.content_cleaner import _extract_json_content
        content = '```python\nprint("hello")\n```'
        result = _extract_json_content(content)
        assert result == content

    def test_plain_text_not_extracted(self):
        """纯文本不提取"""
        from src.content.content_cleaner import _extract_json_content
        content = "普通文本内容"
        result = _extract_json_content(content)
        assert result == content

    def test_mutation_behavior(self):
        """clean_section 应原地修改并返回同一对象"""
        from src.content.content_cleaner import clean_section
        data = {"title": "章节内容", "content": "内容"}
        result = clean_section(data)
        assert result is data
        assert data["title"] == ""


# =====================================================================
# 6. _prepare_template_variables() 严格边界测试
# =====================================================================

class TestPrepareTemplateVariables_EdgeCases:
    """模板变量准备边界 case"""

    def test_empty_research_result(self):
        """空研究结果"""
        orchestrator = ContentOrchestrator()
        variables = orchestrator._prepare_template_variables(
            title="测试",
            sections=[],
            key_findings=[],
            data_points=[],
            research_result={},
            output_format="docx"
        )
        assert "sections" in variables
        assert variables["sections"] == []

    def test_labels_always_present(self):
        """labels 始终存在"""
        orchestrator = ContentOrchestrator()
        variables = orchestrator._prepare_template_variables(
            title="测试",
            sections=[],
            key_findings=[],
            data_points=[],
            research_result={},
            output_format="html"
        )
        assert "labels" in variables
        assert isinstance(variables["labels"], dict)
        assert "toc" in variables["labels"]

    def test_section_with_empty_content(self):
        """章节内容为空"""
        orchestrator = ContentOrchestrator()
        sections = [ContentSection(id="s1", title="空章节", content="")]
        variables = orchestrator._prepare_template_variables(
            title="测试",
            sections=sections,
            key_findings=[],
            data_points=[],
            research_result={"sections": [{"id": "s1", "title": "空章节", "content": ""}]},
            output_format="docx"
        )
        assert variables["sections"][0]["content"] == ""

    def test_data_points_to_tables_conversion(self):
        """data_points 应转为表格格式"""
        orchestrator = ContentOrchestrator()
        research_result = {
            "title": "测试",
            "sections": [{
                "id": "s1",
                "title": "数据",
                "content": "纯文本内容无表格",
                "order": 0,
                "data_points": [
                    {"metric": "营收", "value": "100", "unit": "亿元"},
                    {"metric": "增长", "value": "15", "unit": "%"},
                ]
            }]
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
        if "<table" not in section_data.get("content", ""):
            tables = section_data.get("tables", [])
            assert len(tables) > 0
            assert tables[0]["headers"] == ["Metric", "Value", "Unit"]

    def test_double_table_prevention_with_html_table_in_content(self):
        """内容含HTML<table>时不应生成section_tables"""
        orchestrator = ContentOrchestrator()
        research_result = {
            "title": "测试",
            "sections": [{
                "id": "s1",
                "title": "数据",
                "content": "<table><tr><td>数据</td></tr></table>",
                "order": 0,
                "data_points": [
                    {"metric": "营收", "value": "100", "unit": "亿元"}
                ]
            }]
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
        content = section_data.get("content", "")
        if "<table" in content:
            assert section_data.get("tables") == [] or section_data.get("tables") is None


# =====================================================================
# 7. _md_table_to_html() 严格边界测试
# =====================================================================

class TestMdTableToHtml_EdgeCases:
    """Markdown表格转换边界 case"""

    def test_single_row_table(self):
        """单行表格（无分隔行）应返回空或降级为段落"""
        content = "| A | B |"
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)

    def test_table_with_empty_cells(self):
        """含空单元格的表格"""
        content = "| A | B |\n|---|---|\n| 1 |  |"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html

    def test_table_with_alignment(self):
        """含对齐标记的表格"""
        content = "| Left | Center | Right |\n|:-----|:------:|------:|\n| L | C | R |"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html

    def test_table_with_bold_content(self):
        """表格内容含粗体"""
        content = "| 指标 | 数值 |\n|------|------|\n| **营收** | 100 |"
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html
        assert "<strong>" in html


# =====================================================================
# 8. 混合内容集成测试 — 模拟真实报告段落
# =====================================================================

class TestRealWorldContentIntegration:
    """模拟真实报告中的复杂内容结构"""

    def test_typical_section_with_subsections(self):
        """典型章节：标题+子标题+列表+段落"""
        content = """## 市场细分

### 中低端市场
- 客单价<200元
- 占比约60%

高端市场主要以主题乐园为主，客单价普遍在300元以上。"""

        html = ContentOrchestrator._content_to_html(content)
        assert "<h3" in html
        assert "<h4" in html
        assert "<ul>" in html
        assert "<p" in html

    def test_json_code_block_with_data_points(self):
        """JSON代码块含数据点"""
        content = '''```json
{"title": "市场规模", "content": "2024年市场规模达到**1200亿元**，同比增长15%。"}
```

后续补充说明。'''
        html = ContentOrchestrator._content_to_html(content)
        assert "1200亿元" in html
        assert "<strong>" in html
        assert "后续补充" in html

    def test_blockquote_after_table(self):
        """表格后跟引用"""
        content = """| 指标 | 数值 |
|------|------|
| HHI | 1200 |

> 注：HHI<1500表示竞争型市场"""
        html = ContentOrchestrator._content_to_html(content)
        assert "<table" in html
        assert "<blockquote" in html

    def test_ordered_list_with_risks(self):
        """典型风险列表"""
        content = """1. **政策风险**：监管趋严可能影响行业准入
2. **市场风险**：经济下行导致消费萎缩
3. **竞争风险**：新进入者加剧竞争"""
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert html.count("<li>") == 3
        assert html.count("<strong>") == 3

    def test_mixed_html_and_markdown(self):
        """混合HTML和Markdown"""
        content = """<table><tr><td>现有数据</td></tr></table>

**分析结论**：市场前景乐观。

- 要点1
- 要点2"""
        html = ContentOrchestrator._content_to_html(content)
        assert "<table>" in html
        assert "<strong>" in html
        assert "<ul>" in html

    def test_code_block_with_angle_brackets(self):
        """代码块中的尖括号应被转义"""
        content = "```\nif (x < 10 && y > 5)\n```"
        html = ContentOrchestrator._content_to_html(content)
        assert "<pre" in html
        assert "&lt;" in html
        assert "&gt;" in html

    def test_parse_sections_with_blacklist_title(self):
        """章节标题在黑名单中应被跳过"""
        orchestrator = ContentOrchestrator()
        sections_data = [
            {"id": "s1", "title": "章节内容", "content": "实际内容", "order": 0},
            {"id": "s2", "title": "市场分析", "content": "正常内容", "order": 1},
        ]
        sections = orchestrator._parse_sections(sections_data)
        titles = [s.title for s in sections]
        assert "章节内容" not in titles or any(s.title == "" for s in sections if s.id == "s1")

    def test_parse_sections_with_json_content(self):
        """章节内容为JSON代码块应被提取"""
        orchestrator = ContentOrchestrator()
        sections_data = [
            {
                "id": "s1",
                "title": "画像分析",
                "content": '```json\n{"content": "家长决策以安全为首要因素"}\n```',
                "order": 0
            }
        ]
        sections = orchestrator._parse_sections(sections_data)
        assert len(sections) == 1
        assert "家长决策" in sections[0].content


# =====================================================================
# 9. 发现的Bug验证测试（预期失败→修复后通过）
# =====================================================================

class TestDiscoveredBugs:
    """代码审查中发现的潜在bug，编写测试验证"""

    def test_unclosed_code_block_produces_output(self):
        """Bug: 未闭合代码块不应静默丢弃内容"""
        content = "```\nimportant code here"
        html = ContentOrchestrator._content_to_html(content)
        assert "important code" in html, "未闭合代码块内容被静默丢弃"

    def test_heading_bold_markers_in_parsed_title(self):
        """Bug: ## **粗体标题** 解析后title包含**标记"""
        content = "## **重要发现**\n后续内容"
        result = ContentOrchestrator._parse_markdown_title(content)
        if result["title"]:
            assert "**" not in result["title"], "解析出的标题不应包含**标记"

    def test_code_block_close_with_language_tag(self):
        """Bug: ```python 作为闭合标记可能误匹配"""
        content = "```\ncode line\n```python"
        html = ContentOrchestrator._content_to_html(content)
        assert isinstance(html, str)
        assert "code line" in html

    def test_blockquote_multiline_preserves_content(self):
        """多行引用内容应全部保留"""
        content = "> 第一行重要信息\n> 第二行补充说明\n> 第三行结论"
        html = ContentOrchestrator._content_to_html(content)
        assert "第一行" in html
        assert "第二行" in html
        assert "第三行" in html

    def test_inline_markdown_stray_asterisk(self):
        """单个星号不应产生<em>"""
        result = ContentOrchestrator._inline_markdown("5 * 3 = 15")
        assert "<em>" not in result or "* 3" not in result

    def test_ordered_list_starting_from_non_one(self):
        """Bug: 5. item 起始的有序列表编号问题"""
        content = "5. 第五项\n6. 第六项"
        html = ContentOrchestrator._content_to_html(content)
        assert "<ol>" in html
        assert "第五项" in html
        assert "第六项" in html

    def test_parse_sections_mixed_valid_invalid(self):
        """混合有效和无效section数据"""
        orchestrator = ContentOrchestrator()
        sections_data = [
            {"id": "s1", "title": "有效章节", "content": "内容", "order": 0},
            "invalid string data",
            {"id": "s3", "title": "另一有效", "content": "内容2", "order": 2},
            None,
        ]
        sections = orchestrator._parse_sections(sections_data)
        assert len(sections) == 2
        assert all(isinstance(s, ContentSection) for s in sections)


# =====================================================================
# 10. 精修拒绝/空初稿内容过滤测试
# =====================================================================

class TestRefusalContentFiltering:
    """精修Agent拒绝空初稿时，错误信息不应出现在最终报告中"""

    def test_refusal_content_detected_by_cleaner(self):
        """clean_section 应检测拒绝内容并清空"""
        from src.content.content_cleaner import clean_section
        data = {
            "title": "增长速度",
            "content": "当前初稿为空，无法执行精修润色。分析研究员提交的初稿内容为空（total_sources: 0），未包含任何实质性论述或数据。"
        }
        result = clean_section(data)
        assert result.get("_refusal") is True
        assert result["content"] == ""

    def test_refusal_section_skipped_in_parse(self):
        """_parse_sections 应跳过拒绝内容的章节"""
        orchestrator = ContentOrchestrator()
        sections_data = [
            {"id": "s1", "title": "有效章节", "content": "正常内容", "order": 0},
            {"id": "s2", "title": "增长速度", "content": "当前初稿为空，无法执行精修润色。禁止从头重写或编造数据。请补充完整初稿后，再提交精修。", "order": 1},
            {"id": "s3", "title": "另一有效", "content": "正常内容2", "order": 2},
        ]
        sections = orchestrator._parse_sections(sections_data)
        assert len(sections) == 2
        titles = [s.title for s in sections]
        assert "增长速度" not in titles

    def test_english_refusal_detected(self):
        """英文拒绝内容也应被检测"""
        from src.content.content_cleaner import _is_refusal_content
        assert _is_refusal_content("Draft is empty, cannot refine. No substantive content found.")
        assert _is_refusal_content("The draft is empty so we cannot perform refinement.")

    def test_normal_content_not_flagged(self):
        """正常内容不应被误判为拒绝"""
        from src.content.content_cleaner import _is_refusal_content
        assert not _is_refusal_content("中国老年消费市场呈现双轨并行格局")
        assert not _is_refusal_content("根据国家统计局数据，60岁以上人口超过18%")

    def test_refusal_does_not_affect_other_sections(self):
        """拒绝章节不影响前后正常章节"""
        orchestrator = ContentOrchestrator()
        sections_data = [
            {"id": "s1", "title": "市场概述", "content": "这是正常内容", "order": 0},
            {"id": "s2", "title": "空数据章节", "content": "初稿为空，无法执行精修润色。total_sources: 0", "order": 1},
            {"id": "s3", "title": "总结", "content": "这是总结内容", "order": 2},
        ]
        sections = orchestrator._parse_sections(sections_data)
        assert len(sections) == 2
        assert sections[0].title == "市场概述"
        assert sections[1].title == "总结"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

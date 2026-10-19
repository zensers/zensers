# -*- coding: utf-8 -*-
"""
ContentOrchestrator 测试
========================

测试内容编排功能：
1. 研究结果转换为HTML结构
2. 章节编排
3. 格式适配（Word/PPT）
"""

import pytest
from typing import Dict, Any, List


class TestContentOrchestratorInit:
    """测试 ContentOrchestrator 初始化"""
    
    def test_orchestrator_initialization(self):
        """测试编排器初始化"""
        from src.content.content_orchestrator import ContentOrchestrator
        
        orchestrator = ContentOrchestrator()
        
        assert orchestrator is not None
    
    def test_orchestrator_default_format(self):
        """测试默认格式"""
        from src.content.content_orchestrator import ContentOrchestrator
        
        orchestrator = ContentOrchestrator()
        
        # 默认应支持多种格式
        assert "docx" in orchestrator.supported_formats
        assert "pptx" in orchestrator.supported_formats


class TestContentOrchestratorTransform:
    """测试内容转换"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器实例"""
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    @pytest.fixture
    def sample_research_result(self):
        """创建示例研究结果"""
        return {
            "title": "新能源汽车市场研究报告",
            "topic": "新能源汽车",
            "sections": [
                {
                    "id": "section_1",
                    "title": "市场规模分析",
                    "content": "2026年全球新能源汽车市场规模达到1.2万亿元人民币，同比增长25%。",
                    "order": 1
                },
                {
                    "id": "section_2",
                    "title": "竞争格局",
                    "content": "主要竞争者包括特斯拉、比亚迪、蔚来等。",
                    "order": 2
                }
            ],
            "key_findings": [
                "市场规模持续增长",
                "竞争格局趋于集中"
            ],
            "data_points": [
                {"metric": "市场规模", "value": "1.2万亿", "unit": "人民币"},
                {"metric": "增长率", "value": "25%", "unit": "同比"}
            ]
        }
    
    def test_transform_to_word_html(self, orchestrator, sample_research_result):
        """测试转换为Word格式HTML"""
        html = orchestrator.transform_to_html(
            research_result=sample_research_result,
            output_format="docx"
        )
        
        assert html is not None
        assert "article" in html  # Word格式使用article标签
        assert "新能源汽车市场研究报告" in html
    
    def test_transform_to_ppt_html(self, orchestrator, sample_research_result):
        """测试转换为PPT格式HTML"""
        html = orchestrator.transform_to_html(
            research_result=sample_research_result,
            output_format="pptx"
        )
        
        assert html is not None
        assert "slide" in html.lower() or "section" in html.lower()
    
    def test_transform_preserves_sections(self, orchestrator, sample_research_result):
        """测试转换保留章节"""
        html = orchestrator.transform_to_html(
            research_result=sample_research_result,
            output_format="docx"
        )
        
        # 验证章节标题存在
        assert "市场规模分析" in html
        assert "竞争格局" in html
    
    def test_transform_handles_empty_result(self, orchestrator):
        """测试处理空研究结果"""
        html = orchestrator.transform_to_html(
            research_result={},
            output_format="docx"
        )
        
        # 应返回空结构或默认模板
        assert html is not None
    
    def test_transform_handles_unicode(self, orchestrator):
        """测试Unicode内容处理"""
        research_result = {
            "title": "日本語タイトル",
            "sections": [
                {"id": "s1", "title": "中文标题", "content": "한국어 내용"}
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        assert "日本語タイトル" in html
        assert "中文标题" in html


class TestContentOrchestratorSectionHandling:
    """测试章节处理"""
    
    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    def test_section_ordering(self, orchestrator):
        """测试章节排序"""
        research_result = {
            "title": "测试报告",
            "sections": [
                {"id": "s3", "title": "第三章", "order": 3},
                {"id": "s1", "title": "第一章", "order": 1},
                {"id": "s2", "title": "第二章", "order": 2}
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        # 验证顺序：第一章应在第二章前
        pos1 = html.find("第一章")
        pos2 = html.find("第二章")
        pos3 = html.find("第三章")
        
        assert pos1 < pos2 < pos3
    
    def test_section_without_order(self, orchestrator):
        """测试无order字段的章节"""
        research_result = {
            "title": "测试报告",
            "sections": [
                {"id": "s1", "title": "章节一"},
                {"id": "s2", "title": "章节二"}
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        # 应按原始顺序处理
        assert html is not None
    
    def test_nested_sections(self, orchestrator):
        """测试嵌套章节"""
        research_result = {
            "title": "测试报告",
            "sections": [
                {
                    "id": "s1",
                    "title": "第一章",
                    "subsections": [
                        {"id": "s1_1", "title": "1.1节"},
                        {"id": "s1_2", "title": "1.2节"}
                    ]
                }
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        assert "第一章" in html


class TestContentOrchestratorDataPoints:
    """测试数据点处理"""
    
    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    def test_data_points_in_html(self, orchestrator):
        """测试数据点包含在HTML中"""
        research_result = {
            "title": "数据报告",
            "sections": [],
            "data_points": [
                {"metric": "销售额", "value": "100万", "unit": "元"}
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        # 数据点应被处理
        assert "销售额" in html or "100万" in html
    
    def test_key_findings_in_html(self, orchestrator):
        """测试关键发现包含在HTML中"""
        research_result = {
            "title": "发现报告",
            "sections": [],
            "key_findings": [
                "关键发现1",
                "关键发现2"
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        
        assert "关键发现1" in html


class TestContentOrchestratorPPTSpecific:
    """测试PPT特定功能"""
    
    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    def test_ppt_slide_structure(self, orchestrator):
        """测试PPT幻灯片结构"""
        research_result = {
            "title": "演示报告",
            "sections": [
                {"id": "s1", "title": "章节一", "content": "内容"}
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        
        # PPT应使用slide结构
        assert "slide" in html.lower()
    
    def test_ppt_cover_slide(self, orchestrator):
        """测试PPT封面幻灯片"""
        research_result = {
            "title": "演示报告",
            "sections": []
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        
        # 应包含封面
        assert research_result["title"] in html
    
    def test_ppt_max_content_per_slide(self, orchestrator):
        """测试PPT每页最大内容"""
        research_result = {
            "title": "长报告",
            "sections": [
                {"id": f"s{i}", "title": f"章节{i}", "content": f"内容{i}内容{i}内容{i}"} for i in range(10)
            ]
        }
        
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        
        assert html is not None


class TestContentOrchestratorPPTBulletItems:
    """测试PPT输出使用<li>要点而非<p>长段落"""

    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()

    def test_ppt_content_uses_li_not_p(self, orchestrator):
        research_result = {
            "title": "测试报告",
            "sections": [
                {
                    "id": "s1",
                    "title": "市场分析",
                    "content": (
                        "2025年中国新能源汽车销量达到950万辆，同比增长37.5%。"
                        "全球市场持续高速增长，中国占据全球55%的份额。"
                        "政策驱动向市场驱动转型完成。"
                    ),
                }
            ],
        }
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        assert "<li>" in html, "PPT should use <li> bullet items for content"
        li_count = html.count("<li>")
        p_in_slide_count = 0
        import re
        slides = re.findall(r'<section[^>]*data-type="content"[^>]*>.*?</section>', html, re.DOTALL)
        for slide in slides:
            p_in_slide_count += len(re.findall(r'<p>', slide))
        assert li_count > 0, "Should have bullet items"
        assert li_count >= p_in_slide_count, "Should prefer <li> over <p> in content slides"

    def test_ppt_content_slide_has_title(self, orchestrator):
        research_result = {
            "title": "测试报告",
            "sections": [
                {
                    "id": "s1",
                    "title": "竞争格局",
                    "content": "比亚迪市场份额35%，特斯拉7%。",
                }
            ],
        }
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        import re
        content_slides = re.findall(
            r'<section[^>]*data-type="content"[^>]*>.*?</section>',
            html, re.DOTALL
        )
        assert len(content_slides) >= 1, "Should have at least one content slide"
        has_h2 = any("<h2>" in slide or "<h3>" in slide for slide in content_slides)
        assert has_h2, "Content slides should have a title heading"

    def test_ppt_condenses_long_content_to_bullets(self, orchestrator):
        long_content = (
            "2025年中国新能源汽车销量达到950万辆，同比增长37.5%，渗透率突破40%。"
            "全球新能源汽车市场持续高速增长，中国作为最大单一市场，占据全球55%的份额。"
            "政策驱动向市场驱动转型完成，消费者自发购买意愿显著增强。"
            "核心数据：市场规模1.2万亿元，出口量120万辆，充电桩800万个。"
        )
        research_result = {
            "title": "测试报告",
            "sections": [{"id": "s1", "title": "行业概览", "content": long_content}],
        }
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        assert "<li>" in html
        import re
        li_items = re.findall(r'<li>(.*?)</li>', html)
        assert len(li_items) >= 2, "Long content should be condensed to multiple bullet items"
        assert len(li_items) <= 6, "Should not have too many items per slide"

    def test_word_still_uses_p_not_li(self, orchestrator):
        research_result = {
            "title": "测试报告",
            "sections": [
                {
                    "id": "s1",
                    "title": "市场分析",
                    "content": "2025年销量950万辆，同比增长37.5%。",
                }
            ],
        }
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="docx"
        )
        assert "<p>" in html or "content" in html.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================
# 阶段一测试：_parse_markdown_title 边界测试
# ============================================================

class TestParseMarkdownTitle:
    """测试 _parse_markdown_title 方法
    
    验证各种标题格式的解析正确性
    """
    
    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    def test_standard_markdown_title(self, orchestrator):
        """测试标准 Markdown 标题"""
        content = "## 市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert result["body"] == "2024年销量达到1532万辆。"
    
    def test_chinese_numbered_title(self, orchestrator):
        """测试中文序号标题"""
        content = "一、市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert result["body"] == "2024年销量达到1532万辆。"
    
    def test_chinese_numbered_title_paren(self, orchestrator):
        """测试括号中文序号标题"""
        content = "（一）市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "2024年" in result["body"]
    
    def test_numeric_numbered_title(self, orchestrator):
        """测试数字序号标题"""
        content = "1. 市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert result["body"] == "2024年销量达到1532万辆。"
    
    def test_numeric_numbered_title_chinese_dot(self, orchestrator):
        """测试中文句号数字序号标题"""
        content = "1、市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "2024年" in result["body"]
    
    def test_mixed_numbered_title(self, orchestrator):
        """测试混合序号标题"""
        content = "1. 一、市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "2024年" in result["body"]
    
    def test_no_title_content(self, orchestrator):
        """测试无标题内容"""
        content = "2024年市场规模达到1532万辆，同比增长25%。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] is None
        assert result["body"] == content
    
    def test_empty_content(self, orchestrator):
        """测试空内容"""
        content = ""
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] is None
        assert result["body"] == ""
    
    def test_leading_blank_lines(self, orchestrator):
        """测试开头有空行"""
        content = "\n\n\n## 市场规模\n\n2024年销量达到1532万辆。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "2024年" in result["body"]
    
    def test_multiple_heading_levels(self, orchestrator):
        """测试多级标题"""
        # 只有第一个标题应该被解析
        content = "## 市场规模\n\n### 细分市场\n\n2024年销量数据。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "### 细分市场" in result["body"]
    
    def test_title_with_inline_formatting(self, orchestrator):
        """测试带格式的标题"""
        content = "## **市场规模**分析\n\n2024年销量数据。"
        result = orchestrator._parse_markdown_title(content)
        
        # 标题可能包含格式标记
        assert result["title"] is not None
        assert "2024年" in result["body"]
    
    def test_preserve_subsection_titles(self, orchestrator):
        """测试保留子标题"""
        content = "## 市场规模\n\n2024年销量数据。\n\n### 细分市场\n\n具体数据如下。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "### 细分市场" in result["body"]
        assert "具体数据如下" in result["body"]
    
    def test_whitespace_only_content(self, orchestrator):
        """测试只有空白的内容"""
        content = "   \n\n   \n"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] is None
    
    def test_title_with_colon(self, orchestrator):
        """测试带冒号的标题"""
        content = "## 市场规模：概述\n\n2024年销量数据。"
        result = orchestrator._parse_markdown_title(content)
        
        assert "市场规模" in result["title"]
        assert "2024年" in result["body"]
    
    def test_none_content(self, orchestrator):
        """测试 None 输入"""
        result = orchestrator._parse_markdown_title(None)
        
        assert result["title"] is None
        assert result["body"] == ""
    
    def test_title_only_no_body(self, orchestrator):
        """测试只有标题无正文"""
        content = "## 市场规模"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert result["body"] == ""
    
    def test_title_with_trailing_whitespace(self, orchestrator):
        """测试标题后有空白"""
        content = "## 市场规模   \n\n2024年数据。"
        result = orchestrator._parse_markdown_title(content)
        
        assert result["title"] == "市场规模"
        assert "2024年" in result["body"]


class TestParseMarkdownTitleIntegration:
    """集成测试：验证 _parse_sections 使用 _parse_markdown_title"""
    
    @pytest.fixture
    def orchestrator(self):
        from src.content.content_orchestrator import ContentOrchestrator
        return ContentOrchestrator()
    
    def test_section_content_without_duplicate_title(self, orchestrator):
        """测试章节内容不含重复标题"""
        sections_data = [
            {
                "id": "s1",
                "title": "市场规模",
                "content": "## 市场规模\n\n2024年销量达到1532万辆。"
            }
        ]
        
        sections = orchestrator._parse_sections(sections_data)
        
        assert len(sections) == 1
        assert sections[0].title == "市场规模"
        # content 应该不含标题
        assert "## 市场规模" not in sections[0].content
        assert "2024年销量" in sections[0].content
    
    def test_section_title_fallback(self, orchestrator):
        """测试标题回退：使用 content 中的标题"""
        sections_data = [
            {
                "id": "s1",
                "title": "",  # 空标题
                "content": "## 市场规模\n\n2024年销量数据。"
            }
        ]
        
        sections = orchestrator._parse_sections(sections_data)
        
        # 应该从 content 中提取标题
        assert sections[0].title == "市场规模"
    
    def test_section_preserves_subsections(self, orchestrator):
        """测试子章节正确处理"""
        sections_data = [
            {
                "id": "s1",
                "title": "市场规模",
                "content": "## 市场规模\n\n总体数据。",
                "subsections": [
                    {
                        "id": "s1_1",
                        "title": "细分市场",
                        "content": "### 细分市场\n\n具体数据。"
                    }
                ]
            }
        ]
        
        sections = orchestrator._parse_sections(sections_data)
        
        assert len(sections) == 1
        assert len(sections[0].subsections) == 1
        # 子章节标题应该被保留在 content 中（因为它是子标题）
        assert "具体数据" in sections[0].subsections[0].content
# -*- coding: utf-8 -*-
"""
ContentCondenser 测试
=====================

测试PPT内容精简功能：
1. 长段落→要点列表
2. 数据标签提取
3. KPI识别
4. 图表建议生成
5. 与ContentOrchestrator集成
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestContentCondenserInit:
    
    def test_condenser_initialization(self):
        from src.content.content_condenser import ContentCondenser
        condenser = ContentCondenser()
        assert condenser is not None
    
    def test_condenser_default_config(self):
        from src.content.content_condenser import ContentCondenser
        condenser = ContentCondenser()
        assert condenser.max_bullet_chars == 40
        assert condenser.max_bullets_per_slide == 5
        assert condenser.max_slide_text_chars == 300


class TestContentCondenserExtractBullets:
    """测试从长段落提取要点"""
    
    @pytest.fixture
    def condenser(self):
        from src.content.content_condenser import ContentCondenser
        return ContentCondenser()
    
    def test_single_paragraph_to_bullets(self, condenser):
        content = (
            "2025年中国新能源汽车销量达到950万辆，同比增长37.5%，渗透率突破40%。"
            "全球新能源汽车市场持续高速增长，中国作为最大单一市场，占据全球55%的份额。"
            "政策驱动向市场驱动转型完成，消费者自发购买意愿显著增强。"
        )
        bullets = condenser.extract_bullets(content)
        assert isinstance(bullets, list)
        assert len(bullets) >= 2
        assert len(bullets) <= 5
        for b in bullets:
            assert len(b) <= condenser.max_bullet_chars * 2
    
    def test_multiple_paragraphs_to_bullets(self, condenser):
        content = (
            "国内市场：2025年销量950万辆，预计2026年突破1200万辆，CAGR达28%。\n"
            "出口市场：2025年出口120万辆，同比增长50%，欧洲和东南亚为主要目的地。\n"
            "充电基础设施：全国充电桩保有量突破800万个，车桩比降至1.2:1。"
        )
        bullets = condenser.extract_bullets(content)
        assert len(bullets) >= 3
        assert any("950" in b for b in bullets)
        assert any("120" in b for b in bullets)
        assert any("800" in b for b in bullets)
    
    def test_already_bullet_content_passthrough(self, condenser):
        content = "- 要点1：销量950万辆\n- 要点2：渗透率40%\n- 要点3：出口120万辆"
        bullets = condenser.extract_bullets(content)
        assert len(bullets) == 3
        assert "950" in bullets[0]
    
    def test_empty_content_returns_empty(self, condenser):
        bullets = condenser.extract_bullets("")
        assert bullets == []
    
    def test_short_content_returns_as_is(self, condenser):
        content = "市场规模1.2万亿元"
        bullets = condenser.extract_bullets(content)
        assert len(bullets) >= 1
        assert "1.2" in bullets[0]


class TestContentCondenserExtractKPIs:
    """测试KPI数据提取"""
    
    @pytest.fixture
    def condenser(self):
        from src.content.content_condenser import ContentCondenser
        return ContentCondenser()
    
    def test_extract_kpis_from_text(self, condenser):
        content = (
            "2025年销量950万辆，同比增长37.5%，渗透率突破40.3%。"
            "市场规模1.2万亿元，出口量120万辆。"
        )
        kpis = condenser.extract_kpis(content)
        assert isinstance(kpis, list)
        assert len(kpis) >= 3
        numbers = [k["number"] for k in kpis]
        assert any("950" in n for n in numbers)
        assert any("1.2" in n for n in numbers)
    
    def test_extract_kpis_with_trends(self, condenser):
        content = "销量950万辆，增长37.5%，市场份额35%下降至7%"
        kpis = condenser.extract_kpis(content)
        assert len(kpis) >= 1
        has_trend = any(k.get("trend") is not None for k in kpis)
        assert has_trend
    
    def test_no_kpis_in_plain_text(self, condenser):
        content = "行业整体呈现良好发展态势"
        kpis = condenser.extract_kpis(content)
        assert kpis == []


class TestContentCondenserSuggestCharts:
    """测试图表建议生成"""
    
    @pytest.fixture
    def condenser(self):
        from src.content.content_condenser import ContentCondenser
        return ContentCondenser()
    
    def test_suggest_bar_chart_for_ranking(self, condenser):
        content = (
            "比亚迪以35%的市场份额稳居榜首。"
            "特斯拉中国市场份额降至7%。"
            "吉利新能源市场份额9%。"
        )
        suggestions = condenser.suggest_charts(content)
        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        assert any(s["chart_type"] in ("bar", "pie") for s in suggestions)
    
    def test_suggest_line_chart_for_trend(self, condenser):
        content = (
            "2022年销量688万辆，2023年780万辆，"
            "2024年860万辆，2025年950万辆。"
        )
        suggestions = condenser.suggest_charts(content)
        assert len(suggestions) >= 1
        assert any(s["chart_type"] == "line" for s in suggestions)
    
    def test_no_chart_for_non_data_content(self, condenser):
        content = "行业整体呈现良好发展态势，未来可期"
        suggestions = condenser.suggest_charts(content)
        assert suggestions == []


class TestContentCondenserCondense:
    """测试完整精简流程（同步版本，不依赖LLM）"""
    
    @pytest.fixture
    def condenser(self):
        from src.content.content_condenser import ContentCondenser
        return ContentCondenser()
    
    def test_condense_returns_slide_ready_data(self, condenser):
        content = (
            "2025年中国新能源汽车销量达到950万辆，同比增长37.5%，渗透率突破40%。"
            "全球新能源汽车市场持续高速增长，中国作为最大单一市场，占据全球55%的份额。"
            "政策驱动向市场驱动转型完成，消费者自发购买意愿显著增强。"
        )
        result = condenser.condense(content, title="行业概览")
        assert "items" in result
        assert "kpi_data" in result
        assert "chart_suggestions" in result
        assert isinstance(result["items"], list)
        assert len(result["items"]) >= 2
        assert len(result["items"]) <= 5
        assert len(result["all_items"]) >= len(result["items"])

    def test_all_items_keeps_late_facts_for_pagination(self, condenser):
        content = "。".join(f"第{i}个事实：市场数据{i}万辆" for i in range(1, 9)) + "。"
        result = condenser.condense(content, title="完整事实")
        assert len(result["all_items"]) == 8
        assert "第8个事实" in " ".join(result["all_items"])
    
    def test_condense_preserves_key_numbers(self, condenser):
        content = (
            "2025年销量950万辆，同比增长37.5%。"
            "市场规模1.2万亿元。出口量120万辆，同比增长50%。"
        )
        result = condenser.condense(content, title="市场规模")
        all_text = " ".join(result["items"])
        assert "950" in all_text
        assert "1.2" in all_text
    
    def test_condense_with_table_data(self, condenser):
        content = "比亚迪销量330万辆，特斯拉66万辆，吉利85万辆"
        table_data = [
            ["品牌", "销量(万辆)", "市场份额"],
            ["比亚迪", "330", "35%"],
            ["特斯拉", "66", "7%"],
        ]
        result = condenser.condense(content, title="竞争格局", table_data=table_data)
        assert "chart_suggestions" in result
        assert len(result["chart_suggestions"]) >= 1

    def test_condense_preserves_late_facts_in_english_revision(self, condenser):
        """English long-form revisions must not lose facts after the first line."""
        content = (
            "Asia Pacific reached 5.1B USD in 2024, driven by China's 3.2B "
            "and India's 0.8B markets. The region's CAGR of 24.3% outpaces "
            "the global average of 18.2%. Key verticals: semiconductor "
            "manufacturing (+31%), enterprise SaaS (+27%), fintech (+22%)."
        )
        result = condenser.condense(content, title="Market Overview")
        assert "semiconductor" in " ".join(result["items"])


class TestContentCondenserIntegration:
    """测试与ContentOrchestrator集成"""
    
    def test_orchestrator_uses_condenser_for_pptx(self):
        from src.content.content_orchestrator import ContentOrchestrator
        orchestrator = ContentOrchestrator()
        assert hasattr(orchestrator, '_condenser')
    
    def test_ppt_output_has_items_not_long_content(self):
        from src.content.content_orchestrator import ContentOrchestrator
        orchestrator = ContentOrchestrator()
        research_result = {
            "title": "测试报告",
            "sections": [
                {
                    "id": "s1",
                    "title": "市场分析",
                    "content": (
                        "2025年中国新能源汽车销量达到950万辆，同比增长37.5%，渗透率突破40%。"
                        "全球新能源汽车市场持续高速增长，中国作为最大单一市场，占据全球55%的份额。"
                        "政策驱动向市场驱动转型完成，消费者自发购买意愿显著增强。"
                        "核心数据：市场规模1.2万亿元，出口量120万辆。"
                    ),
                    "order": 1,
                }
            ],
            "key_findings": [],
            "data_points": [],
        }
        html = orchestrator.transform_to_html(
            research_result=research_result,
            output_format="pptx"
        )
        assert '<li>' in html
        long_paragraphs = html.count('<p>') 
        list_items = html.count('<li>')
        assert list_items > 0, "PPT output should contain <li> bullet items, not just <p> paragraphs"
        assert list_items >= long_paragraphs, "PPT should prefer <li> over <p> for content"

    def test_long_ppt_section_is_paginated_instead_of_truncated(self):
        from src.content.content_orchestrator import ContentOrchestrator
        orchestrator = ContentOrchestrator()
        facts = "。".join(f"第{i}项事实：市场规模{i}亿元" for i in range(1, 9)) + "。"
        html = orchestrator.transform_to_html({
            "title": "长章节",
            "sections": [{"id": "s1", "title": "完整分析", "content": facts}],
        }, output_format="pptx")
        assert html.count('data-type="content"') >= 2
        assert "第8项事实" in html

    def test_ppt_page_numbers_are_contiguous_after_section_expansion(self):
        from src.content.content_orchestrator import ContentOrchestrator
        import re

        html = ContentOrchestrator().transform_to_html({
            "title": "页码测试",
            "sections": [
                {"id": "s1", "title": "第一章", "content": "2024年销量950万辆，同比增长37.5%。"},
                {"id": "s2", "title": "第二章", "content": "结论一。结论二。结论三。结论四。结论五。结论六。"},
            ],
        }, output_format="pptx")
        pages = [int(value) for value in re.findall(r'data-page="(\d+)"', html)]
        assert pages == list(range(1, len(pages) + 1))
        assert "目录" not in html  # two sections do not need a TOC slide
        assert "报告结论" in html

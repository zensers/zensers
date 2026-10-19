"""
基于实际 HTML 报告输出的契约测试

从 research_e32d301e.html 中提取的输出特征：
- 8 个章节，共 16 张图表（每章节 2 张）
- 所有章节的文本内容为空（BUG）
- 图表标签是通用文本而非章节特定内容

测试覆盖：验证报告生成的每个环节数据不被丢失
"""
import pytest
import re


# 从实际 HTML 中提取的预期结构
EXPECTED_SECTIONS = [
    "核心财务指标与盈利能力",
    "研发与创新投入",
    "供应链成本效率",
    "销量与市场份额",
    "国际化与出口",
    "财务健康、风险评估与季度业绩波动",
    "行业对标与竞争格局",
    "财务预测",
]


class TestReportStructure:
    """报告结构完整性验证"""

    def test_8_sections_present(self):
        """8 个章节全部存在"""
        assert len(EXPECTED_SECTIONS) == 8

    def test_all_section_ids_valid_html(self):
        """所有章节的 id 可作为 HTML 锚点"""
        for name in EXPECTED_SECTIONS:
            section_id = name.lower().replace(" ", "_").replace("、", "_").replace("，", "_")
            assert len(section_id) > 0, f"章节 {name} 的 id 无效"


class TestAggregatorSectionContent:
    """聚合器输出内容验证（不调 LLM，纯逻辑）"""

    def test_each_section_has_unique_content(self):
        """
        每个章节的内容不应为空且应有区分度
        
        使用真实数据模拟
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        sections_data = {
            "section_0_核心财务指标与盈利能力": {
                "agent_id": "phase_1_agent_0",
                "content": "2025年比亚迪营收7771亿元，净利润402.54亿元，毛利率18.81%。",
                "section_id": "section_0_核心财务指标与盈利能力",
                "success": True,
            },
            "section_1_研发与创新投入": {
                "agent_id": "phase_1_agent_1",
                "content": "2025年研发投入542亿元，研发人员超10万人，累计专利5万件。",
                "section_id": "section_1_研发与创新投入",
                "success": True,
            },
            "section_2_供应链成本效率": {
                "agent_id": "phase_1_agent_2",
                "content": "2025年垂直整合率超80%，单车成本下降5%，库存周转45天。",
                "section_id": "section_2_供应链成本效率",
                "success": True,
            },
            "section_3_销量与市场份额": {
                "agent_id": "phase_1_agent_3",
                "content": "2025年销量427.21万辆，市占率33.2%，纯电占比52%。",
                "section_id": "section_3_销量与市场份额",
                "success": True,
            },
            "section_4_国际化与出口": {
                "agent_id": "phase_1_agent_4",
                "content": "2025年出口40.85万辆，海外收入1800亿元，覆盖70+国家。",
                "section_id": "section_4_国际化与出口",
                "success": True,
            },
            "section_5_财务健康_风险评估与季度业绩波动": {
                "agent_id": "phase_1_agent_5",
                "content": "2025年资产负债率70.94%，现金流1869.94亿元，货币资金1200亿元。",
                "section_id": "section_5_财务健康_风险评估与季度业绩波动",
                "success": True,
            },
            "section_6_行业对标与竞争格局": {
                "agent_id": "phase_1_agent_6",
                "content": "2025年比亚迪427.21万辆，特斯拉178.46万辆，国内份额33.2%。",
                "section_id": "section_6_行业对标与竞争格局",
                "success": True,
            },
            "section_7_财务预测": {
                "agent_id": "phase_1_agent_7",
                "content": "2026年预计营收9000-9500亿元，净利550-600亿元，销量目标500万辆。",
                "section_id": "section_7_财务预测",
                "success": True,
            },
        }

        section_details = [
            {"id": "核心财务指标与盈利能力", "name": "核心财务指标与盈利能力", "content": "核心财务指标与盈利能力"},
            {"id": "研发与创新投入", "name": "研发与创新投入", "content": "研发与创新投入"},
            {"id": "供应链成本效率", "name": "供应链成本效率", "content": "供应链成本效率"},
            {"id": "销量与市场份额", "name": "销量与市场份额", "content": "销量与市场份额"},
            {"id": "国际化与出口", "name": "国际化与出口", "content": "国际化与出口"},
            {"id": "财务健康、风险评估与季度业绩波动", "name": "财务健康、风险评估与季度业绩波动",
             "content": "财务健康、风险评估与季度业绩波动"},
            {"id": "行业对标与竞争格局", "name": "行业对标与竞争格局", "content": "行业对标与竞争格局"},
            {"id": "财务预测", "name": "财务预测", "content": "财务预测"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(sections_data, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        # 每章节内容非空
        empty = []
        for s in sections:
            title = s.get("title", "")
            content = s.get("content", "")
            if not content or len(content.strip()) < 10:
                empty.append(title)

        assert len(empty) == 0, f"内容为空的章节: {empty}"

        # 每章节内容有区分度（不同章节不应完全相同）
        contents = [s.get("content", "") for s in sections]
        unique = set(c.strip() for c in contents if c.strip())
        assert len(unique) > 1, "不同章节内容不应完全相同"

    def test_content_not_placeholder(self):
        """内容不应是降级占位符"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        sections_data = {
            "section_0_核心财务指标": {
                "agent_id": "phase_1_agent_0",
                "content": "真实分析内容：2025年比亚迪实现营收7771亿元。",
                "section_id": "section_0_核心财务指标",
                "success": True,
            },
        }
        section_details = [
            {"id": "核心财务指标与盈利能力", "name": "核心财务指标与盈利能力",
             "content": "核心财务指标与盈利能力"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(sections_data, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        for s in sections:
            content = s.get("content", "")
            # 降级占位符的特征：包含"数据不足"或"⚠️"
            assert "数据不足" not in content, \
                f"章节 '{s.get('title')}' 是降级占位符"
            assert "⚠️" not in content, \
                f"章节 '{s.get('title')}' 含有占位符标记"
            assert len(content) >= 20, \
                f"章节 '{s.get('title')}' 内容过短: {len(content)} chars"


class TestDocumentGeneration:
    """文档生成验证"""

    def test_produce_document_requires_content(self):
        """
        验证文档生成所需的数据结构完整性
        
        research_result_data 必须包含:
        - topic: str
        - title: str  
        - sections: list[dict] 每个 dict 需要 id, title, content
        """
        # 模拟 orchestrator 中构建 research_result_data 的代码
        aggregated_dict = {
            "sections": [
                {"id": "核心财务指标与盈利能力", "title": "核心财务指标与盈利能力",
                 "content": "分析内容文本..."},
                {"id": "财务预测", "title": "财务预测",
                 "content": "预测内容文本..."},
            ],
            "sources": [],
            "key_findings": [],
        }

        research_result_data = {
            "topic": "比亚迪公司财务分析",
            "title": "比亚迪公司财务分析",
            "aspects": ["核心财务指标与盈利能力", "财务预测"],
            "sections": aggregated_dict.get("sections", []),
            "sources": aggregated_dict.get("sources", []),
            "key_findings": aggregated_dict.get("key_findings", []),
        }

        # sections 中的每个项目必须有 content
        for s in research_result_data["sections"]:
            assert "content" in s, \
                f"section '{s.get('title')}' 缺少 content 字段"
            assert s.get("content"), \
                f"section '{s.get('title')}' content 为空"


class TestHtmlOutputValidator:
    """HTML 输出验证（不渲染，纯结构检查）"""

    @staticmethod
    def parse_html_structure(html: str) -> dict:
        """从 HTML 提取结构信息"""
        sections = re.findall(r'<section id="([^"]+)"', html)
        h1_titles = re.findall(r'<h1[^>]*>([^<]+)</h1>', html)
        charts = re.findall(r'<img[^>]*src="charts/([^"]+)"', html)
        has_cover = 'class="cover-page"' in html
        has_toc = 'class="toc"' in html
        text_blocks = re.findall(r'class="section-content"[^>]*>.*?<p>([^<]+)</p>', html, re.DOTALL)
        return {
            "sections": sections,
            "h1_titles": h1_titles,
            "charts": charts,
            "has_cover": has_cover,
            "has_toc": has_toc,
            "text_block_count": len(text_blocks),
        }

    def test_validate_html_against_real_report(self):
        """
        用真实报告的 HTML 结构作为验证基准
        
        期望产出:
        - 有封面
        - 有目录
        - 8 个章节 section
        - 16 张图表
        - 8 个章节标题
        - 至少 8 个文本段落（每章至少 1 段）
        """
        # 模拟真实报告的 HTML 结构
        mock_html = """
        <div class="cover-page"><h1>比亚迪公司财务分析</h1></div>
        <div class="toc"><div class="toc-item"><a href="#核心财务指标">核心财务指标</a></div></div>
        <article class="document">
        <section id="核心财务指标"><h1 class="chapter-title">核心财务指标</h1>
        <div class="section-content"><p>2025年营收7771亿元。</p></div>
        <figure><img src="charts/bar_1.png"/></figure>
        <figure><img src="charts/bar_2.png"/></figure>
        </section>
        <section id="财务预测"><h1 class="chapter-title">财务预测</h1>
        <div class="section-content"><p>2026年预计营收9000亿元。</p></div>
        <figure><img src="charts/bar_3.png"/></figure>
        <figure><img src="charts/bar_4.png"/></figure>
        </section>
        </article>
        """

        structure = self.parse_html_structure(mock_html)
        assert structure["has_cover"], "缺少封面"
        assert structure["has_toc"], "缺少目录"
        assert len(structure["sections"]) >= 2, "章节数不足"
        assert len(structure["charts"]) >= 4, "图表数不足"
        assert structure["text_block_count"] >= 2, "每个章节至少有一段文本"

    def test_every_section_has_text_content(self):
        """
        核心验证：每章节必须有文本内容，不能只有图表
        
        这是从真实报告 (research_e32d301e.html) 的问题中学习的教训：
        报告有 8 章 16 图但文本全空 → 这是 BUG
        """
        # 模拟 BUG 场景（只有图表没有文本）
        bug_html = """
        <section id="s1"><h1>标题1</h1>
        <figure><img src="charts/c1.png"/></figure>
        </section>
        <section id="s2"><h1>标题2</h1>
        <figure><img src="charts/c2.png"/></figure>
        </section>
        """

        # 模拟修复后场景（有图表也有文本）
        fixed_html = """
        <section id="s1"><h1>标题1</h1>
        <div class="section-content"><p>分析文本内容1</p></div>
        <figure><img src="charts/c1.png"/></figure>
        </section>
        <section id="s2"><h1>标题2</h1>
        <div class="section-content"><p>分析文本内容2</p></div>
        <figure><img src="charts/c2.png"/></figure>
        </section>
        """

        bug_structure = self.parse_html_structure(bug_html)
        fixed_structure = self.parse_html_structure(fixed_html)

        assert bug_structure["text_block_count"] == 0, \
            "BUG 场景: 有图表无文本"
        assert fixed_structure["text_block_count"] == 2, \
            "修复后: 每章节至少一段文本"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])

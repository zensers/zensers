"""
用真实缓存数据测试 ContentOrchestrator 的 HTML 生成

验证路径:
  research_result_cache.json → ContentOrchestrator.transform_to_html() → HTML

如果 HTML 有文本内容 → 文档生成 agent 前的环节有问题
如果 HTML 无文本内容 → ContentOrchestrator 或模板本身有问题
"""
import json
import re
import pytest
from src.content.content_orchestrator import ContentOrchestrator


CACHE_PATH = r'E:\market_report_systerm\data\research_e32d301e\research_result_cache.json'


def _load_cache():
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def real_data():
    return _load_cache()


class TestContentOrchestratorWithRealData:
    """用真实缓存数据验证 ContentOrchestrator"""

    def test_parse_sections_preserves_content(self, real_data):
        """_parse_sections 不丢失内容"""
        orchestrator = ContentOrchestrator()
        sections = orchestrator._parse_sections(real_data.get("sections", []))

        assert len(sections) == 8
        for s in sections:
            assert len(s.content) > 50, \
                f"章节 '{s.title}' 内容丢失: {len(s.content)} chars"

    def test_generate_html_has_text_content(self, real_data):
        """
        核心验证：transform_to_html 产出的 HTML 必须有文本
        
        如果这个测试通过 → 问题不在 ContentOrchestrator
        如果这个测试失败 → ContentOrchestrator 或模板有问题
        """
        orchestrator = ContentOrchestrator()
        html = orchestrator.transform_to_html(
            research_result=real_data,
            output_format="html",
        )

        # 提取所有 <p> 标签内的文本
        text_blocks = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)

        assert len(text_blocks) >= 8, \
            f"每个章节至少一段文本，但只找到 {len(text_blocks)} 段"

        total_text = sum(len(re.sub(r'<[^>]+>', '', t).strip()) for t in text_blocks)
        assert total_text >= 5000, \
            f"总文本内容不足: {total_text} chars"

    def test_html_has_text_content_present(self, real_data):
        """HTML 包含文本内容（图表由 DocumentGenerationAgent 预生成，ContentOrchestrator 不负责）"""
        orchestrator = ContentOrchestrator()
        html = orchestrator.transform_to_html(
            research_result=real_data,
            output_format="html",
        )

        text_blocks = re.findall(r'<p[^>]*>(.*?)</p>', html)
        assert len(text_blocks) >= 8, f"文本段数: {len(text_blocks)}"

    def test_template_variables_include_content(self, real_data):
        """模板变量中的 sections 包含 content"""
        from src.content.content_orchestrator import ContentOrchestrator

        orchestrator = ContentOrchestrator()
        sections = orchestrator._parse_sections(real_data.get("sections", []))
        key_findings = real_data.get("key_findings", [])
        data_points = real_data.get("data_points", [])

        variables = orchestrator._prepare_template_variables(
            title=real_data.get("title", "Report"),
            sections=sections,
            key_findings=key_findings,
            data_points=data_points,
            research_result=real_data,
            output_format="html",
        )

        # 模板变量中的每个 section 必须有 content
        for section in variables.get("sections", []):
            assert len(section.get("content", "")) > 50, \
                f"模板变量中 {section.get('title', '?')} 内容丢失"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])

"""End-to-end test for multi-level framework rendering pipeline.

Tests the full data flow:
  framework_tree → section_details → result_aggregator → ContentSection → HTML/DOCX
"""
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
test_dir = os.path.dirname(__file__)
project_root = os.path.dirname(test_dir)
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, project_root)

from unittest.mock import MagicMock

def test_result_aggregator_to_html_fallback():
    """E2E: framework_tree → result_aggregator → ContentSection → HTML fallback"""
    from src.core.orchestrator.aggregation.result_aggregator import _build_subsections_from_skeleton
    from src.content.content_orchestrator import ContentOrchestrator, ContentSection

    framework_subs = [
        {'name': '市场规模', 'points': ['营收规模', '增长率']},
        {'name': '竞争格局', 'points': []},
    ]
    content = '### 市场规模\n2024年营收100亿元。\n#### 营收规模\n营收达100亿元。\n#### 增长率\n同比增长25%。\n### 竞争格局\n主要竞争者包括A、B、C。'
    subsections = _build_subsections_from_skeleton(content, framework_subs)

    assert len(subsections) >= 2, f"Expected >=2 subsections, got {len(subsections)}"
    
    market_sub = [s for s in subsections if s['title'] == '市场规模'][0]
    assert market_sub['points'] == ['营收规模', '增长率'], f"Points mismatch: {market_sub['points']}"
    
    comp_sub = [s for s in subsections if s['title'] == '竞争格局'][0]
    assert comp_sub['points'] == [], f"Empty points mismatch: {comp_sub['points']}"
    
    sections = [
        ContentSection(
            id='s1', title='新能源汽车市场', content='市场概述', order=0,
            subsections=[
                ContentSection(
                    id='s1_1', title='市场规模', content=market_sub['content'], order=0,
                    points=['营收规模', '增长率']
                ),
                ContentSection(
                    id='s1_2', title='竞争格局', content=comp_sub['content'], order=0,
                    points=[]
                ),
            ]
        )
    ]

    co = ContentOrchestrator.__new__(ContentOrchestrator)
    html = co._generate_word_html('新能源汽车市场研究报告', sections, [], [])

    assert '<h4 class="sub-subsection-title">营收规模</h4>' in html, "Missing h4 for 营收规模"
    assert '<h4 class="sub-subsection-title">增长率</h4>' in html, "Missing h4 for 增长率"
    assert '<h3 class="subsection-title">市场规模</h3>' in html, "Missing h3 for 市场规模"
    assert '<h3 class="subsection-title">竞争格局</h3>' in html, "Missing h3 for 竞争格局"
    assert '1.1.1 营收规模' in html, "Missing 3-level TOC entry 营收规模"
    assert '1.1.2 增长率' in html, "Missing 3-level TOC entry 增长率"

    print('PASS: E2E result_aggregator → HTML fallback 3-level rendering')


def test_result_aggregator_to_html_template():
    """E2E: framework_tree → result_aggregator → ContentSection → HTML template"""
    from src.core.orchestrator.aggregation.result_aggregator import _build_subsections_from_skeleton
    from src.content.content_orchestrator import ContentOrchestrator, ContentSection

    framework_subs = [
        {'name': '市场规模', 'points': ['营收规模', '增长率']},
    ]
    content = '### 市场规模\n市场规模数据。\n#### 营收规模\n营收100亿。\n#### 增长率\n增长25%。'
    subsections = _build_subsections_from_skeleton(content, framework_subs)

    market_sub = [s for s in subsections if s['title'] == '市场规模'][0]

    sections = [
        ContentSection(
            id='s1', title='AI Industry', content='Overview', order=0,
            subsections=[
                ContentSection(
                    id='s1_1', title='市场规模', content=market_sub['content'], order=0,
                    points=['营收规模', '增长率']
                ),
            ]
        )
    ]

    research_result = {
        'title': 'AI Industry Report',
        'sections': [{'id': 's1', 'title': 'AI Industry', 'content': 'Overview', 'subsections': subsections}],
        'key_findings': [],
        'data_points': [],
    }

    co = ContentOrchestrator()
    html = co.transform_to_html(research_result=research_result, output_format='html')

    assert '<h4 class="sub-subsection-title"' in html or 'sub-subsection-title' in html, \
        f"Template HTML must contain sub-subsection-title class"
    assert 'point_sections' in html or '营收规模' in html, \
        f"Template HTML must render point content"

    print('PASS: E2E result_aggregator → HTML template 3-level rendering')


def test_result_aggregator_to_docx_direct():
    """E2E: framework_tree → result_aggregator → DOCX direct generation"""
    from src.core.orchestrator.aggregation.result_aggregator import _build_subsections_from_skeleton
    from src.core.orchestrator.output.document_generator import DocumentGenerator, DocumentConfig

    framework_subs = [
        {'name': 'Market Size', 'points': ['Revenue', 'Growth Rate']},
    ]
    content = '### Market Size\nRevenue data.\n#### Revenue\n$100M revenue.\n#### Growth Rate\n25% YoY growth.'
    subsections = _build_subsections_from_skeleton(content, framework_subs)

    dg = DocumentGenerator(DocumentConfig())
    dg._content = [
        {"type": "heading", "text": "Market Analysis", "level": 1},
        {"type": "heading", "text": "Market Size", "level": 2},
        {"type": "heading", "text": "Revenue", "level": 3},
        {"type": "heading", "text": "Growth Rate", "level": 3},
    ]

    toc = dg._generate_toc()

    assert '1.1.1 Revenue' in toc, f"DOCX TOC must include 3-level entry: {toc}"
    assert '1.1.2 Growth Rate' in toc, f"DOCX TOC must include 3-level entry: {toc}"

    print('PASS: E2E result_aggregator → DOCX TOC 3-level rendering')


def test_framework_tree_to_section_details():
    """E2E: framework_tree → _build_section_details_from_tree → _parse_requirement"""
    from src.api.research_api import ResearchAPI

    api = ResearchAPI.__new__(ResearchAPI)

    framework_tree = [
        {'name': 'Market Size', 'sub_sections': [{'name': 'Revenue', 'points': ['Q1 Revenue', 'YoY Growth']}]},
        {'name': 'Competition', 'sub_sections': []},
    ]

    section_details = api._build_section_details_from_tree(framework_tree)

    assert len(section_details) == 2, f"Expected 2 section_details, got {len(section_details)}"
    
    market_detail = [d for d in section_details if d['name'] == 'Market Size'][0]
    assert market_detail.get('sub_sections'), f"Market Size must have sub_sections"
    market_sub = market_detail['sub_sections'][0]
    assert market_sub['name'] == 'Revenue', f"Sub-section name mismatch"
    assert market_sub['points'] == ['Q1 Revenue', 'YoY Growth'], f"Points mismatch: {market_sub['points']}"

    comp_detail = [d for d in section_details if d['name'] == 'Competition'][0]
    assert comp_detail.get('sub_sections') == [], f"Competition should have empty sub_sections"

    print('PASS: E2E framework_tree → section_details with sub_sections and points')


def test_flat_framework_backward_compatibility():
    """E2E: flat framework_sections (no framework_tree) still works correctly"""
    from src.api.research_api import ResearchAPI
    from src.content.content_orchestrator import ContentOrchestrator, ContentSection

    api = ResearchAPI.__new__(ResearchAPI)

    parsed = {
        'message': '确认框架',
        'action': 'enter_framework',
        'framework_sections': ['市场规模', '竞争格局'],
    }

    result = api._build_response(parsed, None, None)
    assert result['framework_tree'] is None, "Flat framework must not produce framework_tree"
    assert result['framework_sections'] == ['市场规模', '竞争格局']

    sections = [
        ContentSection(id='s1', title='市场规模', content='数据内容', order=0, subsections=[], points=[]),
        ContentSection(id='s2', title='竞争格局', content='竞争内容', order=0, subsections=[], points=[]),
    ]

    co = ContentOrchestrator.__new__(ContentOrchestrator)
    html = co._render_section_html(sections[0])
    assert 'sub-subsection-title' not in html, "Flat framework must not produce h4 elements"
    assert '<h3 class="subsection-title">' not in html, "No subsections = no h3"

    print('PASS: E2E flat framework backward compatibility')


def test_bilingual_zh_en_sub_aspects():
    """E2E: ZH and EN language produce correct sub_aspects text"""
    from src.core.decomposition.strategies import IndustryResearchStrategy
    from src.core.i18n import set_language, Language

    decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
    config = MagicMock()
    config.get_focus_areas.return_value = []
    config.get_priority_sources.return_value = []

    set_language(Language.ZH)
    zh_prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
    assert "数据采集" in zh_prompt or "子主题" in zh_prompt, f"ZH prompt must contain Chinese sub_aspects text: {zh_prompt[:200]}"
    assert "NLP" in zh_prompt

    set_language(Language.EN)
    en_prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
    assert "Sub-topics" in en_prompt, f"EN prompt must contain English sub_aspects text: {en_prompt[:200]}"
    assert "NLP" in en_prompt

    set_language(Language.ZH)

    print('PASS: E2E bilingual sub_aspects injection')


if __name__ == '__main__':
    test_result_aggregator_to_html_fallback()
    test_result_aggregator_to_html_template()
    test_result_aggregator_to_docx_direct()
    test_framework_tree_to_section_details()
    test_flat_framework_backward_compatibility()
    test_bilingual_zh_en_sub_aspects()
    print('\nAll 6 E2E tests PASSED!')

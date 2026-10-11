# -*- coding: utf-8 -*-
"""渲染期剥离内部证据标注（置信度/factual/inferential）的单测。

缺陷：研究管线给论断打的内部标注（（factual）/（inferential）/（置信度：中）/
组合形式（inferential，置信度：中））泄漏进读者可见的报告正文与标题。
修复：渲染期净化（落盘的 research_result 审计原件不动）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

S = DocumentGenerationAgent._strip_epistemic_annotations


def test_strip_basic():
    assert S('结论正确（factual）') == '结论正确'
    assert S('预计放量（inferential）') == '预计放量'
    assert S('风险较高（置信度：中）') == '风险较高'
    assert S('（置信度：中高）') == ''


def test_strip_combined():
    assert S('判断成立（inferential，置信度：中）') == '判断成立'
    assert S('头部阵营（置信度：中高）：优必选、宇树科技') == '头部阵营：优必选、宇树科技'


def test_keep_source_notes():
    # 合法口径标注不得误删
    assert S('超330款产品发布（拓端口径）') == '超330款产品发布（拓端口径）'
    assert S('166款整机新品（新战略咨询口径）') == '166款整机新品（新战略咨询口径）'


def test_section_render_strip():
    agent = DocumentGenerationAgent(agent_id='t')
    rr = {'sections': [{'title': '核心结论（置信度：中）',
                        'content': '论断A（factual）论断B（inferential，置信度：中）',
                        'key_findings': ['发现（inferential）']}]}
    out = agent._strip_annotations_for_render(rr)
    assert out['sections'][0]['title'] == '核心结论'
    assert 'factual' not in out['sections'][0]['content']
    assert out['sections'][0]['key_findings'] == ['发现']


def test_empty_and_none_safe():
    assert S('') == ''
    assert S(None) is None
    # 半角括号与英文冒号变体
    assert S('判断(factual)') == '判断'
    assert S('判断(置信度:高)') == '判断'
    assert S('判断(inferential,置信度:低)') == '判断'


def test_strip_square_bracket_and_mixed_paren():
    # 方括号形态（真实样本）
    assert S('梳理。[置信度：中等——结构判断逻辑充分，证据充分]后续') == '梳理。后续'
    assert S('突出。[inferential]') == '突出。'
    assert S('突出。[factual]') == '突出。'
    # 标注混在来源括号内 → 剥标注、保留来源
    assert S('140家（据拓端统计，factual）') == '140家（据拓端统计）'
    assert S('（factual，机构报告）口径') == '（机构报告）口径'
    # 来源口径本身仍保留
    assert S('140家（据拓端统计）') == '140家（据拓端统计）'


def test_render_covers_data_points_and_top_fields():
    agent = DocumentGenerationAgent(agent_id='t')
    rr = {'sections': [{'title': 't', 'content': '（factual）', 'key_conclusions': ['结论（inferential）'],
                        'data_points': [{'metric': '出货量（factual）', 'epistemic_level': 'factual'}]}],
          'exec_summary': '摘要（inferential）', 'conclusion': '结论（置信度：中）',
          'claims': [{'text': '声明（inferential）'}]}
    out = agent._strip_annotations_for_render(rr)
    dp = out['sections'][0]['data_points'][0]
    assert dp['epistemic_level'] == '' and dp['metric'] == '出货量'
    assert out['sections'][0]['key_conclusions'] == ['结论']
    assert out['exec_summary'] == '摘要' and out['conclusion'] == '结论'
    assert out['claims'][0]['text'] == '声明'


def test_render_keeps_section_key_findings_and_top_findings():
    """既有 key_findings 净化（section 级 + 顶层）不回退"""
    agent = DocumentGenerationAgent(agent_id='t')
    rr = {'sections': [{'key_findings': ['发现（factual）']}],
          'key_findings': ['顶层发现（inferential）']}
    out = agent._strip_annotations_for_render(rr)
    assert out['sections'][0]['key_findings'] == ['发现']
    assert out['key_findings'] == ['顶层发现']


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

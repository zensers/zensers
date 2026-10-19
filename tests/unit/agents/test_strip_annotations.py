# -*- coding: utf-8 -*-
"""渲染期剥离内部证据标注（factual/inferential/inference/speculative/置信度）的单测。

缺陷：研究管线给论断打的内部标注以多种形态（圆括号/方括号/组合/表格单元格裸标签）
泄漏进读者可见的报告正文与标题。
修复：渲染期净化（落盘的 research_result 审计原件不动）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

S = DocumentGenerationAgent._strip_epistemic_annotations

# 真实样张漏网形态全量覆盖（含保护项）
REAL_CASES = [
    # 方括号：独立 / 组合 / 长注
    ('集成及规模化量产，附加值相对突出。[inferential]', '集成及规模化量产，附加值相对突出。'),
    ('于可获取的行业信息进行分环节梳理。[置信度：中等——结构判断逻辑充分，数据交叉验证]后续',
     '于可获取的行业信息进行分环节梳理。后续'),
    ('收紧通道。[inferential，置信度：中高]', '收紧通道。'),
    ('承压。[inferential，置信度：中等偏低——prose]', '承压。'),
    # 圆括号：独立 / 组合 / 标签开头（整括号删除）
    ('企业构成庞大但高度分散的参与者基数（factual），叠加融资推力',
     '企业构成庞大但高度分散的参与者基数，叠加融资推力'),
    ('处于退出边缘（inferential，置信度：中）。', '处于退出边缘。'),
    ('收紧（speculative，置信度：中低）。', '收紧。'),
    ('成为优先选择（factual：主流厂商技术路线收敛）', '成为优先选择'),
    ('确立为行业标准架构（置信度：高，关键假设：电机国产化率达标）', '确立为行业标准架构'),
    # 标签收尾复合括号 → 保留来源
    ('整机制造的仅约140家（据拓端统计，factual）。', '整机制造的仅约140家（据拓端统计）。'),
    # markdown 表格：标签+来源括号剥标签留来源；独占格清空
    ('| 认知层级 |\n|---|\n| factual（机构报告） |\n| inferential |',
     '| 认知层级 |\n|---|\n| （机构报告） |\n|  |'),
    # 合法引用方括号不误删
    ('市场规模突破千亿[1]，详见[PDF]与[新战略咨询]口径', '市场规模突破千亿[1]，详见[PDF]与[新战略咨询]口径'),
    # 保护项：置信度自然行文 / 英文术语
    ('力控柔顺性方面仍存在差距（inferential：推断依据——2025年国内整机企业数量超140家、发布产品超330款，且多家企业已进入公开招投标环节）。', '力控柔顺性方面仍存在差距。'),
    ('复杂地形自适应和力控柔顺性方面仍存在差距（inferential：推断依据——2025年国内整机企业数量超140家、发布产品超330款（工信部），但前瞻产业研究院评估显示主流产品自主能力仍处于L2—L3阶段）。', '复杂地形自适应和力控柔顺性方面仍存在差距。'),
    ('进行分环节梳理。[置信度：中等——结构判断逻辑充分，定量锚定有待进一步核实。替代解释：①若上游关键零部件供应格局因外部管制或技术替代而剧烈变动，中游成本结构与利润分配可能偏离当前判断；②若智元等新进入者以价换量超预期，梯队边界可能重构。]下游整机厂商有望受益。', '进行分环节梳理。下游整机厂商有望受益。'),
    ('逐步提升判断的精度和置信度。', '逐步提升判断的精度和置信度。'),
    ('端侧 inference 引擎需求增长', '端侧 inference 引擎需求增长'),
]


@pytest.mark.parametrize('raw,expected', REAL_CASES)
def test_strip_real_cases(raw, expected):
    assert S(raw) == expected


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
    assert S('140家（据拓端统计）') == '140家（据拓端统计）'


def test_table_cell_bare_tag_boundary():
    # 裸标签仅删除于"单元格起始"的两种邻界形态：独占格 / 标签+来源括号
    assert S('| inferential |\n| factual（机构报告） |') == '|  |\n| （机构报告） |'
    # inference 仅作英文术语出现，表格格中不误删（独占格也保留）
    assert S('| inference |') == '| inference |'
    assert S('| inference 引擎加速 |') == '| inference 引擎加速 |'
    # 英文正文行文不碰
    assert S('on-device inference 加速') == 'on-device inference 加速'
    assert S('factual errors found in report') == 'factual errors found in report'


def test_empty_and_none_safe():
    assert S('') == ''
    assert S(None) is None
    # 半角括号与英文冒号变体
    assert S('判断(factual)') == '判断'
    assert S('判断(置信度:高)') == '判断'
    assert S('判断(inferential,置信度:低)') == '判断'


def test_section_render_strip():
    agent = DocumentGenerationAgent(agent_id='t')
    rr = {'sections': [{'title': '核心结论（置信度：中）',
                        'content': '论断A（factual）论断B（inferential，置信度：中）',
                        'key_findings': ['发现（inferential）']}]}
    out = agent._strip_annotations_for_render(rr)
    assert out['sections'][0]['title'] == '核心结论'
    assert 'factual' not in out['sections'][0]['content']
    assert out['sections'][0]['key_findings'] == ['发现']


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

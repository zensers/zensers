"""
基于真实 HTML 输出的验证测试

数据来源：research_e32d301e_report_20260529_214832.html
    结构: 8 章节, 16 图表, 0 段文本（BUG 状态）

测试目标：验证修复后，同数据源能产出带文本内容的 HTML
"""
import re
from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator


# 从实际 HTML 中提取的章节信息
REAL_SECTION_IDS = [
    "核心财务指标与盈利能力",
    "研发与创新投入",
    "供应链成本效率",
    "销量与市场份额",
    "国际化与出口",
    "财务健康、风险评估与季度业绩波动",
    "行业对标与竞争格局",
    "财务预测",
]


def _load_real_html(path):
    """读取真实 HTML 文件，返回结构信息"""
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    sections = re.findall(r'<section id="([^"]+)"', html)
    h1_titles = re.findall(r'<h1[^>]*>([^<]+)</h1>', html)
    charts = re.findall(r'<img[^>]*src="charts/([^"]+)"', html)
    text_blocks = re.findall(r'<div class="section-content">(.*?)</div>', html, re.DOTALL)
    return {
        "html_len": len(html),
        "section_count": len(sections),
        "chart_count": len(charts),
        "text_block_count": len(text_blocks),
        "has_text_content": any(len(re.sub(r'<[^>]+>', '', tb).strip()) > 50 for tb in text_blocks),
    }


def test_real_html_shows_bug_state():
    """验证真实 HTML 确实处于 BUG 状态（有图表无文本）"""
    path = r'E:\market_report_systerm\data\research_e32d301e\research_e32d301e_report_20260529_214832.html'
    info = _load_real_html(path)

    assert info["section_count"] == 8
    assert info["chart_count"] == 16
    assert info["text_block_count"] == 0, \
        f"BUG 状态: 预期 0 文本块, 实际 {info['text_block_count']}"
    assert not info["has_text_content"], \
        "BUG 状态: 不应有文本内容"


def test_aggregator_with_real_section_ids():
    """
    使用真实的 section_id 列表验证聚合器能找到所有内容
    
    真实 section_id 从 HTML 的 <section id="..."> 提取
    """
    # 模拟 engine 注入的结果，key 为真实 section id
    agent_results = {}
    for i, sid in enumerate(REAL_SECTION_IDS):
        # engine key 格式: section_N_{name}
        engine_key = f"section_{i}_{sid}"
        agent_results[engine_key] = {
            "agent_id": f"phase_1_agent_{i}",
            "content": f"这是{sid}的分析内容。包含具体财务数据和行业分析。",
            "section_id": engine_key,
            "success": True,
        }

    # framework section_details（从 section_details 构建逻辑复制）
    section_details = [
        {"id": s.lower().replace(" ", "_"), "name": s, "content": s}
        for s in REAL_SECTION_IDS
    ]

    aggregator = ResultAggregator()
    result = aggregator.aggregate(agent_results, section_details=section_details)
    result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
    sections = result_dict.get("sections", [])

    assert len(sections) == len(REAL_SECTION_IDS), \
        f"章节数匹配: 预期 {len(REAL_SECTION_IDS)}, 实际 {len(sections)}"

    empty = []
    for s in sections:
        title = s.get("title", "")
        content = s.get("content", "").strip()
        if not content or len(content) < 10:
            empty.append(title)
    assert len(empty) == 0, f"内容丢失的章节: {empty}"


def test_aggregator_engine_key_with_section_n_prefix():
    """
    验证 engine 注入的 section_N_ 前缀 key 能在聚合器中匹配
    
    这是实际数据流中 key 的格式:
      engine: "section_0_核心财务指标与盈利能力"  
      -> _normalize_key 移除前缀后: "核心财务指标与盈利能力"
    """
    from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

    for i, sid in enumerate(REAL_SECTION_IDS):
        engine_key = f"section_{i}_{sid}"
        # framework 可能使用不同标点
        framework_id = sid.replace("、", "_").replace("，", "_")

        norm_ek = _normalize_key(engine_key)
        norm_fid = _normalize_key(framework_id)

        # 至少一个方向匹配
        match = (norm_ek == norm_fid or
                 norm_ek in norm_fid or norm_fid in norm_ek)
        assert match, \
            f"无法匹配: engine='{engine_key}' -> norm='{norm_ek}', " \
            f"framework='{framework_id}' -> norm='{norm_fid}'"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=long"])

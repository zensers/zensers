"""
使用真实运行的 JSON 缓存数据验证全链路

数据源: research_e32d301e/research_result_cache.json
  8 章, 每章 1860-3812 字符内容, 无图表
  → 内容已存在缓存（聚合成功），但 HTML 输出时丢失（文档生成 BUG）

测试目标:
  1. 验证缓存数据完整性（内容确实存在）
  2. 验证聚合器能否从相同输入恢复内容  
  3. 验证文档生成 agent 的输入数据完整性
"""
import json
import pytest


CACHE_PATH = r'E:\market_report_systerm\data\research_e32d301e\research_result_cache.json'


def _load_cache():
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestRealCacheIntegrity:
    """真实缓存数据完整性验证"""

    def test_cache_has_8_sections(self):
        data = _load_cache()
        assert len(data.get("sections", [])) == 8

    def test_all_sections_have_content(self):
        data = _load_cache()
        empty = []
        for s in data["sections"]:
            content = s.get("content", "").strip()
            if not content or len(content) < 50:
                empty.append(s.get("title", ""))
        assert len(empty) == 0, f"内容为空的章节: {empty}"

    def test_content_not_placeholder(self):
        data = _load_cache()
        for s in data["sections"]:
            content = s.get("content", "")
            assert "数据不足" not in content, \
                f"{s.get('title')} 是降级占位符"
            assert "⚠️" not in content

    def test_each_section_minimum_length(self):
        data = _load_cache()
        for s in data["sections"]:
            title = s.get("title", "")
            content = s.get("content", "")
            assert len(content) >= 500, \
                f"{title} 内容不足: {len(content)} chars"

    def test_cache_structure_as_docgen_input(self):
        """
        验证缓存数据结构可作为文档生成的直接输入
        
        文档生成 research_result_data 要求:
        { topic, title, aspects, sections: [{id, title, content}], sources, key_findings }
        """
        data = _load_cache()
        assert "topic" in data
        assert "title" in data
        assert "aspects" in data
        assert "sections" in data
        assert "sources" in data
        assert "key_findings" in data

        for s in data["sections"]:
            assert "id" in s, f"section缺少id: {s.get('title')}"
            assert "title" in s
            assert "content" in s

    def test_cache_has_no_charts_in_sections(self):
        """
        缓存中没有图表信息（图表由 docgen 从 data_points 生成）
        """
        data = _load_cache()
        for s in data["sections"]:
            charts = s.get("charts", [])
            assert len(charts) == 0, \
                f"{s.get('title')} 不应有图表数据"


class TestRealCacheAggregationRoundtrip:
    """用缓存数据验证聚合器"""

    def test_aggregator_from_cache_recovers_all_content(self):
        """
        从缓存的 topic 和 section 信息重建聚合器输入，
        验证聚合器能恢复全部内容
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        data = _load_cache()

        # 缓存数据 = research_result_data 格式
        # 需要逆转为 agent_results 格式喂入聚合器
        # agent_results 格式: {key: {content, section_id, success}}
        agent_results = {}
        for i, s in enumerate(data["sections"]):
            section_name = s.get("title", "")
            agent_results[section_name] = {
                "agent_id": f"agent_{i}",
                "content": s.get("content", ""),
                "section_id": section_name,
                "success": True,
            }

        # section_details 从 aspects 构建（同 orchestrator 逻辑）
        aspects = data.get("aspects", [])
        if not aspects:
            aspects = [s.get("title", "") for s in data["sections"]]

        section_details = [
            {"id": a.lower().replace(" ", "_"), "name": a, "content": a}
            for a in aspects
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        assert len(sections) == len(data["sections"]), \
            f"章节数不匹配: 缓存={len(data['sections'])}, 聚合后={len(sections)}"

        empty = []
        for s in sections:
            title = s.get("title", "")
            content = s.get("content", "").strip()
            if not content or len(content) < 50:
                empty.append(title)
        assert len(empty) == 0, f"聚合后内容丢失: {empty}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])

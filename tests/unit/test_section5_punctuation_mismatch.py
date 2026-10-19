"""
验证 section_5 匹配失败的根因：标点符号不匹配

框架 section_id 格式（来自 ResearchRequirement.section_details）：
  {"id": a.lower().replace(" ", "_"), "name": a}
  对于中文名不含空格的情况：id = name = 原始中文（含顿号）

engine 注入的 key 格式（来自 SectionSpec.section_id）：
  section_5_财务健康_风险评估与季度业绩波动  （下划线分隔）
"""
import pytest


# replicating result_aggregator.py line 342-345 matching logic
def section_matches(framework_section_id, engine_key):
    """模拟聚合器中的章节匹配逻辑"""
    key_lower = engine_key.lower()
    section_id_lower = framework_section_id.lower()
    return key_lower == section_id_lower or section_id_lower in key_lower


class TestSectionPunctuationMismatch:
    """验证标点符号导致 section_5 匹配失败"""

    def test_normal_section_matches(self):
        """无标点符号的章节名正常匹配"""
        assert section_matches("核心财务指标与盈利能力", "section_0_核心财务指标与盈利能力")
        assert section_matches("研发与创新投入", "section_1_研发与创新投入")
        assert section_matches("供应链成本效率", "section_2_供应链成本效率")

    def test_punctuation_section_fails_to_match(self):
        """
        含顿号的章节名匹配失败
        
        framework section_id: "财务健康、风险评估与季度业绩波动"
        engine key:          "section_5_财务健康_风险评估与季度业绩波动"
        
        顿号 、  ≠ 下划线 _  → 匹配失败
        """
        framework_id = "财务健康、风险评估与季度业绩波动"
        engine_key = "section_5_财务健康_风险评估与季度业绩波动"
        
        result = section_matches(framework_id, engine_key)
        
        assert not result, \
            "BUG: 含顿号的 framework section_id 无法匹配下划线分隔的 engine key"

    def test_full_simulation_aggregator_section5_fails(self):
        """
        完整模拟聚合器对 8 个章节的匹配流程
        
        期望：section_5 匹配失败，其余 7 个成功
        """
        framework_sections = [
            {"id": "核心财务指标与盈利能力", "name": "核心财务指标与盈利能力"},
            {"id": "研发与创新投入", "name": "研发与创新投入"},
            {"id": "供应链成本效率", "name": "供应链成本效率"},
            {"id": "销量与市场份额", "name": "销量与市场份额"},
            {"id": "国际化与出口", "name": "国际化与出口"},
            {"id": "财务健康、风险评估与季度业绩波动", "name": "财务健康、风险评估与季度业绩波动"},
            {"id": "行业对标与竞争格局", "name": "行业对标与竞争格局"},
            {"id": "财务预测", "name": "财务预测"},
        ]
        
        # engine 注入的 key（section_id）
        engine_keys = [
            "section_0_核心财务指标与盈利能力",
            "section_1_研发与创新投入",
            "section_2_供应链成本效率",
            "section_3_销量与市场份额",
            "section_4_国际化与出口",
            "section_5_财务健康_风险评估与季度业绩波动",
            "section_6_行业对标与竞争格局",
            "section_7_财务预测",
        ]
        
        match_results = {}
        for i, (fs, ek) in enumerate(zip(framework_sections, engine_keys)):
            # 模拟聚合器的多步匹配
            section_id = fs["id"]
            section_name = fs["name"]
            
            matched = False
            # 方法1: section_id == key
            if ek == section_id:
                matched = True
            # 方法2: section_name == key
            elif ek == section_name:
                matched = True
            # 方法3: section_id in key
            elif section_id in ek:
                matched = True
            # 方法4: section_name in key
            elif section_name in ek:
                matched = True
            
            match_results[f"section_{i}"] = {
                "name": section_name,
                "matched": matched,
                "id": section_id,
            }
        
        # 验证前 4 个匹配成功
        for i in range(5):
            assert match_results[f"section_{i}"]["matched"], \
                f"section_{i} ({match_results[f'section_{i}']['name']}) 应匹配成功"
        # 验证后 3 个
        for i in range(6, 8):
            assert match_results[f"section_{i}"]["matched"], \
                f"section_{i} ({match_results[f'section_{i}']['name']}) 应匹配成功"
        
        # 验证 section_5 匹配失败
        assert not match_results["section_5"]["matched"], \
            "BUG: section_5（财务健康、风险评估与季度业绩波动）匹配失败！"

    def test_normalize_punctuation_fixes_matching(self):
        """验证：统一标点符号后匹配成功"""
        framework_id = "财务健康、风险评估与季度业绩波动"
        engine_key = "section_5_财务健康_风险评估与季度业绩波动"
        
        # 修复方案：匹配前统一标点（顿号→下划线）
        def normalize(s):
            return s.replace("、", "_").replace("，", "_").replace(",", "_")
        
        result = section_matches(
            normalize(framework_id), 
            normalize(engine_key)
        )
        
        assert result, "统一标点后应匹配成功"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])

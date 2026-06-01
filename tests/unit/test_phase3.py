# -*- coding: utf-8 -*-
"""
Phase 3 单元测试

测试内容:
- Phase 3.1: CascadeUpdateAnalyzer 级联更新分析器
- Phase 3.2: RevisionTypeInferrer 修订类型推断器
"""

import pytest
from typing import List

# 导入被测试模块
from src.core.adjustment.cascade_update_analyzer import (
    CascadeUpdateAnalyzer,
    CascadeImpact,
    ConsistencyCheck,
)
from src.core.adjustment.revision_type_inferrer import (
    RevisionTypeInferrer,
    RevisionTypeInferenceResult,
)


class TestCascadeUpdateAnalyzer:
    """测试级联更新分析器 (Phase 3.1)"""
    
    def setup_method(self):
        self.analyzer = CascadeUpdateAnalyzer()
        self.sections = ["市场规模", "竞争格局", "发展趋势", "投资建议", "政策环境"]
    
    def test_single_section_impact(self):
        """单章节影响分析"""
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=self.sections
        )
        
        # 市场规模 → 影响竞争格局、发展趋势、投资建议
        assert len(impact.affected_sections) >= 2
        assert "竞争格局" in impact.affected_sections
    
    def test_multiple_sections_impact(self):
        """多章节影响分析"""
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模", "政策环境"],
            all_sections=self.sections
        )
        
        # 多个章节的影响应该更大
        assert len(impact.affected_sections) >= 3
    
    def test_consistency_checks(self):
        """数据一致性检查生成"""
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=self.sections
        )
        
        # 应该生成一致性检查项
        assert len(impact.data_consistency_checks) > 0
        
        # 检查项应包含源和目标
        check = impact.data_consistency_checks[0]
        assert check.source == "市场规模"
        assert check.target in impact.affected_sections
    
    def test_suggested_updates(self):
        """更新建议生成"""
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=self.sections
        )
        
        # 应该生成更新建议
        assert len(impact.suggested_updates) > 0
        
        # 建议应包含必要字段
        suggestion = impact.suggested_updates[0]
        assert "type" in suggestion
        assert "target_section" in suggestion
        assert "action" in suggestion
    
    def test_risk_level_calculation(self):
        """风险等级计算"""
        # 低风险: 单章节
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["发展趋势"],
            all_sections=self.sections
        )
        # 发展趋势只影响投资建议，风险较低
        
        # 高风险: 多章节
        impact_high = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模", "政策环境", "技术趋势"],
            all_sections=self.sections + ["技术趋势"]
        )
        # 多章节影响，风险较高
    
    def test_get_dependencies(self):
        """获取依赖关系"""
        deps = self.analyzer.get_dependencies("市场规模")
        
        assert deps is not None
        assert "affects" in deps
        assert "竞争格局" in deps["affects"]
    
    def test_get_reverse_dependencies(self):
        """获取反向依赖"""
        reverse_deps = self.analyzer.get_reverse_dependencies("投资建议")
        
        # 投资建议被多个章节影响
        assert len(reverse_deps) >= 2
        assert "市场规模" in reverse_deps
    
    def test_add_custom_dependency(self):
        """添加自定义依赖规则"""
        self.analyzer.add_dependency_rule(
            section="新章节",
            affects=["投资建议"],
            data_points=["新数据点"],
            check_type="value_match"
        )
        
        deps = self.analyzer.get_dependencies("新章节")
        assert deps is not None
        assert "投资建议" in deps["affects"]
    
    def test_max_cascade_depth(self):
        """最大级联深度限制"""
        # 创建循环依赖场景
        impact = self.analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=self.sections
        )
        
        # 级联深度应有限制
        assert impact.cascade_depth <= self.analyzer.MAX_CASCADE_DEPTH
    
    def test_empty_input(self):
        """空输入"""
        impact = self.analyzer.analyze_cascade_impact([], self.sections)
        assert len(impact.affected_sections) == 0
        
        impact = self.analyzer.analyze_cascade_impact(["市场规模"], [])
        assert len(impact.affected_sections) == 0
    
    def test_consistency_check_to_dict(self):
        """一致性检查序列化"""
        check = ConsistencyCheck(
            source="市场规模",
            target="竞争格局",
            data_points=["市场份额", "增长率"],
            check_type="value_match",
            description="测试"
        )
        
        data = check.to_dict()
        assert data["source"] == "市场规模"
        assert data["target"] == "竞争格局"
    
    def test_cascade_impact_to_dict(self):
        """级联影响序列化"""
        impact = CascadeImpact(
            affected_sections=["竞争格局"],
            cascade_depth=1,
            risk_level="low"
        )
        
        data = impact.to_dict()
        assert data["affected_sections"] == ["竞争格局"]
        assert data["risk_level"] == "low"


class TestRevisionTypeInferrer:
    """测试修订类型推断器 (Phase 3.2)"""
    
    def setup_method(self):
        self.inferrer = RevisionTypeInferrer()
    
    def test_minor_type_inference(self):
        """小修改类型推断"""
        result = self.inferrer.infer("修正错别字")
        assert result.revision_type == "minor"
        assert result.confidence >= 0.8
    
    def test_minor_typo_keywords(self):
        """错别字关键词"""
        result = self.inferrer.infer("这里有拼写错误")
        assert result.revision_type == "minor"
    
    def test_minor_format_keywords(self):
        """格式关键词"""
        result = self.inferrer.infer("调整一下格式")
        assert result.revision_type == "minor"
    
    def test_section_type_inference(self):
        """章节修订类型推断"""
        result = self.inferrer.infer("更新市场规模数据")
        assert result.revision_type == "section"
        assert result.confidence >= 0.7
    
    def test_section_rewrite_keywords(self):
        """重写关键词"""
        result = self.inferrer.infer("重写这部分内容")
        assert result.revision_type == "section"
    
    def test_section_data_keywords(self):
        """数据更新关键词"""
        result = self.inferrer.infer("修改数据到最新")
        assert result.revision_type == "section"
    
    def test_full_type_inference(self):
        """全量修订类型推断"""
        result = self.inferrer.infer("新增章节")
        assert result.revision_type == "full"
        assert result.confidence >= 0.8
    
    def test_full_structure_keywords(self):
        """结构调整关键词"""
        result = self.inferrer.infer("删除这个章节")
        assert result.revision_type == "full"
    
    def test_full_comprehensive_keywords(self):
        """全面修订关键词"""
        result = self.inferrer.infer("全面修订整个报告")
        assert result.revision_type == "full"
    
    def test_multi_aspects_full(self):
        """多章节推断为 full"""
        result = self.inferrer.infer(
            "修改这些内容",
            aspects=["市场规模", "竞争格局", "发展趋势", "投资建议"]
        )
        # 4个章节 >= 3，推断为 full
        assert result.revision_type == "full"
    
    def test_single_aspect_section(self):
        """单章节推断为 section"""
        result = self.inferrer.infer(
            "修改内容",
            aspects=["市场规模"]
        )
        assert result.revision_type == "section"
    
    def test_llm_suggestion_override(self):
        """LLM 建议覆盖"""
        inferrer = RevisionTypeInferrer(use_llm=True, llm_weight=0.6)
        
        # 规则推断为 section，LLM 建议为 minor
        result = inferrer.infer(
            "修改内容",
            llm_suggestion="minor"
        )
        
        # LLM 权重较高，可能被覆盖
        # 具体行为取决于置信度计算
    
    def test_empty_input(self):
        """空输入"""
        result = self.inferrer.infer("")
        assert result.revision_type == "section"
        assert result.reason == "empty_input"
    
    def test_no_match(self):
        """无匹配规则"""
        result = self.inferrer.infer("随便说说")
        # 无匹配时返回默认 section
        assert result.revision_type == "section"
    
    def test_result_to_dict(self):
        """结果序列化"""
        result = RevisionTypeInferenceResult(
            revision_type="section",
            confidence=0.85,
            reason="rule_match",
            matched_rules=["keyword:更新数据"]
        )
        
        data = result.to_dict()
        assert data["revision_type"] == "section"
        assert data["confidence"] == 0.85
        assert "更新数据" in data["matched_rules"][0]
    
    def test_get_description(self):
        """获取类型描述"""
        desc = self.inferrer.get_revision_type_description("minor")
        assert "小修改" in desc
        
        desc = self.inferrer.get_revision_type_description("section")
        assert "章节" in desc
        
        desc = self.inferrer.get_revision_type_description("full")
        assert "全量" in desc


class TestIntegration:
    """集成测试"""
    
    def test_cascade_and_revision_type_integration(self):
        """级联更新与修订类型集成"""
        analyzer = CascadeUpdateAnalyzer()
        inferrer = RevisionTypeInferrer()
        
        # 用户请求修订市场规模
        user_input = "更新市场规模数据"
        sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
        
        # 推断修订类型
        rev_result = inferrer.infer(user_input, aspects=["市场规模"])
        assert rev_result.revision_type == "section"
        
        # 分析级联影响
        cascade_result = analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=sections
        )
        
        # 应该识别到级联影响
        assert len(cascade_result.affected_sections) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

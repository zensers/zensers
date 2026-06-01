# -*- coding: utf-8 -*-
"""
Phase 2 单元测试

测试内容:
- Phase 2.1: 序数词解析器
- Phase 2.2: 对话历史引用追踪器
- Phase 2.3: 增强版章节定位器
"""

import pytest
from typing import List, Dict

# 导入被测试模块
from src.core.adjustment.ordinal_parser import OrdinalReferenceParser, SectionMatch
from src.core.adjustment.conversation_reference_tracker import ConversationReferenceTracker
from src.core.adjustment.enhanced_section_locator import EnhancedSectionLocator


class TestOrdinalReferenceParser:
    """测试序数词解析器 (Phase 2.1)"""
    
    def setup_method(self):
        self.parser = OrdinalReferenceParser()
        self.sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
    
    def test_chinese_ordinal_basic(self):
        """中文序数词: 第一/第二/第三"""
        matches = self.parser.parse_and_locate("请修改第三部分", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "发展趋势"
        assert matches[0].confidence == 0.95
    
    def test_chinese_ordinal_chapter(self):
        """中文序数词: 第一章/第二章"""
        matches = self.parser.parse_and_locate("第二章需要更新", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "竞争格局"
    
    def test_chinese_ordinal_section(self):
        """中文序数词: 第一节/第二节"""
        matches = self.parser.parse_and_locate("第一节有问题", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
    
    def test_arabic_ordinal(self):
        """阿拉伯数字序数词: 第1个/第2个"""
        matches = self.parser.parse_and_locate("第2个章节", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "竞争格局"
    
    def test_english_ordinal(self):
        """英文序数词: first/second/third"""
        matches = self.parser.parse_and_locate("the third section", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "发展趋势"
    
    def test_english_ordinal_word(self):
        """英文序数词单词: first/second"""
        matches = self.parser.parse_and_locate("first section needs update", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
    
    def test_prefix_ordinal(self):
        """前N个: 前两个/前三章"""
        matches = self.parser.parse_and_locate("前两个章节", self.sections)
        assert len(matches) == 2
        assert matches[0].section_title == "市场规模"
        assert matches[1].section_title == "竞争格局"
    
    def test_suffix_ordinal(self):
        """后N个: 后两个"""
        matches = self.parser.parse_and_locate("后两个章节", self.sections)
        assert len(matches) == 2
        # 后两个 = 发展趋势, 投资建议
        titles = [m.section_title for m in matches]
        assert "发展趋势" in titles
        assert "投资建议" in titles
    
    def test_last_ordinal(self):
        """最后N个: 最后一个"""
        matches = self.parser.parse_and_locate("最后一个章节", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "投资建议"
    
    def test_chinese_number_conversion(self):
        """中文数字转换"""
        # 单字
        assert self.parser._chinese_to_int("一") == 1
        assert self.parser._chinese_to_int("五") == 5
        assert self.parser._chinese_to_int("十") == 10
        
        # 组合
        assert self.parser._chinese_to_int("十一") == 11
        assert self.parser._chinese_to_int("二十") == 20
        assert self.parser._chinese_to_int("二十一") == 21
    
    def test_out_of_range(self):
        """超出范围的序数词"""
        matches = self.parser.parse_and_locate("第十个章节", self.sections)
        # 只有4个章节，第10个不存在
        assert len(matches) == 0
    
    def test_no_ordinal(self):
        """无序数词"""
        matches = self.parser.parse_and_locate("请更新市场规模", self.sections)
        # 无序数词，返回空
        assert len(matches) == 0
    
    def test_empty_input(self):
        """空输入"""
        matches = self.parser.parse_and_locate("", self.sections)
        assert len(matches) == 0
        
        matches = self.parser.parse_and_locate("第三部分", [])
        assert len(matches) == 0


class TestConversationReferenceTracker:
    """测试对话历史引用追踪器 (Phase 2.2)"""
    
    def setup_method(self):
        self.tracker = ConversationReferenceTracker()
        self.sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
    
    def test_reference_detection(self):
        """指代词检测"""
        assert self.tracker._detect_reference("这部分需要更新")
        assert self.tracker._detect_reference("那个章节有问题")
        assert self.tracker._detect_reference("前面提到的")
        assert self.tracker._detect_reference("that section")
        assert self.tracker._detect_reference("mentioned above")
    
    def test_no_reference(self):
        """无指代词"""
        assert not self.tracker._detect_reference("请更新市场规模")
        assert not self.tracker._detect_reference("竞争格局需要修改")
    
    def test_extract_section_mentions(self):
        """提取章节引用"""
        mentions = self.tracker._extract_section_mentions(
            "竞争格局分析得不错",
            self.sections
        )
        assert len(mentions) > 0
        assert mentions[0][0] == "竞争格局"
    
    def test_reference_tracking(self):
        """对话历史引用追踪"""
        conversation = [
            {"role": "user", "content": "竞争格局分析得不错"},
            {"role": "assistant", "content": "好的，我会继续完善"},
        ]
        
        matches = self.tracker.extract_and_locate(
            "这部分数据需要更新",
            conversation,
            self.sections
        )
        
        assert len(matches) == 1
        assert matches[0].section_title == "竞争格局"
        assert matches[0].match_type == "reference"
        # 置信度 = 0.95 * 0.85 ≈ 0.81
        assert matches[0].confidence < 0.95
    
    def test_no_history(self):
        """无对话历史"""
        matches = self.tracker.extract_and_locate(
            "这部分需要更新",
            [],
            self.sections
        )
        assert len(matches) == 0
    
    def test_similarity_calculation(self):
        """相似度计算"""
        # 完全匹配
        assert self.tracker._calculate_similarity("竞争格局", "竞争格局") == 1.0
        
        # 部分匹配
        sim = self.tracker._calculate_similarity("竞争", "竞争格局")
        assert sim > 0.5
        
        # 无匹配
        sim = self.tracker._calculate_similarity("市场", "投资")
        assert sim < 0.5


class TestEnhancedSectionLocator:
    """测试增强版章节定位器 (Phase 2.3)"""
    
    def setup_method(self):
        self.locator = EnhancedSectionLocator()
        self.sections = ["市场规模", "竞争格局", "发展趋势", "投资建议"]
    
    def test_ordinal_location(self):
        """序数词定位"""
        matches = self.locator.locate("第三部分需要更新", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "发展趋势"
        assert matches[0].match_type == "ordinal"
    
    def test_reference_location(self):
        """引用定位"""
        conversation = [
            {"role": "user", "content": "竞争格局分析得不错"},
        ]
        
        matches = self.locator.locate(
            "这部分需要更新",
            self.sections,
            conversation
        )
        
        assert len(matches) == 1
        assert matches[0].section_title == "竞争格局"
        assert matches[0].match_type == "reference"
    
    def test_keyword_location(self):
        """关键词定位"""
        matches = self.locator.locate("请更新市场规模", self.sections)
        assert len(matches) == 1
        assert matches[0].section_title == "市场规模"
        assert matches[0].match_type == "keyword"
    
    def test_combined_strategies(self):
        """多策略组合"""
        conversation = [
            {"role": "user", "content": "竞争格局分析得不错"},
        ]
        
        # 同时包含序数词和关键词
        matches = self.locator.locate(
            "第三部分的市场规模需要更新",
            self.sections,
            conversation
        )
        
        # 应该匹配多个
        assert len(matches) >= 1
    
    def test_confidence_sorting(self):
        """置信度排序"""
        matches = self.locator.locate("第一部分和市场规模", self.sections)
        
        # 结果应按置信度排序
        if len(matches) > 1:
            for i in range(len(matches) - 1):
                assert matches[i].confidence >= matches[i + 1].confidence
    
    def test_min_confidence_filter(self):
        """最小置信度过滤"""
        locator = EnhancedSectionLocator(min_confidence=0.9)
        matches = locator.locate("请更新", self.sections)
        # "请更新" 不匹配任何章节，结果为空
        assert len(matches) == 0
    
    def test_disable_strategies(self):
        """禁用策略"""
        # 禁用序数词
        locator = EnhancedSectionLocator(enable_ordinal=False)
        matches = locator.locate("第三部分", self.sections)
        # 序数词被禁用，无法匹配
        assert len(matches) == 0
    
    def test_locate_with_context(self):
        """带上下文的定位"""
        conversation = [
            {"role": "user", "content": "竞争格局分析得不错"},
        ]
        
        result = self.locator.locate_with_context(
            "这部分需要更新",
            self.sections,
            conversation
        )
        
        assert "matches" in result
        assert "total_matches" in result
        assert "top_match" in result
        assert "strategies_used" in result
    
    def test_empty_input(self):
        """空输入"""
        matches = self.locator.locate("", self.sections)
        assert len(matches) == 0
        
        matches = self.locator.locate("测试", [])
        assert len(matches) == 0


class TestSectionMatch:
    """测试 SectionMatch 数据类"""
    
    def test_creation(self):
        """创建 SectionMatch"""
        match = SectionMatch(
            section_id="section_1",
            section_title="市场规模",
            confidence=0.95,
            match_type="ordinal",
            reason="用户提到第1个章节"
        )
        
        assert match.section_id == "section_1"
        assert match.section_title == "市场规模"
        assert match.confidence == 0.95
        assert match.match_type == "ordinal"
    
    def test_to_dict(self):
        """序列化"""
        match = SectionMatch(
            section_id="section_1",
            section_title="市场规模",
            confidence=0.95,
            match_type="ordinal",
            reason="测试"
        )
        
        data = match.to_dict()
        assert data["section_id"] == "section_1"
        assert data["section_title"] == "市场规模"
        assert data["confidence"] == 0.95
        assert data["match_type"] == "ordinal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

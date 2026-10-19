# -*- coding: utf-8 -*-
"""F6（格式标准 2026-10-18）：框架派生章节 MECE 确定性去重。

ses_92c64980 缺陷：framework_tree 分支直接取树名，未经任何去重，重复/
近重复章节各写一遍。修复：单列表三级去重（精确/包含/相似度），与
_merge_sections_dedup 规则一致，接入全部派生分支。

已知边界（诚实记录）：字面相似度低于阈值的语义重叠（如"核心技术演进"
vs "前沿技术方向"，bigram 重叠 ~0.2）确定性规则抓不住——由
FRAMEWORK_CONFIRM 对话提示词的 MECE 约束 + 用户框架确认兜底。
"""
from src.api.research_api import ResearchAPI


class TestDedupSectionList:
    def test_exact_duplicates_removed(self):
        sections = ["市场规模与增长", "技术演进", "市场规模与增长"]
        assert ResearchAPI._dedup_section_list(sections) == ["市场规模与增长", "技术演进"]

    def test_containment_keeps_longer(self):
        sections = ["市场规模", "市场规模与增长趋势"]
        assert ResearchAPI._dedup_section_list(sections) == ["市场规模与增长趋势"]

    def test_cjk_high_similarity_dedup(self):
        a = "全球人工智能市场规模分析"
        b = "全球人工智能市场规模深度分析"
        assert ResearchAPI._dedup_section_list([a, b]) == [b]

    def test_distinct_sections_are_kept(self):
        """语义重叠但字面相似度低的两章保留——确定性规则不越权。"""
        sections = ["核心技术演进", "前沿技术方向"]
        assert ResearchAPI._dedup_section_list(sections) == sections

    def test_english_token_similarity_dedup(self):
        a = "AI Market Size Analysis"
        b = "AI Market Size Deep Analysis"
        assert ResearchAPI._dedup_section_list([a, b]) == [b]

    def test_malformed_entries_filtered(self):
        sections = ["市场规模", "", "  ", None, 123, "技术演进"]
        assert ResearchAPI._dedup_section_list(sections) == ["市场规模", "技术演进"]

    def test_empty_input(self):
        assert ResearchAPI._dedup_section_list([]) == []

    def test_first_occurrence_position_kept(self):
        sections = ["技术演进", "市场规模", "技术演进路线"]
        assert ResearchAPI._dedup_section_list(sections) == ["技术演进路线", "市场规模"]


class TestMergeSectionsDedupDelegates:
    def test_merge_behaves_as_concat_then_dedup(self):
        primary = ["市场规模", "技术演进"]
        secondary = ["技术演进与路线", "政策监管"]
        result = ResearchAPI._merge_sections_dedup(SimpleSelf(), primary, secondary)
        assert result == ["市场规模", "技术演进与路线", "政策监管"]


class SimpleSelf:
    """最小 self 替身：_merge_sections_dedup 只依赖静态助手。"""
    _tokenize = staticmethod(ResearchAPI._tokenize)
    _bigrams = staticmethod(ResearchAPI._bigrams)
    _has_cjk = staticmethod(ResearchAPI._has_cjk)

    def _dedup_section_list(self, sections):
        return ResearchAPI._dedup_section_list(sections)

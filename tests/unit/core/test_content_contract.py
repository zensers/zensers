# tests/unit/core/test_content_contract.py
# -*- coding: utf-8 -*-
"""内容契约 C1-C6 合同测试。阈值与分级见
docs/design/2026-10-17-system-invariants-rectification-design.md §I1。"""
import pytest
from src.core.content_contract import check_content, check_finding_line

LONG_OK = ("## 核心结论\n\n2025年全球人工智能市场规模达到780亿美元，"
           "预计2026年增长至985亿美元。据IDC数据显示，制造业数字化投入"
           "带动AI应用渗透率持续提升，头部厂商份额进一步巩固。\n") * 6

META_OPEN = ("The task is to repair the chapter. The main issue: quantitative "
             "claims are unbound. Let me look at the current content. ") + LONG_OK
META_RATIO = ("我们需要回答用户。需要撰写摘要。必须遵守结构，不超过1000字。\n" * 8) + LONG_OK
DELIMITER_LEAK = "<<<REPORT_CHAPTER>>>\nSTATUS: ready\n<<<CONTENT>>>\n" + LONG_OK
DP_LEAK = "市场规模数据【DP|全球AI市场|780亿|美元|IDC】如下。\n" + LONG_OK
JSON_RESIDUE = '{"content": "章节正文", "status": "ready"}\n' + LONG_OK
PLACEHOLDER = "本章节未生成可验证内容。系统已记录该章节失败状态，请在补充证据后重新生成。"
ENGLISH_BODY = ("The artificial intelligence market is expanding rapidly. "
                "According to IDC data, the market reached 78 billion USD. ") * 8
REPETITIVE = ("人工智能技术发展迅速应用广泛前景广阔。") * 25

# 语言感知 C2：约 900 字符的干净英文章节（真实 AI 市场叙事，零 CJK）。
EN_CHAPTER = (
    "## Market Size and Growth\n\n"
    "The global artificial intelligence market reached 78 billion USD in 2025 "
    "and is projected to grow to 98.5 billion USD in 2026, according to IDC. "
    "Enterprise adoption of generative AI remains the primary growth driver: "
    "manufacturing, healthcare, and financial services together account for "
    "over 60% of total AI spending. North America leads regional demand with a "
    "38% revenue share, while Asia-Pacific shows the fastest compound annual "
    "growth rate at 24.3%. Cloud-deployed AI platforms expanded fastest, with "
    "hyperscaler revenue from AI workloads rising 41% year over year. Vendor "
    "competition intensified as foundation-model providers pushed enterprise "
    "subscriptions, and system integrators reported record implementation "
    "backlogs. Analysts expect double-digit growth to persist through 2030 as "
    "regulated industries move from pilots to production deployments. Falling "
    "inference costs further strengthen the adoption outlook among mid-sized "
    "enterprises.\n"
)

# 英文报告中的中文泄漏：英文短引语 + 大段中文正文（CJK 占比 >60%）→
# language="en" 下 C2 仅 warn 不 fail。
CJK_LEAK_EN = (
    "## Market Outlook\n\n"
    "Global enterprise AI spending keeps climbing, according to newly "
    "published industry trackers.\n\n"
    "根据IDC最新发布的全球人工智能跟踪报告，2025年全球人工智能市场规模达到780亿美元，"
    "预计2026年将增长至985亿美元。制造、医疗与金融服务三大行业贡献了超过六成的支出份额，"
    "北美市场以38%的收入占比保持领先，亚太地区则以24.3%的复合年增长率成为增速最快的区域。"
    "与此同时，边缘侧推理部署的成本在12个月内下降了近一半，为中小企业的规模化落地"
    "创造了条件，分析师预计这种双位数增长将一直持续到2030年。\n"
)


def _v(text, kind="chapter", **kw):
    return check_content(text, kind=kind, **kw)


class TestC5ContractResidue:
    def test_delimiter_leak_fails(self):
        v = _v(DELIMITER_LEAK)
        assert not v.passed and any(i.code == "C5" for i in v.issues)

    def test_dp_marker_fails(self):
        v = _v(DP_LEAK)
        assert not v.passed and any(i.code == "C5" for i in v.issues)

    def test_json_residue_fails(self):
        v = _v(JSON_RESIDUE)
        assert not v.passed and any(i.code == "C5" for i in v.issues)


class TestC1MetaReasoning:
    def test_meta_open_fails(self):
        v = _v(META_OPEN)
        assert not v.passed and any(i.code == "C1" for i in v.issues)

    def test_meta_ratio_warns_not_fails_phase1(self):
        v = _v(META_RATIO)
        assert v.passed  # 占比项 Phase 1 为 warn 级
        assert any(w.code == "C1" for w in v.warnings)

    def test_clean_chinese_no_c1(self):
        v = _v(LONG_OK)
        assert not any(i.code == "C1" for i in v.issues)


class TestC2LanguagePurity:
    def test_english_body_fails_for_long_chapter(self):
        v = _v(ENGLISH_BODY)  # len>1000，CJK 占比极低
        assert not v.passed and any(i.code == "C2" for i in v.issues)

    def test_short_chapter_c2_is_warn_only(self):
        v = _v("AI is eating the world. " * 10)  # len<1000
        assert v.passed and any(w.code == "C2" for w in v.warnings)


class TestC2LanguageAware:
    def test_english_chapter_passes_with_language_en(self):
        assert len(EN_CHAPTER) >= 900
        v = _v(EN_CHAPTER, language="en")
        assert v.passed
        assert not any(i.code == "C2" for i in v.issues)
        assert not any(w.code == "C2" for w in v.warnings)

    def test_english_chapter_fails_under_default_zh(self):
        # 默认语言 zh：英文长正文仍按中文报告阈值判 fail（锁定既有合同）。
        v = _v(EN_CHAPTER)
        assert not v.passed and any(i.code == "C2" for i in v.issues)

    def test_chinese_leak_into_english_warns_not_fails(self):
        v = _v(CJK_LEAK_EN, language="en")
        assert v.passed
        assert any(w.code == "C2" for w in v.warnings)
        assert not any(i.code == "C2" for i in v.issues)

    def test_pure_chinese_under_en_never_fails_phase1(self):
        v = _v(LONG_OK, language="en")
        assert v.passed
        assert any(w.code == "C2" for w in v.warnings)


class TestC6PlaceholderAndLength:
    def test_placeholder_text_fails(self):
        v = _v(PLACEHOLDER)
        assert not v.passed and any(i.code == "C6" for i in v.issues)

    def test_below_min_length_fails(self):
        v = _v("## 核心结论\n内容过短。", min_length=400)
        assert not v.passed and any(i.code == "C6" for i in v.issues)


class TestC3DataPointDensity:
    def test_zero_dp_long_nonqualitative_fails(self):
        v = _v(LONG_OK, data_points_count=0,
               section_name="市场规模与增长趋势")
        assert not v.passed and any(i.code == "C3" for i in v.issues)

    def test_qualitative_section_zero_dp_warns(self):
        v = _v(LONG_OK, data_points_count=0,
               section_name="政策与监管环境")
        assert v.passed and any(w.code == "C3" for w in v.warnings)

    def test_healthy_density_passes(self):
        v = _v(LONG_OK, data_points_count=8,
               section_name="市场规模与增长趋势")
        assert v.passed


class TestC4Repetition:
    def test_repetitive_body_warns_phase1(self):
        v = _v(REPETITIVE, data_points_count=5)
        assert v.passed  # C4 Phase 1 为 warn 级
        assert any(w.code == "C4" for w in v.warnings)


class TestFindingLine:
    def test_meta_finding_line_rejected(self):
        assert check_finding_line("我们需要回答用户。需要撰写摘要。必须遵守结构。") is False

    def test_real_finding_line_accepted(self):
        assert check_finding_line("2025年全球AI制造业市场规模达到76亿美元") is True


class TestVerdictShape:
    def test_verdict_fields(self):
        v = _v(LONG_OK, data_points_count=5)
        assert v.passed is True
        assert v.issues == []
        assert isinstance(v.warnings, list)
        assert v.text_len > 0

    def test_summary_kind_min_length(self):
        v = _v("太短的摘要。", kind="summary", min_length=80)
        assert not v.passed

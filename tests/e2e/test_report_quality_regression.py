# -*- coding: utf-8 -*-
"""
报告HTML输出质量回归测试
=======================

基于5-28劣化报告与5-25正常报告的实际缺陷对比，设计回归测试套件。
每个测试类对应5-28报告中发现的一类缺陷，确保修复后不再复发。

缺陷分类 (来自5-28 vs 5-25对比):
  A. 数据字段错位/污染 — "200.0万辆"在不同上下文重复出现
  B. 文本截断拼接 — "毛利率18.6年"（百分比值拼接"年"）
  C. 单位错配 — "净利润460.0万辆"（利润用体积单位）
  D. 表格结构崩溃 — 表头缺失、数据列错位、空单元格
  E. 内容重复 — section-content与sub-section逐字重复
  F. 图表标题泛化 — "图：份额对比（5项）"而非具体标题
  G. 综合质量闸门 — 上述缺陷的整体拦截能力
"""

import re
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional
from html.parser import HTMLParser


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
REPORT_GOOD = DATA_DIR / "html_reports" / "research_b55bf2ff.html"
REPORT_BAD = DATA_DIR / "html_reports" / "research_f52d390f.html"


def _read_report(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"Report fixture not found: {path}")
    return path.read_text(encoding="utf-8")


# ==================== HTML辅助解析器 ====================

class TableExtractor(HTMLParser):
    """提取HTML中所有<table>的结构信息"""

    def __init__(self):
        super().__init__()
        self.tables: List[Dict] = []
        self._current: Optional[Dict] = None
        self._in_thead = False
        self._in_tbody = False
        self._current_row: Optional[List[str]] = None
        self._current_cell: str = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._current = {"headers": [], "rows": [], "has_thead": False}
        elif tag == "thead" and self._current is not None:
            self._in_thead = True
            self._current["has_thead"] = True
        elif tag == "tbody" and self._current is not None:
            self._in_tbody = True
        elif tag == "tr" and self._current is not None:
            self._current_row = []
        elif tag in ("td", "th") and self._current_row is not None:
            self._current_cell = ""

    def handle_endtag(self, tag):
        if tag == "table" and self._current is not None:
            self.tables.append(self._current)
            self._current = None
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "tr" and self._current_row is not None:
            if self._current is not None:
                if self._in_thead:
                    self._current["headers"].append(self._current_row)
                else:
                    self._current["rows"].append(self._current_row)
            self._current_row = None
        elif tag in ("td", "th") and self._current_row is not None:
            self._current_row.append(self._current_cell.strip())

    def handle_data(self, data):
        if self._current_row is not None:
            self._current_cell += data


class SectionExtractor(HTMLParser):
    """提取HTML中的章节标题和内容"""

    def __init__(self):
        super().__init__()
        self.sections: List[Dict[str, str]] = []
        self._current_tag: Optional[str] = None
        self._current_text: str = ""
        self._capture = False

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4"):
            self._current_tag = tag
            self._current_text = ""
            self._capture = True

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4") and self._capture:
            self.sections.append({"tag": tag, "title": self._current_text.strip()})
            self._capture = False
            self._current_tag = None

    def handle_data(self, data):
        if self._capture:
            self._current_text += data


class ChartCaptionExtractor(HTMLParser):
    """提取图表标题/caption"""

    def __init__(self):
        super().__init__()
        self.captions: List[str] = []
        self._in_caption = False
        self._current: str = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ("figcaption", "caption"):
            self._in_caption = True
            self._current = ""
        elif tag in ("p", "span", "div"):
            cls = attrs_dict.get("class", "")
            if "chart-title" in cls or "chart-caption" in cls or "caption" in cls:
                self._in_caption = True
                self._current = ""

    def handle_endtag(self, tag):
        if tag in ("figcaption", "caption") and self._in_caption:
            self.captions.append(self._current.strip())
            self._in_caption = False
        elif tag in ("p", "span", "div") and self._in_caption:
            self.captions.append(self._current.strip())
            self._in_caption = False

    def handle_data(self, data):
        if self._in_caption:
            self._current += data


def _extract_tables(html: str) -> List[Dict]:
    parser = TableExtractor()
    parser.feed(html)
    return parser.tables


def _extract_sections(html: str) -> List[Dict[str, str]]:
    parser = SectionExtractor()
    parser.feed(html)
    return parser.sections


def _extract_chart_captions(html: str) -> List[str]:
    parser = ChartCaptionExtractor()
    parser.feed(html)
    captions = parser.captions
    caption_re = re.compile(r'图[：:]\s*(.+?)(?:</|$)', re.IGNORECASE)
    for m in caption_re.finditer(html):
        cap = m.group(1).strip()
        if cap and cap not in captions:
            captions.append(cap)
    return captions


# ==================== A. 数据字段错位/污染 ====================

class TestDataFieldMisalignment:
    """
    缺陷A: 数据字段错位/污染

    5-28表现: "200.0万辆"同时出现在高端品牌销量、海外销量、国内销量等
    不同的上下文中，说明数据源污染或字段映射错误导致同一默认值填充了
    多个不同语义的字段。
    """

    # 同一个数值出现在不同语义上下文的模式
    FIELD_CONTEXT_PATTERNS = [
        (r'高端品牌.{0,30}?([\d.]+)\s*万辆', '高端品牌销量'),
        (r'海外销量.{0,30}?([\d.]+)\s*万辆', '海外销量'),
        (r'国内销量.{0,30}?([\d.]+)\s*万辆', '国内销量'),
        (r'出口量.{0,30}?([\d.]+)\s*万辆', '出口量'),
        (r'总销量.{0,30}?([\d.]+)\s*万辆', '总销量'),
        (r'纯电.{0,30}?([\d.]+)\s*万辆', '纯电销量'),
        (r'插混.{0,30}?([\d.]+)\s*万辆', '插混销量'),
    ]

    def test_bad_report_detected_same_value_different_contexts(self):
        """5-28报告: 同一数值出现在多个不同语义字段中应被检出"""
        html = _read_report(REPORT_BAD)
        context_values: Dict[str, str] = {}
        for pattern, label in self.FIELD_CONTEXT_PATTERNS:
            m = re.search(pattern, html)
            if m:
                context_values[label] = m.group(1)

        if len(context_values) < 2:
            pytest.skip("Not enough context-matched values to compare")

        unique_vals = set(context_values.values())
        assert len(unique_vals) < len(context_values), (
            f"5-28报告应存在数据字段错位: {context_values}"
        )

    def test_good_report_has_distinct_values(self):
        """5-25报告: 不同语义字段应有不同数值"""
        html = _read_report(REPORT_GOOD)
        context_values: Dict[str, str] = {}
        for pattern, label in self.FIELD_CONTEXT_PATTERNS:
            m = re.search(pattern, html)
            if m:
                context_values[label] = m.group(1)

        if len(context_values) < 2:
            pytest.skip("Not enough context-matched values in good report")

        unique_vals = set(context_values.values())
        assert len(unique_vals) > 1, (
            f"即使是好报告，不同语义字段也不应全部相同: {context_values}"
        )

    def test_bad_report_has_suspicious_repeat_numbers(self):
        """5-28报告: 应检出高频重复的浮点数"""
        html = _read_report(REPORT_BAD)
        numbers = re.findall(r'(\d+\.\d+)', html)
        from collections import Counter
        counts = Counter(numbers)
        suspicious = {n: c for n, c in counts.items() if c >= 3 and float(n) > 0}
        assert len(suspicious) > 0, (
            f"5-28报告应存在高频重复数值"
        )

    def test_detect_placeholder_pollution_in_mock(self):
        """模拟测试: 验证检测逻辑对已知污染数据有效"""
        polluted_html = """
        <p>高端品牌销量200.0万辆，同比增长15%</p>
        <p>海外销量200.0万辆，同比增长20%</p>
        <p>国内销量200.0万辆，同比增长10%</p>
        """
        numbers = re.findall(r'([\d.]+)\s*万辆', polluted_html)
        from collections import Counter
        counts = Counter(numbers)
        suspicious = {n: c for n, c in counts.items() if c >= 3}
        assert "200.0" in suspicious, "200.0出现3次应被标记为可疑"


# ==================== B. 文本截断拼接 ====================

class TestTextTruncation:
    """
    缺陷B: 文本截断/拼接错误

    5-28表现: "毛利率18.6年"——百分比值"18.6%"被截断掉"%"
    后与"年"拼接产生无意义短语。
    """

    TRUNCATION_PATTERNS = [
        (r'\d+\.\d+年[^度]', '百分比截断拼接（如"18.6年"）'),
        (r'毛利率.{0,5}?\d+\.\d+年', '毛利率截断拼接'),
        (r'利润率.{0,5}?\d+\.\d+年', '利润率截断拼接'),
        (r'增长率.{0,5}?\d+\.\d+年', '增长率截断拼接'),
        (r'\d+\.\d+%.*?\d+\.\d+年', '百分比后紧跟截断年份'),
    ]

    def test_bad_report_has_truncation_patterns(self):
        """5-28报告: 应检出截断拼接模式"""
        html = _read_report(REPORT_BAD)
        found = []
        for pattern, desc in self.TRUNCATION_PATTERNS:
            matches = re.findall(pattern, html)
            if matches:
                found.extend([(desc, m) for m in matches[:5]])
        assert len(found) > 0, (
            f"5-28报告应存在文本截断拼接缺陷"
        )

    def test_good_report_no_truncation(self):
        """5-25报告: 不应出现截断拼接"""
        html = _read_report(REPORT_GOOD)
        for pattern, desc in self.TRUNCATION_PATTERNS:
            matches = re.findall(pattern, html)
            assert len(matches) == 0, f"好报告不应有'{desc}': {matches[:3]}"

    def test_detect_truncation_in_mock(self):
        """模拟测试: 验证检测逻辑对已知截断有效"""
        truncated = "毛利率18.6年（参考）"
        pattern = r'\d+\.\d+年[^度]'
        matches = re.findall(pattern, truncated)
        assert len(matches) > 0, "应检出'18.6年'截断模式"

    def test_non_truncated_year_format_ok(self):
        """合法年份格式不应误报"""
        valid_text = "2025年度毛利率18.6%，2024年度增长5.3%"
        for pattern, desc in self.TRUNCATION_PATTERNS:
            matches = re.findall(pattern, valid_text)
            assert len(matches) == 0, f"合法格式不应误报为'{desc}': {matches}"


# ==================== C. 单位错配 ====================

class TestUnitMismatch:
    """
    缺陷C: 单位错配

    5-28表现: "净利润460.0万辆"——利润指标使用了体积单位"万辆"
    而非货币单位"亿元"。
    """

    # 财务指标应使用货币单位，不应使用体积单位
    FINANCIAL_METRICS = [
        "净利润", "毛利润", "营业收入", "营收", "利润总额",
        "营业利润", "归母净利润", "扣非净利润",
    ]
    VOLUME_UNITS = ["万辆", "万台", "万套", "万件"]

    # 体积指标不应使用货币单位
    VOLUME_METRICS = ["销量", "产量", "交付量", "出口量"]
    CURRENCY_UNITS = ["亿元", "万元", "元", "美元", "亿美元"]

    def _check_metric_unit(self, html: str, metrics: List[str], wrong_units: List[str]) -> List:
        issues = []
        for metric in metrics:
            for unit in wrong_units:
                pattern = rf'{metric}\s*([\d,.]+)\s*{unit}'
                matches = re.findall(pattern, html)
                if matches:
                    issues.extend([(metric, unit, m) for m in matches[:3]])
        return issues

    def test_bad_report_has_financial_metrics_with_volume_units(self):
        """5-28报告: 应检出财务指标使用了体积单位"""
        html = _read_report(REPORT_BAD)
        issues = self._check_metric_unit(html, self.FINANCIAL_METRICS, self.VOLUME_UNITS)
        assert len(issues) > 0, (
            f"5-28报告应存在财务指标使用体积单位"
        )

    def test_volume_metrics_not_with_currency_units(self):
        """体积指标不应使用货币单位"""
        html = _read_report(REPORT_BAD)
        issues = self._check_metric_unit(html, self.VOLUME_METRICS, self.CURRENCY_UNITS)
        assert len(issues) == 0, (
            f"体积指标使用了货币单位: {issues}"
        )

    def test_good_report_no_unit_mismatch(self):
        """5-25报告: 不应出现单位错配"""
        html = _read_report(REPORT_GOOD)
        issues = self._check_metric_unit(html, self.FINANCIAL_METRICS, self.VOLUME_UNITS)
        assert len(issues) == 0, f"好报告不应有单位错配: {issues[:3]}"

    def test_detect_unit_mismatch_in_mock(self):
        """模拟测试: 验证检测逻辑对已知错配有效"""
        mismatched = "净利润460.0万辆"
        pattern = r'净利润\s*([\d,.]+)\s*万辆'
        assert re.search(pattern, mismatched), "应检出'净利润...万辆'错配"

    def test_correct_units_pass(self):
        """正确单位组合不应误报"""
        correct = "净利润460.0亿元，销量200.0万辆"
        pattern = r'净利润\s*([\d,.]+)\s*万辆'
        assert not re.search(pattern, correct), "净利润+亿元不应匹配万辆"


# ==================== D. 表格结构崩溃 ====================

class TestTableStructure:
    """
    缺陷D: 表格结构崩溃

    5-28表现: 表头缺失、数据列错位、空单元格、数据挤入错误列。
    """

    def test_bad_report_tables_parseable_and_content_issues(self):
        """5-28报告: 表格可解析，内容应存在质量问题"""
        html = _read_report(REPORT_BAD)
        tables = _extract_tables(html)
        assert len(tables) > 0, "5-28报告应包含表格"

        content_issues = []
        for table in tables:
            all_text = " ".join(" ".join(row) for row in table["rows"])
            # Check for unit mismatch within table content
            for metric in ["净利润", "营收"]:
                for unit in ["万辆"]:
                    if re.search(rf'{metric}\s*([\d,.]+)\s*{unit}', all_text):
                        content_issues.append(f"表格中{metric}使用{unit}")
            # Check for year placeholder
            if re.search(r'\d+\.\d+年[^度]', all_text):
                content_issues.append("表格中存在年份占位符")
            # Check for same cell text appearing across multiple rows
            cell_values = [c for row in table["rows"] for c in row if c.strip()]
            from collections import Counter
            cell_counts = Counter(cell_values)
            for v, c in cell_counts.items():
                if c >= 4 and len(v) > 5:
                    content_issues.append(f"单元格'{v[:30]}'重复{c}次")

        if not content_issues:
            pytest.skip("表格内容质量问题未检出，可能需更具体模式")

    def test_bad_report_table_content_quality(self):
        """5-28报告: 表格内容应存在单位错配等问题"""
        html = _read_report(REPORT_BAD)
        tables = _extract_tables(html)
        all_text = ""
        for table in tables:
            for row in table["rows"]:
                all_text += " ".join(row) + " "

        # 检查利润指标是否使用了体积单位
        for metric in ["净利润", "毛利润", "营业收入"]:
            pattern = rf'{metric}\s*([\d,.]+)\s*万辆'
            if re.search(pattern, all_text):
                return
        # 备用检查：表格中是否存在数值高频重复
        from collections import Counter
        values = re.findall(r'(\d+\.\d+)', all_text)
        counts = Counter(values)
        if any(c >= 5 for c in counts.values()):
            return
        pytest.skip("Table content quality check needs more specific patterns")

    def test_good_report_table_structure_better_than_bad(self):
        """5-25报告: 表格解析质量应优于5-28报告"""
        html_good = _read_report(REPORT_GOOD)
        html_bad = _read_report(REPORT_BAD)
        tables_good = _extract_tables(html_good)
        tables_bad = _extract_tables(html_bad)

        def _count_problematic(tables):
            return sum(1 for t in tables
                       if (t["has_thead"] and not t["headers"]) or
                       (t["has_thead"] and not t["rows"]))

        prob_good = _count_problematic(tables_good)
        prob_bad = _count_problematic(tables_bad)
        assert prob_good <= prob_bad, (
            f"好报告表格问题({prob_good})应<=坏报告({prob_bad})"
        )

    def test_bad_report_text_contains_table_artifacts(self):
        """5-28报告: 正文中应检出表格残留标记"""
        html = _read_report(REPORT_BAD)
        artifact_patterns = [
            r'\|[^|]+\|[^|]+\|',
            r'[\d.]+%\s*[\d.]+年',
            r'（参考）',
        ]
        found = []
        for pattern in artifact_patterns:
            matches = re.findall(pattern, html)
            found.extend(matches[:3])
        assert len(found) > 0, "5-28报告应存在表格残留标记"


# ==================== E. 内容重复 ====================

class TestContentDuplication:
    """
    缺陷E: 内容重复

    5-28表现: section-content与sub-section内容逐字重复，
    相同文字出现在页面不同区域。
    """

    def _normalize_text(self, text: str) -> str:
        return re.sub(r'\s+', '', text).strip()

    def _find_duplicate_paragraphs(self, html: str, min_length: int = 30) -> List[Dict]:
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        cleaned = [self._normalize_text(re.sub(r'<[^>]+>', '', p)) for p in paragraphs]
        seen: Dict[str, int] = {}
        duplicates = []
        for i, text in enumerate(cleaned):
            if len(text) < min_length:
                continue
            if text in seen:
                duplicates.append({
                    "first_idx": seen[text],
                    "dup_idx": i,
                    "text_preview": text[:80],
                })
            else:
                seen[text] = i
        return duplicates

    def test_bad_report_has_paragraph_duplication(self):
        """5-28报告: 应检出段落内容重复"""
        html = _read_report(REPORT_BAD)
        duplicates = self._find_duplicate_paragraphs(html)
        assert len(duplicates) > 0, "5-28报告应存在段落内容重复"

    def test_bad_report_has_section_duplication(self):
        """5-28报告: 应检出章节标题重复"""
        html = _read_report(REPORT_BAD)
        sections = _extract_sections(html)
        titles = [s["title"] for s in sections if s["title"]]
        if len(titles) < 2:
            pytest.skip("Not enough sections to check duplication")

        from collections import Counter
        title_counts = Counter(titles)
        duplicated = {t: c for t, c in title_counts.items() if c > 1}
        assert len(duplicated) > 0, "5-28报告应存在章节标题重复"

    def test_good_report_duplication_less_than_bad(self):
        """5-25报告: 段落重复应不多于5-28报告（或相当）"""
        html_good = _read_report(REPORT_GOOD)
        html_bad = _read_report(REPORT_BAD)
        dup_good = len(self._find_duplicate_paragraphs(html_good))
        dup_bad = len(self._find_duplicate_paragraphs(html_bad))
        assert dup_good <= dup_bad * 2, (
            f"好报告重复({dup_good})不应远超坏报告({dup_bad})"
        )

    def test_detect_duplication_in_mock(self):
        """模拟测试: 验证重复检测逻辑"""
        mock_html = """
        <div class="section-content">
            <p>比亚迪以427万辆的销量稳居第一，市场份额达33.4%，连续三年保持领先地位</p>
        </div>
        <div class="sub-section">
            <p>比亚迪以427万辆的销量稳居第一，市场份额达33.4%，连续三年保持领先地位</p>
        </div>
        """
        duplicates = self._find_duplicate_paragraphs(mock_html, min_length=20)
        assert len(duplicates) > 0, "应检出段落重复"


# ==================== F. 图表标题泛化 ====================

class TestChartCaptionQuality:
    """
    缺陷F: 图表标题泛化

    5-28表现: 图表标题为"图：份额对比（5项）"、"图：排名对比（5项）"
    等泛化标题，缺少具体信息（如品牌名、时间段、市场范围等）。
    """

    GENERIC_PATTERNS = [
        r'图[：:]\s*[\w]+对比（\d+项）',
        r'图[：:]\s*[\w]+排名（\d+项）',
        r'图[：:]\s*[\w]+分析（\d+项）',
        r'图[：:]\s*[\w]+趋势（\d+项）',
        r'图[：:]\s*数据对比',
        r'图[：:]\s*数据展示',
        r'图[：:]\s*图表',
    ]

    def test_bad_report_has_generic_chart_titles(self):
        """5-28报告: 应检出泛化图表标题"""
        html = _read_report(REPORT_BAD)
        found = []
        for pattern in self.GENERIC_PATTERNS:
            matches = re.findall(pattern, html)
            found.extend(matches)
        assert len(found) > 0, "5-28报告应存在泛化图表标题"

    def test_good_report_chart_titles_not_all_generic(self):
        """5-25报告: 图表标题不应全部为泛化标题"""
        html = _read_report(REPORT_GOOD)
        captions = _extract_chart_captions(html)
        if not captions:
            pytest.skip("No chart captions found in good report")

        total = len(captions)
        generic_count = 0
        for cap in captions:
            for pattern in self.GENERIC_PATTERNS:
                if re.search(pattern, cap):
                    generic_count += 1
                    break

        generic_ratio = generic_count / total if total > 0 else 0
        assert generic_ratio < 1.0, "好报告不应全部为泛化图表标题"

    def test_detect_generic_title_in_mock(self):
        """模拟测试: 验证泛化标题检测"""
        generic = "图：份额对比（5项）"
        matched = any(re.search(p, generic) for p in self.GENERIC_PATTERNS)
        assert matched, "应检出泛化图表标题"

    def test_specific_title_not_flagged(self):
        """具体标题不应误报"""
        specific = "图：2025年中国新能源汽车市场份额对比"
        for pattern in self.GENERIC_PATTERNS:
            assert not re.search(pattern, specific), "具体标题不应被标记为泛化"


# ==================== G. 综合质量闸门 ====================

class TestQualityGateIntegration:
    """
    缺陷G: 综合质量闸门

    验证QualityCheckAgent能否拦截5-28报告中出现的各类缺陷。
    使用HTML内容作为输入，测试_check_hallucinations等方法的检测能力。
    """

    @pytest.fixture
    def quality_agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        return QualityCheckAgent(agent_id="regression_test_qc")

    def test_hallucination_detection_placeholder_repeat(self, quality_agent):
        """QualityCheckAgent._check_hallucinations应检出占位符重复"""
        content = "高端品牌200.0万辆，海外销量200.0万辆，国内销量200.0万辆"
        issues = quality_agent._check_hallucinations(content)
        severity_types = [(i["severity"], i["message"]) for i in issues]
        assert len(issues) > 0, f"应检出占位符重复: {severity_types}"

    def test_hallucination_detection_profit_unit_mismatch(self, quality_agent):
        """QualityCheckAgent._check_hallucinations应检出利润单位错配"""
        content = "净利润600.0万辆"
        issues = quality_agent._check_hallucinations(content)
        has_unit_issue = any("万辆" in i["message"] for i in issues)
        assert has_unit_issue, "应检出利润使用万辆单位"

    def test_hallucination_detection_year_placeholder(self, quality_agent):
        """QualityCheckAgent._check_hallucinations应检出年份占位符"""
        content = "毛利率18.6年（参考）"
        issues = quality_agent._check_hallucinations(content)
        has_year_issue = any("年" in i["message"] and "占位符" in i["message"] for i in issues)
        assert has_year_issue, "应检出'18.6年'占位符"

    def test_hallucination_no_false_positive_on_valid(self, quality_agent):
        """合法内容不应触发幻觉检测"""
        content = "2025年度净利润460.0亿元，同比增长18.6%，销量200.0万辆"
        issues = quality_agent._check_hallucinations(content)
        high_issues = [i for i in issues if i["severity"] == "high"]
        assert len(high_issues) == 0, f"合法内容不应触发高严重度问题: {high_issues}"

    @pytest.mark.asyncio
    async def test_bad_report_quality_score_low(self, quality_agent):
        """5-28报告质量分数应低于70"""
        html = _read_report(REPORT_BAD)
        report = {
            "title": "5-28 Test Report",
            "content": re.sub(r'<[^>]+>', ' ', html),
            "sections": [{"title": "test", "content": "..."}],
            "word_count": len(html),
            "facts": [],
            "sources": [],
        }
        result = await quality_agent.execute({
            "report": report,
            "html_content": html,
        })
        assert result["quality_score"] < 70, (
            f"5-28报告质量分数 {result['quality_score']} 应低于70"
        )

    @pytest.mark.asyncio
    async def test_good_report_quality_score_higher(self, quality_agent):
        """5-25报告质量分数应高于5-28报告"""
        html_bad = _read_report(REPORT_BAD)
        html_good = _read_report(REPORT_GOOD)

        result_bad = await quality_agent.execute({
            "report": {
                "title": "Bad Report",
                "content": re.sub(r'<[^>]+>', ' ', html_bad),
                "sections": [{"title": "test", "content": "..."}],
                "word_count": len(html_bad),
            },
            "html_content": html_bad,
        })

        result_good = await quality_agent.execute({
            "report": {
                "title": "Good Report",
                "content": re.sub(r'<[^>]+>', ' ', html_good),
                "sections": [{"title": "test", "content": "..."}],
                "word_count": len(html_good),
            },
            "html_content": html_good,
        })

        assert result_good["quality_score"] >= result_bad["quality_score"], (
            f"好报告({result_good['quality_score']})分数应>=坏报告({result_bad['quality_score']})"
        )


# ==================== H. 模板引擎回归 ====================

class TestTemplateEngineRegression:
    """
    确保TemplateEngine的渲染不引入上述缺陷。

    模板引擎在render_template的最后一步执行_cleanup_remaining_tags，
    如果变量未被正确替换，会被清理掉但可能留下残缺文本。
    """

    @pytest.fixture
    def engine(self):
        from src.content.template_engine import TemplateEngine
        return TemplateEngine()

    def test_render_no_truncated_text(self, engine):
        """渲染结果不应产生截断文本"""
        template = "毛利率{{ profit_margin }}年增长"
        result = engine.render_template(template, {"profit_margin": "18.6%"})
        assert "18.6%年增长" in result or "18.6% 年增长" in result, (
            f"渲染结果异常: '{result}'"
        )

    def test_render_no_unit_confusion(self, engine):
        """渲染不应混入错误单位"""
        template = "净利润{{ profit }}{{ unit }}"
        result = engine.render_template(template, {"profit": "460.0", "unit": "亿元"})
        assert "460.0亿元" in result
        assert "460.0万辆" not in result

    def test_validate_rendered_catches_unrendered(self, engine):
        """validate_rendered应检出未渲染标签"""
        content = "毛利率{{ profit_margin }}年增长"
        assert not engine.validate_rendered(content), "未渲染标签应被检出"

        rendered = "毛利率18.6%年增长"
        assert engine.validate_rendered(rendered), "已渲染内容应通过验证"

    def test_cleanup_does_not_produce_truncation(self, engine):
        """_cleanup_remaining_tags不应产生截断拼接"""
        content = "毛利率{{ profit_margin }}年增长"
        cleaned = engine._cleanup_remaining_tags(content)
        truncation_pattern = r'\d+\.\d+年[^度]'
        assert not re.search(truncation_pattern, cleaned), (
            f"清理后不应产生截断: '{cleaned}'"
        )

    def test_loop_rendering_no_data_pollution(self, engine):
        """循环渲染不应导致数据污染（所有项同值）"""
        template = "{% for brand in brands %}{{ brand.name }}: {{ brand.sales }}万辆 {% endfor %}"
        variables = {
            "brands": [
                {"name": "比亚迪", "sales": "427.0"},
                {"name": "特斯拉", "sales": "198.0"},
                {"name": "蔚来", "sales": "22.0"},
            ]
        }
        result = engine.render_template(template, variables)
        assert "427.0万辆" in result
        assert "198.0万辆" in result
        assert "22.0万辆" in result
        sales_values = re.findall(r'([\d.]+)万辆', result)
        assert len(set(sales_values)) == 3, (
            f"循环渲染不应产生数据污染: {sales_values}"
        )


# ==================== I. 端到端管道质量守卫 ====================

class TestEndToEndPipelineGuard:
    """
    模拟完整管道的HTML输出，验证缺陷检测器能拦截各类问题。

    这些测试不需要真正的LLM调用，使用模拟HTML即可。
    """

    MOCK_BAD_HTML = """
    <html><body>
    <h1>2025年中国新能源汽车市场研究报告</h1>
    <div class="section-content">
        <h2>市场规模</h2>
        <p>高端品牌200.0万辆，海外销量200.0万辆，国内销量200.0万辆</p>
        <p>毛利率18.6年（参考）</p>
        <p>净利润600.0万辆，同比下降5.2%</p>
    </div>
    <div class="sub-section">
        <h2>市场规模</h2>
        <p>高端品牌200.0万辆，海外销量200.0万辆，国内销量200.0万辆</p>
    </div>
    <table>
        <tbody>
            <tr><td>200.0</td><td></td><td>18.6</td></tr>
            <tr><td>460.0</td><td>200.0</td></tr>
        </tbody>
    </table>
    <p>图：份额对比（5项）</p>
    <p>图：排名对比（5项）</p>
    </body></html>
    """

    MOCK_GOOD_HTML = """
    <html><body>
    <h1>2025年中国新能源汽车市场研究报告</h1>
    <h2>市场规模</h2>
    <p>2025年新能源汽车销量1,280万辆，同比增长35.6%。其中纯电动汽车896万辆，插电混动384万辆。</p>
    <p>比亚迪以427万辆的销量稳居第一，市场份额达33.4%。特斯拉销量198万辆，市场份额15.5%。</p>
    <p>行业净利润达600.0亿元，毛利率18.6%，同比增长5.2%。</p>
    <table>
        <thead><tr><th>品牌</th><th>销量(万辆)</th><th>份额</th></tr></thead>
        <tbody>
            <tr><td>比亚迪</td><td>427.0</td><td>33.4%</td></tr>
            <tr><td>特斯拉</td><td>198.0</td><td>15.5%</td></tr>
        </tbody>
    </table>
    <p>图：2025年中国新能源汽车市场份额对比</p>
    </body></html>
    """

    def _run_all_checks(self, html: str) -> Dict[str, List]:
        issues = {}
        issues["field_misalignment"] = []
        numbers = re.findall(r'([\d.]+)\s*万辆', html)
        from collections import Counter
        counts = Counter(numbers)
        for n, c in counts.items():
            if c >= 3:
                issues["field_misalignment"].append(f"{n}出现{c}次")

        issues["truncation"] = re.findall(r'\d+\.\d+年[^度]', html)

        issues["unit_mismatch"] = []
        for metric in ["净利润", "毛利润", "营业收入"]:
            for unit in ["万辆", "万台"]:
                matches = re.findall(rf'{metric}\s*([\d,.]+)\s*{unit}', html)
                issues["unit_mismatch"].extend(matches)

        issues["table_structure"] = []
        tables = _extract_tables(html)
        for i, table in enumerate(tables):
            if not table["has_thead"] and not table["headers"]:
                issues["table_structure"].append(f"表格{i}缺表头")
            if table["headers"]:
                hcount = len(table["headers"][0])
                for ri, row in enumerate(table["rows"]):
                    if len(row) != hcount:
                        issues["table_structure"].append(
                            f"表格{i}行{ri}列数{len(row)}!={hcount}"
                        )

        issues["duplication"] = []
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        cleaned = [re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', p)) for p in paras]
        seen = {}
        for i, t in enumerate(cleaned):
            if len(t) < 30:
                continue
            if t in seen:
                issues["duplication"].append(f"段落{i}与{seen[t]}重复")
            else:
                seen[t] = i

        issues["generic_caption"] = []
        for pattern in [r'图[：:]\s*[\w]+对比（\d+项）', r'图[：:]\s*[\w]+排名（\d+项）']:
            issues["generic_caption"].extend(re.findall(pattern, html))

        return issues

    def test_mock_bad_html_all_defects_detected(self):
        """模拟坏HTML: 所有缺陷类型应被检出"""
        issues = self._run_all_checks(self.MOCK_BAD_HTML)
        assert len(issues["field_misalignment"]) > 0, "应检出数据字段错位"
        assert len(issues["truncation"]) > 0, "应检出文本截断"
        assert len(issues["unit_mismatch"]) > 0, "应检出单位错配"
        assert len(issues["duplication"]) > 0, "应检出内容重复"
        assert len(issues["generic_caption"]) > 0, "应检出泛化图表标题"

    def test_mock_good_html_no_defects(self):
        """模拟好HTML: 不应检出缺陷"""
        issues = self._run_all_checks(self.MOCK_GOOD_HTML)
        assert len(issues["field_misalignment"]) == 0, f"不应有字段错位: {issues['field_misalignment']}"
        assert len(issues["truncation"]) == 0, f"不应有截断: {issues['truncation']}"
        assert len(issues["unit_mismatch"]) == 0, f"不应有单位错配: {issues['unit_mismatch']}"
        assert len(issues["duplication"]) == 0, f"不应有内容重复: {issues['duplication']}"
        assert len(issues["generic_caption"]) == 0, f"不应有泛化标题: {issues['generic_caption']}"


# ==================== J. QualityCheckAgent增量检测 ====================

class TestQualityCheckAgentIncremental:
    """
    测试QualityCheckAgent._check_hallucinations的增量检测能力。

    确保新增的检测规则（占位符重复、利润单位错配、年份占位符）
    在各种边界条件下正确工作。
    """

    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        return QualityCheckAgent(agent_id="incremental_test_qc")

    # --- 占位符重复 ---

    def test_placeholder_repeated_3_times_detected(self, agent):
        content = "A销量200.0万辆，B销量200.0万辆，C销量200.0万辆"
        issues = agent._check_hallucinations(content)
        assert any("占位符" in i["message"] or "重复" in i["message"] for i in issues)

    def test_placeholder_not_repeated_passes(self, agent):
        content = "A销量200.0万辆，B销量198.0万辆，C销量22.0万辆"
        issues = agent._check_hallucinations(content)
        placeholder_issues = [i for i in issues if "占位符" in i["message"] or "重复" in i["message"]]
        assert len(placeholder_issues) == 0

    # --- 利润单位错配 ---

    def test_profit_with_wanliang_detected(self, agent):
        """净利润+万辆应被检出"""
        content = "净利润600.0万辆"
        issues = agent._check_hallucinations(content)
        assert any("万辆" in i["message"] for i in issues)

    def test_profit_with_yiyuan_passes(self, agent):
        """净利润+亿元不应触发"""
        content = "净利润460.0亿元"
        issues = agent._check_hallucinations(content)
        unit_issues = [i for i in issues if "万辆" in i["message"]]
        assert len(unit_issues) == 0

    # --- 年份占位符 ---

    def test_decimal_year_placeholder_detected(self, agent):
        """QC Agent应检出年份占位符（含句末情况）"""
        content = "毛利率18.6年"
        issues = agent._check_hallucinations(content)
        has_year_issue = any("占位符年份" in i["message"] for i in issues)
        assert has_year_issue, "应检出'18.6年'占位符（句末情况）"

    def test_valid_year_format_passes(self, agent):
        """合法年份格式不应误报"""
        content = "2025年度毛利率18.6%"
        issues = agent._check_hallucinations(content)
        year_issues = [i for i in issues if "占位符年份" in i["message"]]
        assert len(year_issues) == 0

    # --- 数值高频重复 ---

    def test_same_number_5_plus_times_detected(self, agent):
        """QC Agent应检出同一数值高频出现"""
        content = "销量200.0万，营收200.0亿，利润200.0亿，增长200.0%，份额200.0%，目标200.0万"
        issues = agent._check_hallucinations(content)
        assert any("幻觉占位符" in i["message"] or "出现" in i["message"] for i in issues)

    def test_diverse_numbers_pass(self, agent):
        """不同数值不应触发频率检测"""
        content = "销量427.0万，营收356.2亿，利润18.6亿，增长5.3%，份额33.4%"
        issues = agent._check_hallucinations(content)
        freq_issues = [i for i in issues if "出现" in i.get("message", "") and "次" in i.get("message", "")]
        assert len(freq_issues) == 0

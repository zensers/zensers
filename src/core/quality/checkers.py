# -*- coding: utf-8 -*-
"""
Quality Checkers
================

Provides three-stage quality checking:
1. DataCollectionQualityChecker - Data collection quality check
2. AnalysisQualityChecker - Analysis quality check
3. ReportQualityChecker - Report quality check

Design principles:
1. Threshold control - simple score + threshold judgment
2. Industry research must be high quality - only set high quality thresholds
3. Feedback loop - retry if not passed

Usage example:
    from src.config.settings import settings
    
    checker = DataCollectionQualityChecker(
        threshold=settings.quality.threshold_data_collection
    )
    
    result = checker.check(data, context)
    if result.passed:
        print(f"Quality check passed: {result.score}")
    else:
        print(f"Quality check failed: {result.issues}")
"""

import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Literal
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    """Quality check result"""
    checker_type: str                    # Checker type
    score: float                         # Quality score (0-100)
    threshold: float                     # Threshold
    passed: bool                         # Whether passed
    issues: List[str] = field(default_factory=list)      # Issue descriptions
    suggestions: List[str] = field(default_factory=list) # Improvement suggestions
    details: Dict[str, Any] = field(default_factory=dict) # Detailed info
    checked_at: datetime = field(default_factory=datetime.now)
    score_scale: Literal["0-1", "0-100"] = "0-100"  # 分数尺度，默认 0-100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "checker_type": self.checker_type,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
            "score_scale": self.score_scale,
        }


class BaseQualityChecker(ABC):
    """
    Base quality checker
    
    All checkers must implement:
    1. get_checker_type() - return checker type
    2. calculate_score() - calculate quality score
    3. generate_suggestions() - generate improvement suggestions
    """
    
    def __init__(self, threshold: float = 70.0):
        """
        Initialize checker
        
        Args:
            threshold: Quality threshold (0-100)
        """
        self.threshold = threshold
    
    @abstractmethod
    def get_checker_type(self) -> str:
        """Return checker type"""
        ...
    
    @abstractmethod
    def calculate_score(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate quality score
        
        Args:
            data: Data to check
            context: Check context
            
        Returns:
            Quality score (0-100)
        """
        ...
    
    def check(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> QualityResult:
        """
        Execute quality check
        
        Args:
            data: Data to check
            context: Check context
            
        Returns:
            QualityResult: Check result
        """
        checker_type = self.get_checker_type()
        
        try:
            # Validate data integrity
            if not data or not isinstance(data, dict):
                logger.warning(f"[{checker_type}] Data format incomplete")
                return QualityResult(
                    checker_type=checker_type,
                    score=0.0,
                    threshold=self.threshold,
                    passed=False,
                    issues=["Data format incomplete, cannot perform quality check"],
                    suggestions=["Ensure data is a non-empty dictionary"],
                )
            
            # Calculate score
            score = self.calculate_score(data, context)
            
            # Determine if passed
            passed = score >= self.threshold
            
            # Generate issue list
            issues = []
            if not passed:
                issues.append(f"Quality score {score:.1f} is below threshold {self.threshold}")
            
            # Get detailed info
            details = self._get_details(data, context)
            
            # Generate suggestions
            suggestions = self.generate_suggestions(score, data, context)
            
            logger.info(
                f"[{checker_type}] Check complete: "
                f"score={score:.1f}, threshold={self.threshold}, passed={passed}"
            )
            
            return QualityResult(
                checker_type=checker_type,
                score=score,
                threshold=self.threshold,
                passed=passed,
                issues=issues,
                suggestions=suggestions,
                details=details,
            )
            
        except Exception as e:
            logger.error(f"[{checker_type}] Check failed: {e}")
            return QualityResult(
                checker_type=checker_type,
                score=0.0,
                threshold=self.threshold,
                passed=False,
                issues=[f"Check process error: {str(e)}"],
                suggestions=["Check input data format and content"],
            )
    
    def _validate_data(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Validate data integrity
        
        Args:
            data: Data to validate
            context: Check context
            
        Returns:
            Whether data is valid
        """
        return bool(data and isinstance(data, dict))
    
    @abstractmethod
    def generate_suggestions(
        self,
        score: float,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Generate improvement suggestions"""
        ...
    
    def _get_details(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get detailed info"""
        return {}


class DataCollectionQualityChecker(BaseQualityChecker):
    """
    Data Collection Quality Checker
    
    Check dimensions:
    1. Data volume - sufficient data
    2. Source credibility - authoritative sources
    3. Data quality score - Skill output quality assessment
    4. Coverage - key information coverage
    
    Weight allocation:
    - Data volume: 30%
    - Quality score: 40%
    - Source credibility: 30%
    """
    
    def __init__(self, threshold: float = 80.0):  # Q-FIX-4: was 70
        super().__init__(threshold)
    
    def get_checker_type(self) -> str:
        return "data_collection"
    
    def calculate_score(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate data collection quality score
        
        Args:
            data: Data containing quality_metadata
            context: Check context
            
        Returns:
            Quality score (0-100)
        """
        quality_metadata = data.get("quality_metadata", {})
        
        # 1. Data volume score (weight 30%)
        volume_score = self._calculate_volume_score(quality_metadata)
        
        # 2. Quality score (weight 40%)
        quality_score = quality_metadata.get("quality_score", 50.0)
        
        # 3. Source credibility (weight 30%)
        source_score = self._calculate_source_score(quality_metadata)
        
        # Weighted average
        final_score = volume_score * 0.3 + quality_score * 0.4 + source_score * 0.3
        
        return min(final_score, 100.0)
    
    def _calculate_volume_score(self, metadata: Dict[str, Any]) -> float:
        """Calculate data volume score"""
        data_volume = metadata.get("data_volume", 0)
        
        if data_volume >= 100:
            return 100.0
        elif data_volume >= 50:
            return 80.0
        elif data_volume >= 20:
            return 60.0
        elif data_volume >= 10:
            return 40.0
        elif data_volume >= 5:
            return 20.0
        else:
            return 10.0
    
    def _calculate_source_score(self, metadata: Dict[str, Any]) -> float:
        """Calculate source credibility score"""
        sources = metadata.get("sources", [])
        
        if not sources:
            return 30.0  # Base score when no sources
        
        # Authoritative sources get full score, others get partial
        authoritative_keywords = [
            "gov", "政府", "official", "官方", "report", "报告",
            "statistics", "统计局", "association", "协会",
        ]
        
        authoritative_count = 0
        for source in sources:
            source_lower = source.lower() if isinstance(source, str) else ""
            if any(kw in source_lower for kw in authoritative_keywords):
                authoritative_count += 1
        
        # Weighted average
        authoritative_ratio = authoritative_count / len(sources) if sources else 0
        return 80.0 * authoritative_ratio + 30.0 * (1 - authoritative_ratio)
    
    def generate_suggestions(
        self,
        score: float,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Generate improvement suggestions"""
        suggestions = []
        metadata = data.get("quality_metadata", {})
        
        # Insufficient data volume
        if metadata.get("data_volume", 0) < 20:
            suggestions.append("Consider expanding search keywords and increasing data sources")
            suggestions.append("Try searching official statistics or industry reports")
        
        # Low source credibility
        if metadata.get("sources"):
            if self._calculate_source_score(metadata) < 60:
                suggestions.append("Prioritize highly credible sources such as government websites and authoritative institutions")
        
        return suggestions
    
    def _get_details(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get detailed info"""
        metadata = data.get("quality_metadata", {})
        return {
            "data_volume": metadata.get("data_volume", 0),
            "sources_count": len(metadata.get("sources", [])),
            "quality_score": metadata.get("quality_score", 0),
        }


class AnalysisQualityChecker(BaseQualityChecker):
    """
    Analysis Quality Checker (Q-FIX-1: rewritten from keyword counting to structure assessment)
    
    Check dimensions:
    1. Structure completeness (40%): 5-segment framework present with context validation
    2. Data caliber declaration rate (30%): numeric values carry caliber/source annotations
    3. Counter-evidence completeness (20%): gradient scoring for boundary conditions
    4. Quantified decomposition rate (10%): gradient scoring for causal decomposition
    """
    
    STRUCTURE_MARKERS = {
        "core_judgment": {
            "keywords": ["核心判断", "核心结论", "Core Judgment", "核心观点", "核心主张"],
            "min_context_chars": 50,
        },
        "data_support": {
            "keywords": ["数据来源", "Source", "来源", "数据显示", "据", "统计", "调研"],
            "min_context_chars": 30,
        },
        "causal_decomposition": {
            "keywords": ["贡献", "个百分点", "其中", "分解", "因为", "因此", "驱动", "拉动", "源于"],
            "min_context_chars": 40,
        },
        "counter_evidence": {
            "keywords": ["如果", "若", "边界条件", "风险在于", "但需注意", "当",
                         "然而", "不过", "需要注意的是", "潜在风险", "不确定性",
                         "风险", "限制", "假设"],
            "min_context_chars": 30,
            "exclude_trivial": True,
        },
        "implication": {
            "keywords": ["意味着", "含义", "对投资", "对决策", "建议", "启示", "影响", "指向"],
            "min_context_chars": 30,
        },
    }
    
    CALIBER_PATTERNS = [
        r"(?:A股|港股|美股|GAAP|IFRS|纳斯达克|纽交所|深交所)口径",
        r"含.*权益|不含.*权益",
        r"来源[：:].+",
        r"(?:同比|环比|年化|累计)(?:增长|变化|变动)",
        r"(?:调整后|调整前|经调整)",
    ]
    
    TRIVIAL_COUNTER_PATTERNS = [
        r"如果[你我他她]",
        r"如果需要",
        r"如果.*可以",
        r"若要",
        r"当[你我他她]",
    ]
    
    def __init__(self, threshold: float = 85.0):
        super().__init__(threshold)
    
    def get_checker_type(self) -> str:
        return "analysis"
    
    def calculate_score(self, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> float:
        content = data.get("content", "")
        if not content:
            return 0.0
        
        structure_score = self._check_structure(content) * 0.40
        caliber_score = self._check_caliber_coverage(content) * 0.30
        counter_score = self._check_counter_evidence(content) * 0.20
        quant_score = self._check_quantified_decomposition(content) * 0.10
        
        return min(structure_score + caliber_score + counter_score + quant_score, 100.0)
    
    def _check_structure(self, content: str) -> float:
        """Check 5-segment structure with context validation."""
        segments_found = 0
        for section_name, config in self.STRUCTURE_MARKERS.items():
            keywords = config["keywords"]
            min_ctx = config.get("min_context_chars", 30)
            found = False
            for kw in keywords:
                idx = content.find(kw)
                while idx != -1:
                    start = max(0, idx - 20)
                    end = min(len(content), idx + len(kw) + min_ctx)
                    context = content[start:end].strip()
                    if len(context) >= min_ctx:
                        if section_name == "counter_evidence" and config.get("exclude_trivial"):
                            if self._is_trivial_counter(kw, context):
                                idx = content.find(kw, idx + len(kw))
                                continue
                        found = True
                        break
                    idx = content.find(kw, idx + len(kw))
            if found:
                segments_found += 1
        return (segments_found / 5.0) * 100.0
    
    @staticmethod
    def _is_trivial_counter(keyword: str, context: str) -> bool:
        return any(re.search(p, context) for p in AnalysisQualityChecker.TRIVIAL_COUNTER_PATTERNS)
    
    def _check_caliber_coverage(self, content: str) -> float:
        """Check if numeric references carry caliber annotations."""
        numeric_refs = re.findall(r'\d+\.?\d*\s*(亿元|亿美元|%|万辆|GWh|万元|元)', content)
        caliber_refs = sum(1 for p in self.CALIBER_PATTERNS if re.search(p, content))
        if len(numeric_refs) == 0:
            return 50.0
        ratio = caliber_refs / max(1, len(numeric_refs) * 0.3)
        return min(100.0, ratio * 100.0)
    
    def _check_counter_evidence(self, content: str) -> float:
        """Gradient scoring for counter-evidence and boundary conditions."""
        counter_indicators = [
            (r'(?:然而|不过|但是|但需注意|需要注意的是)[^。？！；…\n]{10,}', 1.0),
            (r'(?:风险|不确定性|边界条件|限制|假设)[^。？！；…\n]{10,}', 0.8),
            (r'(?:如果|若|当)[^。？！；…\n]{15,}(?:则|那么|可能|将|会)', 0.6),
            (r'(?:如果|若)[^。？！；…\n]{5,}', 0.2),
        ]
        max_score = 0.0
        for pattern, weight in counter_indicators:
            matches = re.findall(pattern, content)
            if matches:
                score = min(len(matches) / 3.0, 1.0) * weight * 100
                max_score = max(max_score, score)
        return max_score
    
    def _check_quantified_decomposition(self, content: str) -> float:
        """Gradient scoring for quantified causal decomposition."""
        patterns_strong = [
            r'其中[^。]*贡献[^。]*\d+',
            r'分解为[^。]*\d+[^。]*\d+',
            r'\d+[^。]*个百分点[^。]*源于',
            r'(?:驱动|拉动|贡献)[^。]*\d+\.?\d*\s*(?:%|个百分点)',
        ]
        patterns_partial = [
            r'(?:其中|分解)[^。]{5,}\d+',
            r'(?:增长|下降|变化)[^。]{3,}\d+\.?\d*\s*%',
        ]
        for p in patterns_strong:
            if re.search(p, content):
                return 100.0
        partial_count = sum(1 for p in patterns_partial if re.search(p, content))
        if partial_count >= 2:
            return 70.0
        if partial_count == 1:
            return 40.0
        return 0.0
    
    def generate_suggestions(self, score: float, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> List[str]:
        suggestions = []
        content = data.get("content", "")
        if not content:
            suggestions.append("Analysis content is empty, need to regenerate")
            return suggestions
        structure = self._check_structure(content)
        if structure < 80:
            suggestions.append("Ensure all 5 required segments are present: core judgment, data support, causal decomposition, counter evidence, implication")
        if self._check_caliber_coverage(content) < 70:
            suggestions.append("Add caliber/source annotations to numeric references")
        if self._check_counter_evidence(content) < 50:
            suggestions.append("Include boundary conditions for each major conclusion")
        return suggestions
    
    def _get_details(self, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = data.get("content", "")
        return {"content_length": len(content) if content else 0, "has_content": bool(content)}


class ReportQualityChecker(BaseQualityChecker):
    """
    Report Quality Checker (Enhanced)
    
    Check dimensions:
    1. Completeness - all required sections are present (weight 10%)
    2. Cross-chapter consistency - no contradictory conclusions (weight 35%)
    3. Data redundancy - no repeated data points across chapters (weight 20%)
    4. Finding provenance - synthesis sections cite research findings (weight 35%)
    5. External search audit - synthesis sections must not call search_skill (gate)
    
    Weight allocation:
    - Completeness: 10%
    - Cross-chapter consistency: 35%
    - Data redundancy: 20%
    - Finding provenance: 35%
    - External search audit: gate (0%, auto-fail if triggered)
    """
    
    # 跨章矛盾检测用的反义词对
    CONTRADICTION_PAIRS = [
        ("看涨", "看空"), ("上涨", "下跌"), ("上升", "下降"),
        ("增长", "减少"), ("增加", "降低"), ("扩张", "收缩"),
        ("乐观", "悲观"), ("看好", "看衰"), ("供不应求", "供过于求"),
        ("牛市", "熊市"), ("positive", "negative"),
        ("increase", "decrease"), ("grow", "shrink"),
        ("optimistic", "pessimistic"), ("bullish", "bearish"),
    ]
    
    def __init__(self, threshold: float = 80.0):
        super().__init__(threshold)
    
    def get_checker_type(self) -> str:
        return "report"
    
    def calculate_score(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate report quality score using enhanced dimensions.
        
        Expected data format:
        {
            "sections": [{ "id": str, "content": str, "role": str }, ...],
            "findings": [{ "section_id": str, "core_claims": [...], "key_data_points": [...] }, ...],
            "execution_logs": [{ "section_id": str, "skills_used": [...] }, ...],
        }
        
        context format:
        {
            "synthesis_section_ids": [str, ...],
            "research_section_ids": [str, ...],
            "core_question": str,                      # 报告核心问题
            "section_roles": {sid: str, ...},          # 各章节角色描述
        }
        """
        sections = data.get("sections", data.get("content", ""))
        context = context or {}
        
        # 1. Completeness (10%)
        completeness_score = self._check_completeness(sections)
        
        # 2. Cross-chapter consistency (35%)
        sections_list = sections if isinstance(sections, list) else []
        consistency_score = self._check_cross_chapter_consistency(sections_list)
        
        # 3. Data redundancy (20%)
        redundancy_score = self._check_data_redundancy(sections_list)
        
        # 4. Finding provenance (35%)
        provenance_score = self._check_finding_provenance(data, context)
        
        # 5. External search audit (gate)
        search_violation = self._check_external_search_audit(data, context)
        
        # Gate: if synthesis sections called search_skill, auto-fail
        if search_violation:
            return 0.0
        
        # 6. Framework compliance (bonus, up to +10)
        framework_bonus = self._check_framework_compliance(sections_list, context)
        
        # Weighted average
        final_score = (
            completeness_score * 0.10 +
            consistency_score * 0.35 +
            redundancy_score * 0.20 +
            provenance_score * 0.35
        ) + framework_bonus
        
        return min(final_score, 100.0)
    
    # ── 维度 1: Completeness ──────────────────────────
    
    def _check_completeness(self, sections: Any) -> float:
        """Check completeness with content validation (P1-3)."""
        if not sections:
            return 0.0
        
        if isinstance(sections, list):
            count_score = 0
            if len(sections) >= 10: count_score = 60
            elif len(sections) >= 7: count_score = 50
            elif len(sections) >= 5: count_score = 40
            elif len(sections) >= 3: count_score = 30
            else: count_score = 10
            
            content_score = 0
            non_empty = 0
            total_chars = 0
            for s in sections:
                text = s.get("content", "") if isinstance(s, dict) else str(s)
                stripped = text.strip()
                if stripped:
                    non_empty += 1
                    total_chars += len(stripped)
            if len(sections) > 0:
                content_ratio = non_empty / len(sections)
                content_score = content_ratio * 40
            
            return min(count_score + content_score, 100.0)
        
        if isinstance(sections, str):
            text = sections
            required_sections_found = 0
            required_keywords = ["市场", "竞争", "趋势", "market", "competition", "trend"]
            for kw in required_keywords:
                if kw in text:
                    required_sections_found += 1
            return (required_sections_found / len(required_keywords)) * 100
        
        return 50.0
    
    # ── 维度 2: Cross-chapter consistency (Q-FIX-2: full-text numeric contradiction detection) ───
    
    _METRIC_PATTERNS_FOR_CROSS_CHECK = [
        (r'(?:净利润|归母净利润|扣非净利润)[^\d]*?(\d+\.?\d*)\s*亿元', "净利润"),
        (r'(?:营业)?收入[^\d]*?(\d+\.?\d*)\s*亿元', "营收"),
        (r'(?:总)?销量[^\d]*?(\d+\.?\d*)\s*万辆', "销量"),
        (r'(?:研发|R&D)(?:投入|费用)?[^\d]*?(\d+\.?\d*)\s*亿元', "研发投入"),
        (r'毛利率[^\d]*?(\d+\.?\d*)\s*%', "毛利率"),
        (r'(?:市场)?份额[^\d]*?(\d+\.?\d*)\s*%', "市占率"),
        (r'增长率[^\d]*?(\d+\.?\d*)\s*%', "增长率"),
        (r'财务费用[^\d]*?(\d+\.?\d*)\s*亿元', "财务费用"),
        (r'现金流[^\d]*?(\d+\.?\d*)\s*亿元', "现金流"),
        (r'负债[率]?[^\d]*?(\d+\.?\d*)\s*%', "负债率"),
    ]
    
    def _check_cross_chapter_consistency(self, sections: List[Any]) -> float:
        """
        Q-FIX-2: Full-text numeric contradiction detection across chapters.
        Extracts (metric, value) pairs from ALL sections and detects conflicts (>5% difference).
        Only compares entries with the same year AND caliber.
        """
        if not sections or len(sections) < 2:
            return 70.0
        
        from collections import defaultdict
        
        metric_values = defaultdict(list)  # {metric_year_caliber: [(value, section_id), ...]}
        
        for idx, s in enumerate(sections):
            text = s.get("content", "") if isinstance(s, dict) else (s if isinstance(s, str) else "")
            sid = s.get("id", f"section_{idx}") if isinstance(s, dict) else f"section_{idx}"
            if not text:
                continue
            
            for pattern, metric_name in self._METRIC_PATTERNS_FOR_CROSS_CHECK:
                for match in re.finditer(pattern, text):
                    try:
                        value = float(match.group(1))
                        window = text[max(0, match.start()-40):match.start()+40]
                        years = re.findall(r'(20\d{2})', window)
                        year = years[-1] if years else "unknown"
                        
                        caliber_parts = []
                        if '归母' in window or '归母' in metric_name:
                            caliber_parts.append('归母')
                        if '扣非' in window or '扣非' in metric_name:
                            caliber_parts.append('扣非')
                        caliber = '_'.join(caliber_parts) if caliber_parts else 'default'
                        
                        metric_values[f"{metric_name}_{year}_{caliber}"].append((value, sid))
                    except (ValueError, IndexError):
                        continue
        
        if not metric_values:
            return 70.0
        
        contradictions = 0
        total = 0
        for key, entries in metric_values.items():
            if len(entries) >= 2:
                parts = key.split('_')
                year = parts[1] if len(parts) >= 2 else "unknown"
                if year == "unknown":
                    continue
                total += 1
                values = [e[0] for e in entries]
                max_v, min_v = max(values), min(values)
                if min_v > 0 and (max_v - min_v) / min_v > 0.05:
                    contradictions += 1
                    logger.warning(f"Cross-chapter numeric contradiction: {key} values={values}")
        
        if total == 0:
            return 100.0
        
        score = max(0.0, 100.0 - (contradictions / total) * 100)
        return score
    
    # ── 维度 3: Data redundancy ────────────────────────
    
    _DATA_POINT_RE = re.compile(r"(\d+\.?\d*)\s*(亿元|亿美元|元/斤|元/公斤|%|万吨|亿羽|亿只|亿|万)")
    
    def _check_data_redundancy(self, sections: List[Any]) -> float:
        """
        Check if the same data point appears in 2+ research chapters.
        """
        if not sections or len(sections) < 2:
            return 70.0
        
        # Collect all numeric data points with their section roles
        data_points_by_section = []
        for s in sections:
            text = ""
            role = ""
            if isinstance(s, dict):
                text = s.get("content", "")
                role = s.get("role", s.get("section_role", ""))
            elif isinstance(s, str):
                text = s
            
            points = set()
            for match in self._DATA_POINT_RE.finditer(text):
                value = match.group(1)
                unit = match.group(2)
                prefix = text[max(0, match.start()-20):match.start()]
                metric_hint = re.sub(r'[\s\d，。、：；]+$', '', prefix)[-10:] if prefix else ""
                points.add(f"{metric_hint}|{value}|{unit}")
            data_points_by_section.append((points, role))
        
        if not data_points_by_section:
            return 100.0
        
        # Count occurrences of each data point
        all_points = []
        for points, _ in data_points_by_section:
            all_points.extend(points)
        
        point_counts = Counter(all_points)
        
        # Only count redundancies in ANALYSIS/DATA_COLLECTION sections (not SYNTHESIS)
        research_points = Counter()
        for points, role in data_points_by_section:
            if role in ("analysis", "data_collection", "ANALYSIS", "DATA_COLLECTION"):
                for p in points:
                    research_points[p] += 1
        
        redundant_count = sum(1 for v in research_points.values() if v >= 2)
        unique_count = len(research_points)
        
        if unique_count == 0:
            return 100.0
        
        # Score based on redundancy ratio
        redundancy_ratio = redundant_count / unique_count
        score = max(0.0, 100.0 - redundancy_ratio * 100)
        return score
    
    # ── 维度 4: Finding provenance ─────────────────────
    
    def _check_finding_provenance(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Check if synthesis sections reference research findings.
        Relies on SectionFindings[] from findings_extractor.
        """
        findings = data.get("findings", [])
        sections = data.get("sections", [])
        synthesis_ids = set(context.get("synthesis_section_ids", [])) if context else set()
        
        if not findings or not synthesis_ids:
            return 50.0
        
        # Collect all core claims from research findings
        research_claims = []
        for f in findings:
            if isinstance(f, dict):
                if f.get("section_id") not in synthesis_ids:
                    research_claims.extend(f.get("core_claims", []))
        
        if not research_claims:
            return 50.0
        
        # Check if synthesis sections mention research claims
        synthesis_texts = []
        for s in sections:
            sid = ""
            text = ""
            if isinstance(s, dict):
                sid = s.get("id", "")
                text = s.get("content", "")
            if sid in synthesis_ids and text:
                synthesis_texts.append(text)
        
        if not synthesis_texts:
            return 50.0
        
        combined_text = " ".join(synthesis_texts).lower()
        covered_count = 0
        for claim in research_claims:
            # Check if key terms from the claim appear in synthesis text
            key_terms = [w for w in re.split(r'[\s，。、：；！？]+', claim) if len(w) > 0]
            if not key_terms:
                continue
            match_count = sum(1 for t in key_terms if t.lower() in combined_text)
            if match_count >= max(1, len(key_terms) * 0.3):
                covered_count += 1
        
        coverage_ratio = covered_count / len(research_claims) if research_claims else 1.0
        return coverage_ratio * 100.0
    
    # ── 维度 5: External search audit (gate) ───────────
    
    def _check_external_search_audit(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if any synthesis agent called search_skill.
        Returns True if violation found (auto-fail).
        """
        execution_logs = data.get("execution_logs", [])
        synthesis_ids = set(context.get("synthesis_section_ids", [])) if context else set()
        
        for log in execution_logs:
            section_id = ""
            skills = []
            if isinstance(log, dict):
                section_id = log.get("section_id", "")
                skills = log.get("skills_used", [])
            
            if section_id in synthesis_ids and "search_skill" in skills:
                logger.warning(
                    f"External search audit violation: synthesis section "
                    f"{section_id} used search_skill"
                )
                return True
        
        return False
    
    # ── 维度 6: Framework compliance ───────────────────

    def _check_framework_compliance(
        self,
        sections: List[Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Check if each section's content is relevant to its assigned role.
        Returns a bonus score (0 to +10) rather than a penalty.
        """
        context = context or {}
        section_roles = context.get("section_roles", {})
        if not section_roles or not sections:
            return 0.0

        matched_count = 0
        total_count = 0
        for s in sections:
            sid = ""
            text = ""
            if isinstance(s, dict):
                sid = s.get("id", "")
                text = s.get("content", "")
            if not sid or sid not in section_roles or not text:
                continue

            total_count += 1
            role_desc = section_roles[sid].lower()
            text_lower = text.lower()
            # Split on whitespace and Chinese punctuation
            key_terms = [t for t in re.split(r'[\s，。、：；（）！？]+', role_desc) if len(t) > 0]
            matched_terms = sum(1 for t in key_terms if t in text_lower)
            if key_terms and matched_terms >= max(1, len(key_terms) * 0.3):
                matched_count += 1

        if total_count == 0:
            return 0.0
        ratio = matched_count / total_count
        # Bonus: +0 to +10 based on compliance ratio
        return round(ratio * 10.0, 1)

    # ── Suggestions & Details ──────────────────────────
    
    def generate_suggestions(
        self,
        score: float,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Generate improvement suggestions"""
        suggestions = []
        sections = data.get("sections", data.get("content", ""))
        
        if not sections:
            suggestions.append("Report content is empty, need to regenerate")
            return suggestions
        
        if isinstance(sections, list) and len(sections) < 5:
            suggestions.append("Report sections are too few, consider adding more analysis dimensions")
        
        ctx = context or {}
        search_violation = self._check_external_search_audit(data, ctx)
        if search_violation:
            suggestions.append("CRITICAL: Synthesis sections must not use external search. "
                               "Remove search_skill from synthesis agents.")
        
        sections_list = sections if isinstance(sections, list) else []
        consistency_score = self._check_cross_chapter_consistency(sections_list)
        if consistency_score < 70:
            suggestions.append("Contradictory conclusions detected across chapters. "
                               "Ensure findings are aligned before generating synthesis.")

        redundancy_score = self._check_data_redundancy(sections_list)
        if redundancy_score < 70:
            suggestions.append("Data redundancy detected: same data points appear in "
                               "multiple research chapters. Consolidate and reference instead.")

        provenance_score = self._check_finding_provenance(data, ctx)
        if provenance_score < 60:
            suggestions.append("Weak finding provenance: synthesis sections do not "
                               "adequately reference research findings.")

        framework_bonus = self._check_framework_compliance(sections_list, ctx)
        if framework_bonus < 5:
            suggestions.append("Some section content does not align with its assigned "
                               "research role. Review section_roles configuration.")
        
        return suggestions
    
    def _get_details(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get detailed info including enhanced dimension scores"""
        sections = data.get("sections", data.get("content", ""))
        sections_list = sections if isinstance(sections, list) else []
        context = context or {}
        
        return {
            "section_count": len(sections_list),
            "has_content": bool(sections),
            "completeness": round(self._check_completeness(sections), 1),
            "cross_chapter_consistency": round(
                self._check_cross_chapter_consistency(sections_list), 1),
            "data_redundancy": round(self._check_data_redundancy(sections_list), 1),
            "finding_provenance": round(
                self._check_finding_provenance(data, context), 1),
            "framework_compliance": round(
                self._check_framework_compliance(sections_list, context), 1),
            "search_audit_violation": self._check_external_search_audit(data, context),
        }


class NumericConsistencyGate(BaseQualityChecker):
    def __init__(self, threshold: float = 80.0):
        super().__init__(threshold)
    
    def get_checker_type(self) -> str:
        return "numeric_gate"
    
    def calculate_score(self, data: Dict, context: Optional[Dict] = None) -> float:
        sections = data.get("sections", data.get("content", ""))
        if isinstance(sections, str):
            sections = [{"id": "content", "content": sections}]
        
        from collections import defaultdict
        
        metric_values = defaultdict(list)
        METRIC_PATTERNS = [
            (r'(?:净利润|归母净利润|扣非净利润)[^\d]*?(\d+\.?\d*)\s*亿元', "净利润"),
            (r'(?:营业)?收入[^\d]*?(\d+\.?\d*)\s*亿元', "营收"),
            (r'(?:总)?销量[^\d]*?(\d+\.?\d*)\s*万辆', "销量"),
        ]
        
        for s in sections:
            text = s.get("content", "") if isinstance(s, dict) else (s if isinstance(s, str) else "")
            sid = s.get("id", "") if isinstance(s, dict) else ""
            if not text:
                continue
            for pat, mname in METRIC_PATTERNS:
                for m in re.finditer(pat, text):
                    try:
                        v = float(m.group(1))
                        window = text[max(0, m.start()-40):m.start()+40]
                        years = re.findall(r'(20\d{2})', window)
                        year = years[-1] if years else "unknown"
                        caliber_parts = []
                        if '归母' in window or '归母' in mname:
                            caliber_parts.append('归母')
                        if '扣非' in window or '扣非' in mname:
                            caliber_parts.append('扣非')
                        caliber = '_'.join(caliber_parts) if caliber_parts else 'default'
                        metric_values[f"{mname}_{year}_{caliber}"].append((v, sid))
                    except ValueError:
                        continue
        
        contradictions = 0
        for key, entries in metric_values.items():
            if "_unknown_" in key:
                continue
            if len(entries) >= 2:
                vals = [e[0] for e in entries]
                mv, nv = max(vals), min(vals)
                if nv > 0 and (mv - nv) / nv > 0.05:
                    contradictions += 1
        
        if contradictions == 0:
            return 100.0
        return max(0.0, 100.0 - contradictions * 25.0)
    
    def generate_suggestions(self, score: float, data: Dict, context: Optional[Dict] = None) -> List[str]:
        if score >= self.threshold:
            return []
        return ["Data inconsistency detected: same metric has different values across chapters. Run calibration to resolve."]


class CompositeChecker:
    """Composite checker — weighted scoring across multiple checkers (G3-FIX-1).
    
    All sub-checkers use synchronous check() per BaseQualityChecker protocol.
    """
    
    def __init__(self, checkers: List[BaseQualityChecker], weights: List[float]):
        if not checkers or not weights:
            raise ValueError("checkers and weights must be non-empty")
        if len(checkers) != len(weights):
            raise ValueError("checkers and weights must match")
        t = sum(weights)
        self.checkers = checkers
        self.weights = [w / t for w in weights]
    
    def check(self, data: Dict, context: Optional[Dict] = None) -> QualityResult:
        total = 0.0
        all_issues = []
        for c, w in zip(self.checkers, self.weights):
            r = c.check(data, context)
            total += r.score * w
            all_issues.extend(r.issues)
        return QualityResult(
            checker_type="composite",
            score=total,
            threshold=self.checkers[0].threshold,
            passed=total >= self.checkers[0].threshold,
            issues=all_issues,
        )


__all__ = [
    "QualityResult",
    "BaseQualityChecker",
    "DataCollectionQualityChecker",
    "AnalysisQualityChecker",
    "ReportQualityChecker",
    "NumericConsistencyGate",
    "CompositeChecker",
]
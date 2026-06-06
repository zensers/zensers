# -*- coding: utf-8 -*-
"""
SemanticQualityAdapter — 三层评分 → BaseQualityChecker 接口适配器

将 SemanticQualityScorer 的三层评分结果适配为 QualityResult，
使 engine.py 的 check(data, context) -> QualityResult 调用链无需修改。

设计约束:
- 必须实现 check(data, context) -> QualityResult 同步接口
- section_type 从 agent_id / content 推断（不依赖调用方传入）
- 无 LLM 时自动降级（Layer2 用正则, Layer3 用 fallback 35.0）

设计参考: engine.py:1388, :1216, :2591 的 checker.check() 调用
"""

__all__ = ["SemanticQualityAdapter"]

import logging
import re
from typing import Any, Dict, List, Optional

from .checkers import BaseQualityChecker, QualityResult
from .semantic_scorer import SemanticQualityScorer, SectionScore, _SECTION_TYPE_TO_ASPECTS

logger = logging.getLogger(__name__)

# section_type patterns: keys auto-derived from _SECTION_TYPE_TO_ASPECTS (single source of truth).
# Chinese patterns maintained separately for practical matching.
_CN_PATTERNS: Dict[str, List[str]] = {
    "market_size": ["市场规模", "市场规模分析"],
    "competition": ["竞争格局", "竞争分析"],
    "technology": ["技术分析", "技术路线"],
    "risk": ["风险评估", "风险分析"],
    "financial_analysis": ["财务分析"],
    "policy": ["政策分析", "政策环境"],
    "enterprise": ["企业分析", "企业深度"],
    "industry_chain": ["产业链", "产业链分析"],
    "trend": ["趋势分析", "发展趋势"],
}
_SECTION_TYPE_PATTERNS: List[Dict[str, Any]] = []
for _st in _SECTION_TYPE_TO_ASPECTS:
    _patterns = [_st] + _CN_PATTERNS.get(_st, [])
    # Add snake_case first token for partial match (e.g. "financial"→"financial_analysis")
    _first_token = _st.split("_")[0]
    if _first_token != _st and _first_token not in _patterns:
        _patterns.append(_first_token)
    _SECTION_TYPE_PATTERNS.append({"type": _st, "patterns": _patterns})


def _infer_section_type(data: Dict[str, Any], context: Optional[Dict] = None) -> str:
    """从 data/context 推断 section_type"""
    for source_key in ("agent_id", "id", "title"):
        val = (data.get(source_key) or "") if isinstance(data, dict) else ""
        if not val and context:
            val = context.get(source_key, "")
        if val:
            val_lower = val.lower()
            for entry in _SECTION_TYPE_PATTERNS:
                if any(p in val_lower for p in entry["patterns"]):
                    return entry["type"]

    content = data.get("content", "") if isinstance(data, dict) else ""
    if content:
        content_lower = content[:2000].lower()
        for entry in _SECTION_TYPE_PATTERNS:
            if any(p in content_lower for p in entry["patterns"]):
                return entry["type"]

    return "generic"


class SemanticQualityAdapter(BaseQualityChecker):
    """
    三层语义评分适配器

    实现 BaseQualityChecker.check(data, context) -> QualityResult 接口，
    内部使用 SemanticQualityScorer 进行三层评分。

    用法（与 CompositeChecker / AnalysisQualityChecker 接口一致）:
        adapter = SemanticQualityAdapter(threshold=75.0)
        result = adapter.check(data, context)
        if result.passed: ...
    """

    def __init__(
        self,
        threshold: float = 75.0,
        llm_client: Optional[Any] = None,
        fallback_checker: Optional[BaseQualityChecker] = None,
    ):
        super().__init__(threshold)
        self._scorer = SemanticQualityScorer(llm_client=llm_client)
        self._fallback_checker = fallback_checker

    def get_checker_type(self) -> str:
        return "semantic_three_layer"

    def calculate_score(self, data: Dict, context: Optional[Dict] = None) -> float:
        result = self.check(data, context)
        return result.score

    def check(self, data: Dict, context: Optional[Dict] = None) -> QualityResult:
        """
        三层评分并转换为 QualityResult。

        降级策略:
        - SemanticQualityScorer 异常 → fallback_checker（旧 AnalysisQualityChecker）
        - fallback 也异常 → 返回保守通过
        """
        content = data.get("content", "") if isinstance(data, dict) else ""
        if not content:
            if self._fallback_checker:
                return self._fallback_checker.check(data, context)
            return QualityResult(
                checker_type=self.get_checker_type(),
                score=0.0,
                threshold=self.threshold,
                passed=False,
                issues=["内容为空"],
            )

        try:
            section_type = _infer_section_type(data, context)
            section_score = self._scorer.score(content, section_type)
            return self._to_quality_result(section_score)
        except Exception as e:
            logger.warning(f"SemanticQualityAdapter failed, falling back: {e}")
            if self._fallback_checker:
                try:
                    return self._fallback_checker.check(data, context)
                except Exception as e2:
                    logger.warning(f"Fallback checker also failed: {e2}")
            return QualityResult(
                checker_type=self.get_checker_type(),
                score=40.0,
                threshold=self.threshold,
                passed=False,
                issues=[f"三层评分异常: {str(e)[:80]}"],
            )

    def generate_suggestions(self, score: float, data: Dict, context: Optional[Dict] = None) -> List[str]:
        if score >= self.threshold:
            return []
        suggestions = []
        if score < 50:
            suggestions.append("分析质量严重不足，建议补充数据源并重构分析框架")
        elif score < self.threshold:
            suggestions.append("建议加强方法论应用深度，补充交叉验证和不确定性分析")
        return suggestions

    def _to_quality_result(self, section_score: SectionScore) -> QualityResult:
        """将 SectionScore 转换为 QualityResult"""
        issues = []
        l3_detail = section_score.layers_detail.get("layer3", {})
        issues.extend(l3_detail.get("issues", []))

        if section_score.layer1_score < 30:
            issues.append("结构不完整：缺少必要的分析要素")

        l2_detail = section_score.layers_detail.get("layer2", {})
        coverage_rate = l2_detail.get("coverage_rate", 0)
        if coverage_rate < 0.5:
            issues.append(f"框架组件覆盖率仅{coverage_rate:.0%}，建议补充分析维度")

        return QualityResult(
            checker_type=self.get_checker_type(),
            score=section_score.total,
            threshold=self.threshold,
            passed=section_score.total >= self.threshold,
            issues=issues[:10],
            suggestions=self.generate_suggestions(section_score.total, {}),
            details={
                "layer1_score": section_score.layer1_score,
                "layer2_score": section_score.layer2_score,
                "layer3_score": section_score.layer3_score,
                "layer2_framework": l2_detail.get("framework", ""),
                "layer2_coverage_rate": coverage_rate,
                "layer3_rubric_id": l3_detail.get("rubric_id", ""),
                "layer3_dimension_scores": l3_detail.get("dimension_scores", {}),
                "skipped_layers": section_score.skipped_layers,
            },
        )

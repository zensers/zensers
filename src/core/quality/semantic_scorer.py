# -*- coding: utf-8 -*-
"""
SemanticQualityScorer — 三层语义评分融合

Layer 1 (25%): 结构规范 — SECTION_ELEMENT_REQUIREMENTS 正则匹配
Layer 2 (40%): 方法论应用 — 框架组件覆盖率 + LLM 框架匹配度
Layer 3 (35%): 分析深度 — LLM-as-Judge with MKB rubric 动态评分

设计参考: 08_未来优化方向设计.md §4.3 Track B 三层融合
"""

__all__ = ["SemanticQualityScorer", "SectionScore"]

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .layer2_methodology import Layer2MethodologyScorer
from .layer3_depth import Layer3DepthScorer

logger = logging.getLogger(__name__)

LAYER1_WEIGHT = 0.25
LAYER2_WEIGHT = 0.40
LAYER3_WEIGHT = 0.35
LAYER1_SKIP_THRESHOLD = 30.0

# Single source of truth for section_type → aspects mapping.
# SemanticQualityAdapter._infer_section_type derives patterns from these keys.
_SECTION_TYPE_TO_ASPECTS = {
    "market_size": ["market_size", "market_analysis"],
    "competition": ["competitive_landscape", "market_structure", "industry_analysis"],
    "technology": ["technology", "technology_analysis"],
    "risk": ["risk", "risk_assessment"],
    "financial_analysis": ["financial_analysis", "valuation"],
    "policy": ["policy", "regulatory"],
    "enterprise": ["enterprise", "company_analysis"],
    "industry_chain": ["industry_chain", "supply_chain", "value_chain"],
    "trend": ["trend", "forecasting", "future_analysis"],
}


@dataclass
class SectionScore:
    total: float
    layer1_score: float
    layer2_score: float
    layer3_score: float
    layers_detail: Dict[str, Any] = field(default_factory=dict)
    skipped_layers: List[str] = field(default_factory=list)


class SemanticQualityScorer:
    """
    三层语义评分器

    用法:
        scorer = SemanticQualityScorer()
        result = scorer.score(content, section_type)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        section_elements: Optional[Dict[str, List[Dict]]] = None,
    ):
        self._llm_client = llm_client
        self._section_elements = section_elements
        self._layer2 = Layer2MethodologyScorer(llm_client=llm_client)
        self._layer3 = Layer3DepthScorer(llm_client=llm_client)

    def score(
        self,
        content: str,
        section_type: str,
        issues: Optional[List[Dict]] = None,
    ) -> SectionScore:
        """
        三层评分

        Args:
            content: 章节内容
            section_type: 章节类型
            issues: 质检问题列表 (Layer 1 用)

        Returns:
            SectionScore
        """
        skipped: List[str] = []
        details: Dict[str, Any] = {}

        # Layer 1: 结构规范
        l1 = self._layer1_score(content, section_type, issues or [])
        details["layer1"] = {"score": l1, "weight": LAYER1_WEIGHT}

        if l1 < LAYER1_SKIP_THRESHOLD:
            return SectionScore(
                total=l1,
                layer1_score=l1,
                layer2_score=0.0,
                layer3_score=0.0,
                layers_detail=details,
                skipped_layers=["layer2", "layer3"],
            )

        # Layer 2: 方法论应用
        frameworks = self._load_frameworks_for(section_type)
        if frameworks:
            l2_result = self._layer2.score(content, section_type, frameworks)
            l2 = l2_result.score
            details["layer2"] = {
                "score": l2,
                "weight": LAYER2_WEIGHT,
                "framework": l2_result.framework_name,
                "component_coverage": l2_result.component_coverage,
                "coverage_rate": l2_result.component_coverage_rate,
                "evidence_quality": l2_result.evidence_quality,
            }
        else:
            l2 = 0.0
            skipped.append("layer2")
            details["layer2"] = {"score": 0.0, "weight": LAYER2_WEIGHT, "reason": "no matching frameworks"}

        # Layer 3: 分析深度
        l3_result = self._layer3.score(content, section_type)
        l3 = l3_result.score
        details["layer3"] = {
            "score": l3,
            "weight": LAYER3_WEIGHT,
            "dimension_scores": l3_result.dimension_scores,
            "issues": l3_result.issues,
            "rubric_id": l3_result.rubric_id,
        }

        total = round(l1 * LAYER1_WEIGHT + l2 * LAYER2_WEIGHT + l3 * LAYER3_WEIGHT, 1)

        return SectionScore(
            total=total,
            layer1_score=l1,
            layer2_score=l2,
            layer3_score=l3,
            layers_detail=details,
            skipped_layers=skipped,
        )

    def _layer1_score(
        self,
        content: str,
        section_type: str,
        issues: List[Dict],
    ) -> float:
        """Layer 1: 结构规范评分（从 quality_check_agent 的逻辑提取）"""
        if not content or len(content.strip()) < 50:
            return max(0, 30 - sum(1 for i in issues if i.get("severity") == "high") * 10)

        elements = self._get_elements(section_type)
        if not elements:
            return 50.0

        element_score = 0.0
        for elem in elements:
            patterns = elem.get("patterns", [])
            matched = any(re.search(p, content) for p in patterns)
            if matched:
                element_score += elem.get("weight", 0.1)

        base_score = element_score * 100.0

        numbers = re.findall(r'\d+\.?\d*', content)
        data_bonus = min(len(numbers) * 2, 10)

        severity_weights = {"high": 15, "medium": 5, "low": 1}
        penalty = sum(
            severity_weights.get(i.get("severity", "low"), 1) for i in issues
        )
        penalty = min(penalty, 40)

        return max(0, min(100, base_score + data_bonus - penalty))

    def _get_elements(self, section_type: str) -> List[Dict]:
        """获取 section_type 对应的 elements"""
        if self._section_elements:
            return self._section_elements.get(section_type, [])

        try:
            from src.agents.fixed_agents.quality_check_agent import SECTION_ELEMENT_REQUIREMENTS, GENERIC_ELEMENTS
            return SECTION_ELEMENT_REQUIREMENTS.get(section_type, GENERIC_ELEMENTS)
        except ImportError:
            return []

    def _load_frameworks_for(self, section_type: str) -> List[Dict]:
        """从 MKB 加载匹配的框架"""
        try:
            from src.methodologies.registry import match_for_aspect
            aspects = _SECTION_TYPE_TO_ASPECTS.get(section_type, [section_type])
            frameworks = []
            seen_ids = set()
            for aspect in aspects:
                for fw in match_for_aspect(aspect):
                    fw_id = fw.get("id", "")
                    if fw_id and fw_id not in seen_ids:
                        seen_ids.add(fw_id)
                        frameworks.append(fw)
            return frameworks
        except Exception as e:
            logger.warning(f"Failed to load frameworks for {section_type}: {e}")
            return []

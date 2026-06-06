# -*- coding: utf-8 -*-
"""
Layer 2: 方法论应用评估

混合评分策略：
- 正则组件覆盖率：检查框架 components 的 keywords 是否出现在内容中（无 LLM 调用）
- LLM 框架匹配度：判断内容实际使用的分析方法与预期框架的匹配程度

设计参考: 08_未来优化方向设计.md §4.1 Track B Layer 2
"""

__all__ = ["Layer2MethodologyScorer", "Layer2Result"]

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FRAMEWORK_MATCH_PROMPT = """\
你是一个方法论分析专家。判断以下报告内容使用了哪种分析方法。

预期分析框架: {framework_name}
框架描述: {framework_desc}

报告内容（摘要）:
---
{content}
---

请判断内容与预期框架的匹配程度，返回JSON:
{{"match_score": <0-100>, "reasoning": "<一句话说明>", "evidence_found": ["<内容中体现该框架的具体片段关键词>"]}}

仅返回JSON，无其他文字。"""

_MAX_CONTENT_CHARS = 6000


@dataclass
class Layer2Result:
    score: float
    component_coverage: Dict[str, bool]
    component_coverage_rate: float
    framework_match_score: float
    framework_name: str
    evidence_quality: float
    details: Dict[str, Any] = field(default_factory=dict)


class Layer2MethodologyScorer:
    """
    Layer 2 方法论应用评估

    混合评分：
    1. 正则组件覆盖率（60%权重）— 检查框架components的keywords是否在内容中出现
    2. LLM框架匹配度（40%权重）— LLM判断内容实际分析方法与框架的匹配程度

    用法：
        scorer = Layer2MethodologyScorer()
        result = scorer.score(content, section_type, frameworks)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        coverage_weight: float = 0.6,
        match_weight: float = 0.4,
    ):
        self._llm_client = llm_client
        self._coverage_weight = coverage_weight
        self._match_weight = match_weight

    def score(
        self,
        content: str,
        section_type: str,
        frameworks: List[Dict[str, Any]],
        max_frameworks: int = 2,
    ) -> Layer2Result:
        """
        同步评分接口。

        Args:
            content: 章节内容
            section_type: 章节类型 (market_size, competition, etc.)
            frameworks: 匹配到的框架列表 (来自 MKB registry)
            max_frameworks: 最多评估的框架数量

        Returns:
            Layer2Result
        """
        if not content or not frameworks:
            return Layer2Result(
                score=0.0,
                component_coverage={},
                component_coverage_rate=0.0,
                framework_match_score=0.0,
                framework_name="",
                evidence_quality=0.0,
            )

        evaluated = frameworks[:max_frameworks]
        results: List[Dict[str, Any]] = []

        for fw in evaluated:
            coverage = self._check_component_coverage(content, fw)
            match_score = self._check_framework_match(content, fw)
            evidence = self._check_evidence(content, fw)

            results.append({
                "framework_id": fw.get("id", ""),
                "framework_name": fw.get("name", ""),
                "component_coverage": coverage,
                "coverage_rate": sum(coverage.values()) / max(len(coverage), 1),
                "match_score": match_score,
                "evidence_quality": evidence,
            })

        best = max(results, key=lambda r: r["coverage_rate"] * self._coverage_weight + r["match_score"] / 100 * self._match_weight)

        total = (
            best["coverage_rate"] * 100 * self._coverage_weight
            + best["match_score"] * self._match_weight
        )

        return Layer2Result(
            score=round(total, 1),
            component_coverage=best["component_coverage"],
            component_coverage_rate=round(best["coverage_rate"], 2),
            framework_match_score=best["match_score"],
            framework_name=best["framework_name"],
            evidence_quality=round(best["evidence_quality"], 1),
            details={"evaluated_frameworks": results},
        )

    def _check_component_coverage(
        self, content: str, framework: Dict[str, Any]
    ) -> Dict[str, bool]:
        """正则检查框架 components 的 keywords 是否出现在内容中"""
        components = framework.get("components", [])
        if not components:
            return {}

        coverage = {}
        for comp in components:
            comp_id = comp.get("id", "")
            keywords = comp.get("keywords", [])
            found = any(kw.lower() in content.lower() for kw in keywords if kw)
            coverage[comp_id] = found

        return coverage

    def _check_framework_match(self, content: str, framework: Dict[str, Any]) -> float:
        """LLM 框架匹配度评估"""
        if not self._llm_client:
            components = framework.get("components", [])
            if components:
                coverage = self._check_component_coverage(content, framework)
                rate = sum(coverage.values()) / max(len(coverage), 1)
                return round(rate * 100, 1)
            return 50.0

        try:
            prompt = _FRAMEWORK_MATCH_PROMPT.format(
                framework_name=framework.get("name", ""),
                framework_desc=framework.get("content", "")[:500],
                content=content[:_MAX_CONTENT_CHARS],
            )

            result = self._call_llm(prompt)
            parsed = self._parse_match_response(result)
            return float(parsed.get("match_score", 50.0))

        except Exception as e:
            logger.warning(f"Layer 2 framework match LLM failed: {e}")
            return 50.0

    def _check_evidence(self, content: str, framework: Dict[str, Any]) -> float:
        """检查 evidence_required 中的数据源类型是否在内容中体现"""
        evidence_required = framework.get("evidence_required", [])
        if not evidence_required:
            return 50.0

        evidence_keywords = {
            "宏观统计数据": ["统计局", "GDP", "宏观数据", "官方统计"],
            "行业研究报告": ["报告", "研究", "调研", "白皮书", "行业分析"],
            "企业财报或官方数据": ["财报", "年报", "季报", "营收", "净利润", "官方"],
            "至少2个独立数据源": ["来源", "数据源", "独立", "交叉"],
            "技术性能参数数据": ["参数", "性能", "指标", "规格"],
            "历史技术演进数据": ["历史", "演进", "趋势", "变化"],
            "市场渗透率数据": ["渗透率", "普及率", "采纳"],
            "竞品技术对比数据": ["对比", "比较", "vs", "竞品"],
            "行业竞争格局数据": ["格局", "排名", "市占率"],
            "企业市场份额数据": ["份额", "市占率", "占比"],
            "进入壁垒案例": ["壁垒", "门槛", "护城河"],
            "供应链结构信息": ["供应链", "上游", "下游"],
        }

        found = 0
        for ev in evidence_required:
            kws = evidence_keywords.get(ev, [ev[:4]] if len(ev) >= 4 else [ev])
            if any(kw in content for kw in kws):
                found += 1

        return round(found / max(len(evidence_required), 1) * 100, 1)

    def _call_llm(self, prompt: str) -> str:
        """同步 LLM 调用"""
        import asyncio

        async def _do():
            if hasattr(self._llm_client, "execute"):
                resp = await self._llm_client.execute(prompt=prompt)
                if isinstance(resp, dict):
                    data = resp.get("data", resp)
                    if isinstance(data, dict):
                        return data.get("content", "")
                    return str(data)
                return str(resp)
            elif callable(self._llm_client):
                return self._llm_client(prompt)
            return ""

        try:
            return asyncio.run(_do())
        except RuntimeError:
            return ""

    def _parse_match_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        if not response:
            return {}
        try:
            s = response.find("{")
            e = response.rfind("}") + 1
            if s >= 0 and e > s:
                parsed = json.loads(response[s:e])
                if isinstance(parsed, dict):
                    return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

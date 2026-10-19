"""Deterministic chapter coverage checks used before and after writing."""

import re
from typing import Any, Dict, Iterable, List

from .models import ChapterCoverage, ChapterRequirement, ReportEvidenceContext

# P1-C（复审修订，ses_baf7a884）：指标名归一化与受控别名词对。
# 归一化先做确定性步骤（去括注/空白/标点/全半角），再按受限词对做
# 双向包含判定。词对只收"后缀/嵌词变体"，不收宽泛同义词，避免把
# 真空缺洗白成命中（复审抽查：细分领域占比/产业基金两类真空缺必须
# 继续报缺失）。
_METRIC_NORMALIZE_STRIP = re.compile(r"[（(][^）)]*[）)]|[\s，,。.:：;；、\-—_/]+")
_METRIC_ALIAS_PAIRS = (
    ("核心产业规模", "市场规模"),
    ("复合年增长率", "复合增长率"),
    ("复合增长率", "年均增速"),
    ("复合增长率", "年均增长率"),
    ("投融资规模", "融资规模"),
    ("政策文件", "政策信号"),
)


def _normalize_metric_name(name: str) -> str:
    return _METRIC_NORMALIZE_STRIP.sub("", str(name or "").lower())


def _metric_equivalent(a: str, b: str) -> bool:
    na, nb = _normalize_metric_name(a), _normalize_metric_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return any(
        (pair[0] in na and pair[1] in nb) or (pair[1] in na and pair[0] in nb)
        for pair in _METRIC_ALIAS_PAIRS
    )


class ChapterCoverageChecker:
    def check(
        self,
        requirement: ChapterRequirement,
        chapter_data: Dict[str, Any],
        context: ReportEvidenceContext,
    ) -> ChapterCoverage:
        structured_text = self._text(chapter_data)
        raw_items = context.raw_search_results or []
        raw_text = "\n".join(self._text(item) for item in raw_items)

        available_structured = [
            metric for metric in requirement.required_metrics
            if _metric_equivalent(metric, structured_text)
            or any(_metric_equivalent(metric, str(dp.get("metric", "")))
                   for dp in chapter_data.get("upstream_data_points", [])
                   if isinstance(dp, dict))
        ]
        available_raw = [
            metric for metric in requirement.required_metrics
            if _metric_equivalent(metric, raw_text)
            and any(
                self._usable_evidence(item)
                and _metric_equivalent(metric, self._text(item))
                for item in raw_items
            )
            and metric not in available_structured
        ]
        missing_metrics = [
            metric for metric in requirement.required_metrics
            if metric not in available_structured and metric not in available_raw
        ]
        missing_topics = [
            topic for topic in requirement.required_topics
            if topic.lower() not in structured_text.lower()
            and not any(
                self._usable_evidence(item)
                and topic.lower() in self._text(item).lower()
                for item in raw_items
            )
        ]
        return ChapterCoverage(
            ready_to_write=not missing_metrics and not missing_topics,
            missing_topics=missing_topics,
            missing_metrics=missing_metrics,
            available_in_structured=available_structured,
            available_in_raw_search=available_raw,
            external_search_required=bool(missing_metrics or missing_topics),
        )

    @staticmethod
    def _usable_evidence(item: Dict[str, Any]) -> bool:
        return bool(
            str(item.get("url") or item.get("href") or "").strip()
            and (
                str(item.get("evidence_id") or "").strip()
                or str(item.get("evidence_excerpt") or item.get("excerpt") or "").strip()
                or str(item.get("snippet") or "").strip()
            )
        )

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(ChapterCoverageChecker._text(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return " ".join(ChapterCoverageChecker._text(v) for v in value)
        return str(value or "")

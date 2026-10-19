import re
import logging
from typing import Dict, List, Optional, Any

from .models import DataConflict, MetricEntry

logger = logging.getLogger(__name__)


class DataRegistry:

    def __init__(self) -> None:
        self._metrics: Dict[str, MetricEntry] = {}

    def register(self, metric: str, value: str, unit: str,
                 chapter_id: str, source: str, **evidence: Any) -> None:
        key = self._normalize_metric(metric)
        if key in self._metrics:
            existing = self._metrics[key]
            # Compare semantic numeric values rather than presentation text.
            # For example, "下滑3" and "-3" describe the same change; they
            # must not create an L5 conflict merely because the wording
            # differs.  The original strings are retained for traceability.
            if self._normalize_value(existing.value) != self._normalize_value(value):
                # P0-A（复审修订，ses_baf7a884）：双侧均无数值的定性表述
                # 差异（同一事实的复述变体）只记 variants 供展示，不进
                # conflicts——L5 blocking 的本体职责是数值冲突。
                if self._is_quantitative(existing.value) or self._is_quantitative(value):
                    existing.conflicts.append({
                        "chapter_id": chapter_id,
                        "value": value,
                        "unit": unit,
                        "source": source,
                        **{k: v for k, v in evidence.items() if v not in (None, "")},
                    })
                else:
                    existing.variants.append({
                        "chapter_id": chapter_id,
                        "value": value,
                        "unit": unit,
                        "source": source,
                    })
        else:
            self._metrics[key] = MetricEntry(
                metric=metric, value=value, unit=unit,
                canonical_chapter=chapter_id, source=source,
                conflicts=[],
            )

        # Keep the canonical evidence contract available to report repair and
        # checkpoint consumers without breaking the legacy MetricEntry shape.
        entry = self._metrics[key]
        for key_name, value_item in evidence.items():
            if value_item not in (None, ""):
                setattr(entry, key_name, value_item)

    def get_canonical_value(self, metric: str) -> Optional[str]:
        key = self._normalize_metric(metric)
        entry = self._metrics.get(key)
        return entry.value if entry else None

    def set_canonical_value(self, metric: str, value: str, source: str) -> None:
        key = self._normalize_metric(metric)
        entry = self._metrics.get(key)
        if entry:
            entry.value = value
            entry.source = source
            entry.conflicts = []

    def get_conflicts(self) -> List[DataConflict]:
        conflicts = []
        for entry in self._metrics.values():
            if entry.conflicts:
                all_entries = [{
                    "chapter_id": entry.canonical_chapter,
                    "value": entry.value,
                    "unit": entry.unit,
                    "source": entry.source,
                }] + entry.conflicts
                conflicts.append(DataConflict(
                    metric=entry.metric, entries=all_entries,
                ))
        return conflicts

    def is_used(self, metric: str, value: str) -> bool:
        key = self._normalize_metric(metric)
        entry = self._metrics.get(key)
        if not entry:
            return False
        return self._normalize_value(entry.value) == self._normalize_value(value)

    def serialize_used_metrics(self) -> str:
        if not self._metrics:
            return "暂无已使用的数据指标。"
        lines = []
        for key, entry in self._metrics.items():
            conflict_mark = " ⚠️存在冲突" if entry.conflicts else ""
            variant_mark = "（存在定性表述变体）" if entry.variants else ""
            lines.append(
                f"- {entry.metric}: {entry.value} {entry.unit}（来源: {entry.source}）"
                f"{conflict_mark}{variant_mark}"
            )
        return "\n".join(lines)

    @staticmethod
    def _is_quantitative(value: Any) -> bool:
        """数值型判定：值中含数字即视为定量断言（P0-A 分流依据）。"""
        return bool(re.search(r"\d", str(value or "")))

    def serialize_conflicts(self) -> str:
        conflicts = self.get_conflicts()
        if not conflicts:
            return "无已知数据冲突。"
        lines = []
        for c in conflicts:
            values_str = ", ".join(
                f'{e["value"]}{e["unit"]}（来源:{e["source"]}）'
                for e in c.entries
            )
            lines.append(f"- {c.metric}: {values_str}")
        return "\n".join(lines)

    def to_snapshot(self) -> Dict[str, Any]:
        return {
            "metrics": {
                k: {
                    "metric": v.metric, "value": v.value, "unit": v.unit,
                    "canonical_chapter": v.canonical_chapter,
                    "source": v.source, "conflicts": v.conflicts,
                    "variants": getattr(v, "variants", []),
                    "evidence_id": getattr(v, "evidence_id", ""),
                    "provenance_id": getattr(v, "provenance_id", ""),
                    "source_url": getattr(v, "source_url", ""),
                    "period": getattr(v, "period", ""),
                    "geographic_scope": getattr(v, "geographic_scope", ""),
                    "population": getattr(v, "population", ""),
                }
                for k, v in self._metrics.items()
            }
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, Any]) -> "DataRegistry":
        registry = cls()
        for k, v in snapshot.get("metrics", {}).items():
            registry._metrics[k] = MetricEntry(
                metric=v["metric"], value=v["value"], unit=v["unit"],
                canonical_chapter=v["canonical_chapter"],
                source=v["source"], conflicts=v.get("conflicts", []),
                variants=v.get("variants", []),
            )
            for key_name in (
                "evidence_id", "provenance_id", "source_url", "period",
                "geographic_scope", "population",
            ):
                if key_name in v:
                    setattr(registry._metrics[k], key_name, v[key_name])
        return registry

    @staticmethod
    def _normalize_metric(metric: str) -> str:
        return re.sub(r'\s+', '', metric.lower().strip())

    @staticmethod
    def _normalize_value(value: Any) -> str:
        """Normalize common Chinese numeric qualifiers for conflict checks."""
        text = str(value or "").strip().replace(",", "")
        text = text.replace("下滑", "-").replace("下降", "-")
        text = re.sub(r"^(接近|约为|约|超过|达到)", "", text)
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return match.group(0) if match else text

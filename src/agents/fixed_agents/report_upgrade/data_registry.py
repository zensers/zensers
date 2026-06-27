import re
import logging
from typing import Dict, List, Optional, Any

from .models import DataConflict, MetricEntry

logger = logging.getLogger(__name__)


class DataRegistry:

    def __init__(self) -> None:
        self._metrics: Dict[str, MetricEntry] = {}

    def register(self, metric: str, value: str, unit: str,
                 chapter_id: str, source: str) -> None:
        key = self._normalize_metric(metric)
        if key in self._metrics:
            existing = self._metrics[key]
            if existing.value != value:
                existing.conflicts.append({
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
        return entry.value == value

    def serialize_used_metrics(self) -> str:
        if not self._metrics:
            return "暂无已使用的数据指标。"
        lines = []
        for key, entry in self._metrics.items():
            conflict_mark = " ⚠️存在冲突" if entry.conflicts else ""
            lines.append(
                f"- {entry.metric}: {entry.value} {entry.unit}（来源: {entry.source}）{conflict_mark}"
            )
        return "\n".join(lines)

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
            )
        return registry

    @staticmethod
    def _normalize_metric(metric: str) -> str:
        return re.sub(r'\s+', '', metric.lower().strip())

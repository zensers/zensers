"""Caliber Consistency Checker — detect conflicting data points."""

import re
from typing import Any, Dict, List


def _normalize_value(val: str) -> str:
    """标准化数值用于比较。"""
    v = str(val).strip().lower()
    v = re.sub(r"[,\s]", "", v)
    v = re.sub(r"(亿|万|百万|千|billion|million|thousand)", "", v)
    v = re.sub(r"[^\d.%+-]", "", v)
    return v


def _normalize_unit(unit: str) -> str:
    u = str(unit).strip().lower()
    mapping = {"台": "units", "万辆": "10k_units", "亿": "100m", "万": "10k", "%": "pct"}
    return mapping.get(u, u)


class CaliberConsistencyChecker:
    def check(self, data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检测同一 metric 下的冲突数据点。"""
        by_metric: Dict[str, List[Dict]] = {}
        for dp in data_points:
            metric = str(dp.get("metric") or "").strip()
            if not metric:
                continue
            by_metric.setdefault(metric, []).append(dp)

        conflicts = []
        for metric, items in by_metric.items():
            if len(items) < 2:
                continue
            values = set()
            units = set()
            periods = set()
            for item in items:
                values.add(_normalize_value(str(item.get("value") or "")))
                units.add(_normalize_unit(str(item.get("unit") or "")))
                periods.add(str(item.get("period") or ""))
            has_value_conflict = len([v for v in values if v]) > 1
            has_unit_conflict = len([u for u in units if u]) > 1
            if has_value_conflict or has_unit_conflict:
                conflicts.append({
                    "metric": metric,
                    "reason": "value_conflict" if has_value_conflict else "unit_conflict",
                    "values": list(values),
                    "units": list(units),
                    "periods": list(periods),
                    "data_points": items,
                })
        return conflicts

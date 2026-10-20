from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .config import DeepModeConfig
from .models import DeepModePlan

_SECTION_MATCHERS = {
    "company_share": (
        "competitive",
        "competition",
        "竞争",
        "市场份额",
        "market share",
        "cr4",
        "cr8",
    ),
    "bom_item": ("technology", "技术", "bom", "成本结构", "cost structure"),
    "supplier": ("value_chain", "value chain", "产业链", "供应链", "supplier", "供应商"),
}

_DEFAULT_BOM = {
    "新能源": ["动力电池", "电驱", "电控", "热管理", "智能座舱", "自动驾驶"],
    "汽车": ["动力电池", "电驱", "电控", "热管理", "智能座舱", "自动驾驶"],
    "半导体": ["真空系统", "光学系统", "运动控制", "射频电源", "腔体", "精密零部件"],
    "机器人": ["关节模组", "减速器", "电机", "丝杠", "传感器", "控制器"],
}


def _section_id(section: Any) -> str:
    if isinstance(section, Mapping):
        return str(section.get("id") or section.get("section_id") or "")
    return str(getattr(section, "section_id", "") or getattr(section, "id", ""))


def _section_name(section: Any) -> str:
    if isinstance(section, Mapping):
        parts = [
            section.get("id") or section.get("section_id") or "",
            section.get("name") or "",
        ]
    else:
        parts = [
            getattr(section, "section_id", "") or getattr(section, "id", "") or "",
            getattr(section, "name", "") or "",
        ]
    return " ".join(str(part) for part in parts).lower()


def _flatten_need(item: Any) -> list[str]:
    if isinstance(item, Mapping):
        joined = " ".join(str(value).strip() for value in item.values() if str(value).strip())
        return [joined] if joined else []
    text = str(item).strip()
    return [text] if text else []


def _mapping_needs(section: Any) -> list[str]:
    if not isinstance(section, Mapping):
        raw = getattr(section, "all_data_needs", []) or []
        return [str(item).strip() for item in raw if str(item).strip()]
    needs: list[str] = []
    for key in ("points", "data_needs"):
        for item in section.get(key) or []:
            needs.extend(_flatten_need(item))
    for sub in section.get("sub_sections") or []:
        if isinstance(sub, Mapping):
            raw = sub.get("data_needs") or []
        else:
            raw = getattr(sub, "data_needs", []) or []
        for item in raw:
            needs.extend(_flatten_need(item))
    return needs


def _section_needs(section: Any) -> list[str]:
    return _dedupe(_mapping_needs(section))


def _dedupe(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _classify_section(section: Any) -> tuple[str, int]:
    name = _section_name(section)
    needs = " ".join(_mapping_needs(section)).lower()
    scores: dict[str, int] = {}
    for record_type, keywords in _SECTION_MATCHERS.items():
        score = 0
        for keyword in keywords:
            if keyword in name:
                score += 100
            if keyword in needs:
                score += 10
        scores[record_type] = score
    top_score = max(scores.values(), default=0)
    if top_score <= 0:
        return "", 0
    winners = [
        record_type for record_type, score in scores.items() if score == top_score
    ]
    if len(winners) != 1:
        return "", 0
    return winners[0], top_score


def _infer_bom_systems(topic: str, config: DeepModeConfig) -> list[str]:
    for keyword, systems in _DEFAULT_BOM.items():
        if keyword in topic:
            return systems[: config.max_bom_systems]
    return ["核心部件", "关键材料", "主要模组"][: config.max_bom_systems]


class DeepModePlanner:
    def __init__(self, config: DeepModeConfig | None = None) -> None:
        self.config = config or DeepModeConfig()

    def build_plan(
        self,
        topic: str,
        section_specs: list[Any],
        output_type: str = "industry_report",
        companies: list[str] | None = None,
    ) -> DeepModePlan | None:
        if output_type != "industry_report":
            return None

        best: dict[str, tuple[int, str, list[str]]] = {}
        for section in section_specs or []:
            section_id = _section_id(section)
            if not section_id:
                continue
            record_type, score = _classify_section(section)
            if not record_type or score <= 0:
                continue
            current = best.get(record_type)
            if current is None or score > current[0]:
                best[record_type] = (score, section_id, _section_needs(section))

        sections = {record_type: item[1] for record_type, item in best.items()}
        section_needs = {
            record_type: item[2] for record_type, item in best.items()
        }

        if not sections:
            return None

        return DeepModePlan(
            topic=topic,
            sections=sections,
            section_needs=section_needs,
            companies=_dedupe(companies or [])[: self.config.max_companies],
            bom_systems=_infer_bom_systems(topic, self.config),
        )

from __future__ import annotations

from datetime import datetime, timezone

from .config import DeepModeConfig
from .models import DeepModePlan, DeepQuery

_FALLBACK_QUERIES = {
    "company_share": (
        "{topic} 市场份额 数据 {year}",
        "{topic} 企业销量 排名 {year}",
        "{topic} 行业集中度 分析 {year}",
        "{topic} 头部企业 市占率 {year}",
        "{topic} 品牌份额 排名 {year}",
        "{topic} 市场格局 份额 变化 {year}",
    ),
    "bom_item": (
        "{topic} 成本结构 分析 {year}",
        "{topic} 核心部件 成本占比",
        "{topic} 供应链 成本 拆解",
        "{topic} BOM 成本 结构 明细",
        "{topic} 整车 成本 构成",
        "{topic} 关键零部件 成本",
    ),
    "supplier": (
        "{topic} 供应链 上游 企业 {year}",
        "{topic} 核心零部件 厂商",
        "{topic} 供应商 配套 关系",
        "{topic} 上游材料 供应商 {year}",
        "{topic} 关键部件 供应商 名单",
        "{topic} 产业链 供应商 格局",
    ),
}


class DeepQueryBuilder:
    def build(
        self,
        topic: str,
        plan: DeepModePlan,
        config: DeepModeConfig,
        year: int | None = None,
    ) -> list[DeepQuery]:
        current_year = year or datetime.now(timezone.utc).year
        buckets: dict[str, list[DeepQuery]] = {
            "company_share": [],
            "bom_item": [],
            "supplier": [],
        }

        company_section = plan.sections.get("company_share", "")
        if company_section:
            self._add(
                buckets["company_share"],
                f"{topic} 主要企业 市场份额 排名 {current_year}",
                "company_share",
                company_section,
            )
            self._add(
                buckets["company_share"],
                f"{topic} CR4 CR8 市场集中度 {current_year}",
                "company_share",
                company_section,
            )
            for company in plan.companies:
                self._add(
                    buckets["company_share"],
                    f"{topic} {company} 市场份额 {current_year}",
                    "company_share",
                    company_section,
                    company=company,
                )

        bom_section = plan.sections.get("bom_item", "")
        if bom_section:
            self._add(
                buckets["bom_item"],
                f"{topic} BOM 成本 拆解 {current_year}",
                "bom_item",
                bom_section,
            )
            for system in plan.bom_systems:
                self._add(
                    buckets["bom_item"],
                    f"{topic} {system} 成本占比 零部件",
                    "bom_item",
                    bom_section,
                    system=system,
                )

        supplier_section = plan.sections.get("supplier", "")
        if supplier_section:
            self._add(
                buckets["supplier"],
                f"{topic} 上游 零部件 供应商 名单 {current_year}",
                "supplier",
                supplier_section,
            )
            components = plan.bom_systems[:4] or plan.section_needs.get(
                "supplier", []
            )[:4]
            for component in components:
                self._add(
                    buckets["supplier"],
                    f"{topic} {component} 供应商 配套关系",
                    "supplier",
                    supplier_section,
                    component=component,
                )

        for key, bucket in buckets.items():
            if bucket:
                self._backfill(
                    bucket,
                    key,
                    plan.sections[key],
                    topic,
                    current_year,
                    config.min_queries_per_section,
                )
            buckets[key] = bucket[: config.max_queries_per_section]

        ordered: list[DeepQuery] = []
        while len(ordered) < config.max_searches:
            added = False
            for key in ("company_share", "bom_item", "supplier"):
                if buckets[key] and len(ordered) < config.max_searches:
                    ordered.append(buckets[key].pop(0))
                    added = True
            if not added:
                break
        return ordered

    def _backfill(
        self,
        bucket: list[DeepQuery],
        record_type: str,
        section_id: str,
        topic: str,
        year: int,
        minimum: int,
    ) -> None:
        for template in _FALLBACK_QUERIES[record_type]:
            if len(bucket) >= minimum:
                break
            self._add(
                bucket,
                template.format(topic=topic, year=year),
                record_type,
                section_id,
            )

    @staticmethod
    def _add(
        bucket: list[DeepQuery],
        query: str,
        record_type: str,
        section_id: str,
        company: str = "",
        system: str = "",
        component: str = "",
    ) -> None:
        normalized = " ".join(query.split())
        if any(item.query == normalized for item in bucket):
            return
        bucket.append(
            DeepQuery(
                query=normalized,
                record_type=record_type,
                section_id=section_id,
                company=company,
                system=system,
                component=component,
            )
        )

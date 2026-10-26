from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from src.core.search.gateway import SearchRequest

from .config import DeepModeConfig
from .extractor import StructuredEvidenceExtractor
from .models import DeepModePlan
from .planner import DeepModePlanner
from .query_builder import DeepQueryBuilder
from .store import DeepModeStore
from .table_builder import DeepTableBuilder
from .validator import RecordValidator

logger = logging.getLogger(__name__)

_MAX_SCRAPES_PER_RUN = 40
_SCRAPE_TIMEOUT_SECONDS = 20
_TERMINAL_STOP_REASONS = frozenset({"max_searches_reached", "invalid_scope"})


class DeepModeService:

    _RECORD_TYPE_LABELS: ClassVar[dict[str, str]] = {
        "company_share": "公司市场份额",
        "bom_item": "BOM 成本结构",
        "supplier": "供应商配套关系",
    }

    def __init__(
        self,
        config: DeepModeConfig,
        gateway_provider: Callable[[], Any],
        scraper_provider: Callable[[], Any] | None = None,
        llm_call: Callable[[str], Awaitable[Any]] | None = None,
        store_dir: str | Path = "data/deep_mode",
    ) -> None:
        self.config = config
        self._gateway_provider = gateway_provider
        self._scraper_provider = scraper_provider
        self.planner = DeepModePlanner(config)
        self.query_builder = DeepQueryBuilder()
        self.extractor = StructuredEvidenceExtractor(
            llm_call=llm_call,
            max_records=config.max_records_per_type,
        )
        self.validator = RecordValidator()
        self.table_builder = DeepTableBuilder()
        self.store = DeepModeStore(base_dir=store_dir)
        self._records_by_section: dict[str, list[dict[str, Any]]] = {}
        self._tables_by_section: dict[str, str] = {}
        self._last_plan: DeepModePlan | None = None
        self._last_queries: list[Any] = []
        self._last_validation: list[dict[str, Any]] = []
        self._scrapes_used = 0

    async def enrich(
        self,
        *,
        topic: str,
        section_specs: list[Any],
        output_type: str = "industry_report",
        companies: list[str] | None = None,
        task_id: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        self._records_by_section = {}
        self._tables_by_section = {}
        self._last_plan = None
        self._last_queries = []
        self._last_validation = []
        self._scrapes_used = 0

        if not self.config.enabled or output_type != "industry_report":
            return {}

        plan = self.planner.build_plan(
            topic,
            section_specs,
            output_type,
            companies=companies,
        )
        if plan is None:
            return {}

        gateway = self._gateway_provider()
        if gateway is None:
            logger.warning("DeepModeService: no search gateway available")
            return {}

        now = datetime.now(timezone.utc)
        queries = self.query_builder.build(
            topic,
            plan,
            self.config,
            year=now.year,
        )
        self._last_plan = plan
        self._last_queries = queries

        records_by_section: dict[str, list[dict[str, Any]]] = {}
        scraper = self._scraper_provider() if self._scraper_provider else None
        for query in queries:
            try:
                response = await gateway.search(
                    SearchRequest(query=query.query, max_results=8),
                    scope="deep_mode",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("DeepModeService search failed: %s", exc)
                self._last_validation.append(self._error_entry(query.query, str(exc)))
                continue
            if not response.success:
                logger.warning(
                    "DeepModeService search unsuccessful for '%s': stop_reason=%s",
                    query.query,
                    response.stop_reason,
                )
                self._last_validation.append(
                    self._error_entry(
                        query.query,
                        f"unsuccessful response (stop_reason={response.stop_reason})",
                    )
                )
                if response.stop_reason in _TERMINAL_STOP_REASONS:
                    break
                continue
            try:
                documents = await self._documents_from_response(response, scraper)
                extracted = await self.extractor.extract(
                    documents,
                    query.record_type,
                    {
                        "section_id": query.section_id,
                        "data_need": query.query,
                        "period": str(now.year),
                        "system": query.system,
                    },
                )
                validation = self.validator.validate(extracted, query.record_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "DeepModeService extraction failed for '%s': %s",
                    query.query,
                    exc,
                )
                self._last_validation.append(self._error_entry(query.query, str(exc)))
                continue
            self._last_validation.append(
                {
                    "query": query.query,
                    "dropped": validation.dropped,
                    "conflicts": validation.conflicts,
                    "partial_bom": validation.partial_bom,
                }
            )
            for record in validation.records:
                records_by_section.setdefault(record.section_id, []).append(
                    record.to_data_point()
                )

        deduped_by_section: dict[str, list[dict[str, Any]]] = {}
        for section_id, points in records_by_section.items():
            kept, removed = self._dedupe_points(points)
            deduped_by_section[section_id] = kept
            if removed:
                self._last_validation.append(
                    {
                        "query": f"dedupe:{section_id}",
                        "dropped": [{"reason": "duplicate", "count": removed}],
                        "conflicts": [],
                        "partial_bom": False,
                    }
                )
        self._records_by_section = deduped_by_section
        self._tables_by_section = {
            section_id: self.table_builder.build_for_section(section_id, points)
            for section_id, points in deduped_by_section.items()
        }

        self.store.save(
            task_id=task_id,
            plan={
                "sections": plan.sections,
                "companies": plan.companies,
                "bom_systems": plan.bom_systems,
            },
            queries=[query.query for query in queries],
            records=deduped_by_section,
            validation=self._last_validation,
            tables="\n\n".join(
                text for text in self._tables_by_section.values() if text
            ),
            summary={
                "queries_used": len(queries),
                "sections": list(deduped_by_section),
                "records": sum(
                    len(points) for points in deduped_by_section.values()
                ),
                "tables": len(
                    [text for text in self._tables_by_section.values() if text]
                ),
            },
        )
        return deduped_by_section

    async def _documents_from_response(
        self, response: Any, scraper: Any
    ) -> list[dict[str, Any]]:
        documents = []
        for result in getattr(response, "results", []) or []:
            url = getattr(result, "url", "") or ""
            content = getattr(result, "snippet", "") or ""
            if (
                scraper is not None
                and url
                and "|---" not in content
                and self._scrapes_used < _MAX_SCRAPES_PER_RUN
            ):
                self._scrapes_used += 1
                content = await self._scrape_tables(scraper, url, content)
            documents.append(
                {
                    "title": getattr(result, "title", "") or "",
                    "url": url,
                    "content": content,
                    "evidence_id": getattr(result, "evidence_id", "") or "",
                    "quality_score": getattr(result, "quality_score", 0) or 0,
                }
            )
        return documents

    async def _scrape_tables(
        self, scraper: Any, url: str, fallback: str
    ) -> str:
        try:
            scraped = await asyncio.wait_for(
                scraper.execute(url=url, action="extract_tables", max_chars=3000),
                timeout=_SCRAPE_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("DeepModeService scrape failed for %s: %s", url, exc)
            return fallback
        tables = scraped.get("tables") if isinstance(scraped, dict) else None
        markdown = self._tables_to_markdown(tables or [])
        return markdown[:3000] if markdown else fallback

    @staticmethod
    def _tables_to_markdown(tables: Any) -> str:
        blocks = []
        for rows in tables or []:
            if not rows:
                continue
            lines = []
            for index, row in enumerate(rows):
                cells = [
                    str(cell or "").replace("|", "\\|").replace("\n", " ").strip()
                    for cell in row
                ]
                lines.append("| " + " | ".join(cells) + " |")
                if index == 0:
                    lines.append("|" + "---|" * len(cells))
            if len(lines) >= 2:
                blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _error_entry(label: str, error: str) -> dict[str, Any]:
        return {
            "query": label,
            "dropped": [],
            "conflicts": [],
            "partial_bom": False,
            "error": error,
        }

    @staticmethod
    def _dedupe_points(
        points: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        seen = set()
        result = []
        removed = 0
        for point in points:
            data = point.get("structured_data") or {}
            key = (
                point.get("record_type") or "",
                data.get("company_name") or "",
                data.get("system") or "",
                data.get("component") or "",
                data.get("supplier_name") or "",
                data.get("metric_basis") or "",
                point.get("period") or "",
            )
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            result.append(point)
        return result, removed

    def get_tables(self, section_id: str) -> str:
        # Shadow mode stores artifacts without injecting anywhere, so every
        # consumer of tables must see them as absent (engine analysis prompt,
        # report-upgrade chapter writer, etc.).
        if self.config.shadow:
            return ""
        return self._tables_by_section.get(section_id, "")

    def get_section_evidence(self, section_id: str) -> dict[str, Any]:
        """Return validated tables plus planned-but-empty gap notes.

        Report chapters address sections by their parent id (``section_N``
        or ``section_N::sub_k``); leaf suffixes are folded here so callers
        can pass the chapter id verbatim.  Each planned record type mapped
        to this section with zero surviving records is reported as a gap
        note so the writer can state the public-data gap explicitly instead
        of staying silent about it.
        """
        if self.config.shadow:
            return {"tables": "", "gap_notes": []}
        parent = str(section_id or "").split("::")[0]
        tables = self._tables_by_section.get(parent, "")
        present_types = {
            str(point.get("record_type") or "")
            for point in (self._records_by_section.get(parent) or [])
        }
        gap_notes: list[str] = []
        plan = self._last_plan
        if plan is not None:
            for record_type, mapped in plan.sections.items():
                if mapped == parent and record_type not in present_types:
                    gap_notes.append(
                        self._RECORD_TYPE_LABELS.get(record_type, record_type)
                    )
        return {"tables": tables, "gap_notes": gap_notes}

    def ensure_tables(
        self,
        batch_results: list[dict[str, Any]],
        section_by_agent: dict[str, str],
    ) -> None:
        for result in batch_results or []:
            section_id = section_by_agent.get(result.get("agent_id", ""), "")
            if not section_id:
                continue
            points = result.get("data_points", []) or []
            result["content"] = self.table_builder.ensure_table(
                section_id,
                result.get("content", "") or "",
                points,
            )

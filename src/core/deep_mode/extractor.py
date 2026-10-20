from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from typing import Any

from .models import BOMItemRecord, CompanyShareRecord, StructuredRecord, SupplierRecord

_MD_TABLE_RE = re.compile(r"((?:^[ \t]*\|.*\|?[ \t]*$\n?)+)", re.MULTILINE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _quote_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[tuple[str, list[str]]]] = []
        self._rows: list[tuple[str, list[str]]] = []
        self._cells: list[str] = []
        self._buffer: list[str] = []
        self._in_cell = False

    def _flush_cell(self) -> None:
        if not self._in_cell:
            return
        self._cells.append("".join(self._buffer).strip())
        self._in_cell = False
        self._buffer = []

    def _flush_row(self) -> None:
        self._flush_cell()
        if not self._cells:
            return
        cells = self._cells
        self._rows.append((_quote_row(cells), cells))
        self._cells = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._flush_row()
            self._rows = []
        elif tag == "tr":
            self._flush_row()
            self._cells = []
        elif tag in {"td", "th"}:
            self._flush_cell()
            self._in_cell = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self._flush_cell()
        elif tag == "tr":
            self._flush_row()
        elif tag == "table":
            self._flush_row()
            if self._rows:
                self.tables.append(self._rows)
            self._rows = []


def _iter_tables(content: str) -> list[list[tuple[str, list[str]]]]:
    tables: list[list[tuple[str, list[str]]]] = []
    for block in _MD_TABLE_RE.findall(content or ""):
        rows: list[tuple[str, list[str]]] = []
        for line in block.strip().splitlines():
            raw = line.strip()
            cells = [cell.strip() for cell in raw.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            rows.append((raw, cells))
        if len(rows) >= 2:
            tables.append(rows)
    if "<table" in (content or "").lower():
        parser = _HTMLTableParser()
        parser.feed(content)
        tables.extend(parser.tables)
    return tables


def _parse_pct(value: str) -> float | None:
    match = _PCT_RE.search(value or "")
    if match:
        return float(match.group(1))
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def _find_col(header: list[str], aliases: tuple[str, ...]) -> int | None:
    for index, name in enumerate(header):
        lowered = name.lower()
        if any(alias in lowered for alias in aliases):
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class StructuredEvidenceExtractor:
    def __init__(
        self,
        llm_call: Callable[[str], Awaitable[Any]] | None = None,
        max_records: int = 30,
    ) -> None:
        self._llm_call = llm_call
        self._max_records = max_records

    async def extract(
        self,
        documents: list[dict[str, Any]],
        record_type: str,
        context: dict[str, Any],
    ) -> list[StructuredRecord]:
        records: list[StructuredRecord] = []
        for doc in documents:
            for table in _iter_tables(str(doc.get("content") or "")):
                records.extend(self._from_table(table, record_type, doc, context))
        if not records and self._llm_call:
            records.extend(await self._from_llm(documents, record_type, context))
        return self._dedupe(records)[: self._max_records]

    def _from_table(
        self,
        table: list[list[tuple[str, list[str]]]],
        record_type: str,
        doc: dict[str, Any],
        context: dict[str, Any],
    ) -> list[StructuredRecord]:
        if len(table) < 2:
            return []
        header = [cell.lower() for cell in table[0][1]]
        if record_type == "company_share":
            return self._company_rows(table, header, doc, context)
        if record_type == "bom_item":
            return self._bom_rows(table, header, doc, context)
        if record_type == "supplier":
            return self._supplier_rows(table, header, doc, context)
        return []

    def _base(self, doc: dict[str, Any], context: dict[str, Any], quote: str) -> dict[str, Any]:
        return {
            "section_id": str(context.get("section_id") or ""),
            "data_need": str(context.get("data_need") or ""),
            "source_url": str(doc.get("url") or ""),
            "source_title": str(doc.get("title") or ""),
            "source_quote": quote,
            "evidence_id": str(doc.get("evidence_id") or ""),
            "period": str(context.get("period") or ""),
            "quality_score": float(doc.get("quality_score") or 0.0),
        }

    def _company_rows(self, table, header, doc, context):
        company_col = _find_col(header, ("公司", "企业", "company", "player"))
        share_col = _find_col(header, ("份额", "市占", "share"))
        if company_col is None or share_col is None:
            return []
        basis_col = _find_col(header, ("口径", "basis", "metric"))
        period_col = _find_col(header, ("期间", "年份", "period", "year"))
        records = []
        for raw, row in table[1:]:
            company = _cell(row, company_col)
            share = _parse_pct(_cell(row, share_col))
            if not company or share is None:
                continue
            base = self._base(doc, context, raw)
            if period_col is not None:
                base["period"] = _cell(row, period_col) or base["period"]
            records.append(
                CompanyShareRecord(
                    **base,
                    company_name=company,
                    share_pct=share,
                    metric_basis=_cell(row, basis_col),
                )
            )
        return records

    def _bom_rows(self, table, header, doc, context):
        system_col = _find_col(header, ("系统", "system"))
        component_col = _find_col(header, ("部件", "零件", "component", "part"))
        cost_col = _find_col(header, ("占比", "成本", "cost", "share"))
        supplier_col = _find_col(header, ("供应商", "supplier"))
        if component_col is None or cost_col is None:
            return []
        records = []
        for raw, row in table[1:]:
            component = _cell(row, component_col)
            cost = _parse_pct(_cell(row, cost_col))
            if not component or cost is None:
                continue
            supplier = _cell(row, supplier_col)
            base = self._base(doc, context, raw)
            records.append(
                BOMItemRecord(
                    **base,
                    system=_cell(row, system_col) or str(context.get("system") or ""),
                    component=component,
                    cost_share_pct=cost,
                    supplier_names=[supplier] if supplier else [],
                )
            )
        return records

    def _supplier_rows(self, table, header, doc, context):
        supplier_col = _find_col(header, ("供应商", "supplier"))
        component_col = _find_col(header, ("部件", "零件", "component", "part"))
        customer_col = _find_col(header, ("客户", "customer"))
        if supplier_col is None or component_col is None:
            return []
        records = []
        for raw, row in table[1:]:
            supplier = _cell(row, supplier_col)
            component = _cell(row, component_col)
            if not supplier or not component:
                continue
            customer = _cell(row, customer_col)
            records.append(
                SupplierRecord(
                    **self._base(doc, context, raw),
                    supplier_name=supplier,
                    component=component,
                    customers=[customer] if customer else [],
                )
            )
        return records

    async def _from_llm(self, documents, record_type, context) -> list[StructuredRecord]:
        if not documents:
            return []
        docs_text = "\n\n".join(
            f"[{index}] {doc.get('title', '')}\nURL: {doc.get('url', '')}\n"
            f"EVIDENCE_ID: {doc.get('evidence_id', '')}\n{str(doc.get('content') or '')[:3000]}"
            for index, doc in enumerate(documents)
        )
        prompt = f"""从以下资料抽取 {record_type} 记录。
只输出 JSON，不要解释。每个记录必须包含 source_quote 和 evidence_id。
无法确认的数字不要输出。

资料：
{docs_text}
"""
        response = await self._llm_call(prompt)
        if isinstance(response, dict) and response.get("success") is False:
            return []
        content = response.get("content", "") if isinstance(response, dict) else response
        content = content if isinstance(content, str) else ""
        payload = self._load_json(content)
        items = payload.get("records", []) if isinstance(payload, dict) else payload
        records = []
        if not isinstance(items, list):
            return records
        for item in items:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("source_quote") or "").strip()
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not quote or not evidence_id:
                continue
            doc = next(
                (d for d in documents if str(d.get("evidence_id") or "") == evidence_id),
                {},
            )
            if not doc.get("url"):
                continue
            base = self._base(doc, context, quote)
            try:
                if record_type == "company_share":
                    records.append(
                        CompanyShareRecord(
                            **base,
                            company_name=str(item.get("company_name") or ""),
                            share_pct=float(item.get("share_pct") or 0),
                            metric_basis=str(item.get("metric_basis") or ""),
                            ticker=str(item.get("ticker") or ""),
                        )
                    )
                elif record_type == "bom_item":
                    records.append(
                        BOMItemRecord(
                            **base,
                            system=str(item.get("system") or ""),
                            component=str(item.get("component") or ""),
                            cost_share_pct=float(item.get("cost_share_pct") or 0),
                            supplier_names=_as_list(item.get("supplier_names")),
                        )
                    )
                elif record_type == "supplier":
                    records.append(
                        SupplierRecord(
                            **base,
                            supplier_name=str(item.get("supplier_name") or ""),
                            component=str(item.get("component") or ""),
                            customers=_as_list(item.get("customers")),
                        )
                    )
            except (TypeError, ValueError):
                continue
        return records

    @staticmethod
    def _load_json(content: str) -> Any:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _dedupe(records: list[StructuredRecord]) -> list[StructuredRecord]:
        seen = set()
        result = []
        for record in records:
            payload = record.payload()
            key = (
                record.record_type,
                record.source_url,
                record.period,
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(record)
        return result

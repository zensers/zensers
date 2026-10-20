from __future__ import annotations

from typing import Any


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _record_type_for_section(section_id: str) -> str:
    text = (section_id or "").lower()
    if "compet" in text or "竞争" in text:
        return "company_share"
    if "tech" in text or "技术" in text or "bom" in text:
        return "bom_item"
    if "value" in text or "chain" in text or "产业链" in text or "supply" in text:
        return "supplier"
    return ""


class DeepTableBuilder:
    def build_for_section(self, section_id: str, data_points: list[dict[str, Any]]) -> str:
        supported = {"company_share", "bom_item", "supplier"}
        present = [
            point.get("record_type")
            for point in (data_points or [])
            if point.get("record_type") in supported
        ]
        record_type = max(present, key=present.count) if present else _record_type_for_section(section_id)
        records = [
            point for point in data_points or [] if point.get("record_type") == record_type
        ]
        if record_type == "company_share":
            return self.build_company_share_table(records)
        if record_type == "bom_item":
            return self.build_bom_table(records)
        if record_type == "supplier":
            return self.build_supplier_table(records)
        return ""

    def ensure_table(
        self,
        section_id: str,
        content: str,
        data_points: list[dict[str, Any]],
    ) -> str:
        table = self.build_for_section(section_id, data_points)
        if not table:
            return content
        first_line = table.splitlines()[0]
        if first_line in content:
            return content
        return f"{content.rstrip()}\n\n### 深度模式数据表\n\n{table}\n"

    def build_company_share_table(self, records: list[dict[str, Any]]) -> str:
        rows = sorted(
            records,
            key=lambda point: float((point.get("structured_data") or {}).get("share_pct") or 0),
            reverse=True,
        )
        if not rows:
            return ""
        lines = [
            "| 公司 | 市场份额 | 统计口径 | 期间 | 数据性质 | 来源 |",
            "|---|---|---|---|---|---|",
        ]
        notes = []
        for point in rows:
            data = point.get("structured_data") or {}
            marker = "*" if point.get("is_estimate") else ""
            nature = "估算" if point.get("is_estimate") else "披露"
            url = str(point.get("url") or "")
            lines.append(
                f"| {_cell(data.get('company_name', ''))} | {float(data.get('share_pct') or 0):.1f}%{marker} "
                f"| {_cell(data.get('metric_basis', ''))} | {_cell(point.get('period', ''))} "
                f"| {nature} | [链接]({url}) |"
            )
            if point.get("is_estimate"):
                notes.append(
                    f"\\* 估算值：{_cell(point.get('estimate_method', '未注明'))}；锚点：{url}"
                )
        return "\n".join(lines + ([""] + notes if notes else []))

    def build_bom_table(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ""
        lines = [
            "| 系统 | 部件 | 成本占比 | 关键供应商 | 技术路线/备注 | 来源 |",
            "|---|---|---|---|---|---|",
        ]
        notes = []
        for point in records:
            data = point.get("structured_data") or {}
            marker = "*" if point.get("is_estimate") else ""
            suppliers = _cell("、".join(data.get("supplier_names") or []))
            url = str(point.get("url") or "")
            lines.append(
                f"| {_cell(data.get('system', ''))} | {_cell(data.get('component', ''))} "
                f"| {float(data.get('cost_share_pct') or 0):.1f}%{marker} "
                f"| {suppliers} | {_cell(data.get('model', ''))} | [链接]({url}) |"
            )
            if point.get("is_estimate"):
                notes.append(
                    f"\\* 估算值：{_cell(point.get('estimate_method', '未注明'))}；锚点：{url}"
                )
        return "\n".join(lines + ([""] + notes if notes else []))

    def build_supplier_table(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ""
        lines = [
            "| 环节 | 主要供应商 | 配套关系 | 期间 | 来源 |",
            "|---|---|---|---|---|",
        ]
        for point in records:
            data = point.get("structured_data") or {}
            customers = _cell("、".join(data.get("customers") or []))
            url = str(point.get("url") or "")
            lines.append(
                f"| {_cell(data.get('component', ''))} | {_cell(data.get('supplier_name', ''))} "
                f"| {_cell(data.get('relationship_type', 'supplier'))}（客户：{customers}） "
                f"| {_cell(point.get('period', ''))} | [链接]({url}) |"
            )
        return "\n".join(lines)

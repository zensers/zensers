# -*- coding: utf-8 -*-
"""
AnnualReportParserSkill — PDF Annual Report Parsing with Dynamic TOC (v1.5)

Parses PDF annual reports from global exchanges (A股/港股/美股10-K/日股):
1. Extract TOC via PDF bookmarks (PyPDF2) or LLM fallback
2. Extract text + tables via pdfplumber
3. Dynamic chapter splitting (TOC-based or LLM-based)
4. Generate analysis framework dynamically via LLM
5. Smart financial table extraction (multilingual keywords + LLM fallback)
6. Table quality validation
7. Scanned page detection + Vision OCR (P2-1)
8. Chart/image understanding via Vision LLM (P2-2)
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.skills.base import Skill

logger = logging.getLogger(__name__)

FINANCIAL_TABLE_KEYWORDS = {
    "income": {
        "zh": ["营业收入", "营业成本", "净利润", "利润总额", "营业利润", "毛利润"],
        "en": ["Revenue", "Net Income", "Gross Profit", "Operating Income", "Cost of Revenue", "EBITDA"],
        "ja": ["売上高", "営業利益", "経常利益", "当期純利益"],
    },
    "balance": {
        "zh": ["总资产", "总负债", "所有者权益", "流动资产", "流动负债", "净资产"],
        "en": ["Total Assets", "Total Liabilities", "Stockholders Equity", "Current Assets", "Current Liabilities"],
        "ja": ["総資産", "負債", "純資産", "流動資産"],
    },
    "cashflow": {
        "zh": ["经营活动", "投资活动", "筹资活动", "现金流量", "自由现金流"],
        "en": ["Operating Activities", "Investing Activities", "Financing Activities", "Cash Flow", "Free Cash Flow"],
        "ja": ["営業活動", "投資活動", "財務活動", "キャッシュフロー"],
    },
}

TYPE_TO_PROFILE = {
    "overview": "executive_summary_role",
    "business": "enterprise",
    "financial": "financial_analysis",
    "cashflow": "financial_analysis",
    "governance": "enterprise",
    "strategy": "enterprise",
    "risk": "risk",
    "investment": "investment",
    "other": "general",
}

TYPE_TO_ASPECT_NAME = {
    "overview": "概述",
    "business": "经营分析",
    "financial": "财务分析",
    "cashflow": "现金流分析",
    "governance": "治理分析",
    "strategy": "战略展望",
    "risk": "风险评估",
    "investment": "投资价值",
}

MAX_FILE_SIZE_MB = 100
MAX_TOTAL_SIZE_MB = 300
MAX_PAGES_NO_BOOKMARK = 200


class AnnualReportParserSkill(Skill):
    """
    Annual Report Parser Skill

    Parses PDF annual reports with dynamic TOC-based chapter recognition.
    Supports: A-share, HK, US 10-K, Japan 有価証券報告書.
    """

    @property
    def name(self) -> str:
        return "annual_report_parser"

    @property
    def description(self) -> str:
        return (
            "Parse PDF annual reports from global exchanges. "
            "Extracts TOC, chapters, financial tables, and generates "
            "dynamic analysis framework. Supports A-share, HK, US 10-K, Japan."
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "parse")
        if action == "parse":
            return await self._action_parse(kwargs)
        return self._failure(f"Unsupported action: {action}")

    async def _action_parse(self, kwargs: Dict) -> Dict[str, Any]:
        file_paths = kwargs.get("file_paths", [])
        extract_tables = kwargs.get("extract_tables", True)
        extract_sections = kwargs.get("extract_sections", True)
        user_requirement = kwargs.get("user_requirement")

        if not file_paths:
            return self._failure("No file_paths provided")

        reports = []
        for fp in file_paths:
            result = await self._parse_single_report(fp, extract_tables, extract_sections, user_requirement)
            if result.get("success"):
                reports.append(result["data"])
            else:
                logger.warning(f"Failed to parse {fp}: {result.get('error')}")

        if not reports:
            return self._failure("All PDF files failed to parse")

        merged = self._merge_reports(reports)

        return self._success({
            "data": merged,
            "file_count": len(file_paths),
            "success_count": len(reports),
        }, f"Parsed {len(reports)}/{len(file_paths)} reports")

    async def _parse_single_report(
        self,
        file_path: str,
        extract_tables: bool = True,
        extract_sections: bool = True,
        user_requirement: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        import os
        if not os.path.isfile(file_path):
            return self._failure(f"File not found: {file_path}")

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            return self._failure(f"File too large: {file_size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)")

        result = {
            "meta": {"file_path": file_path, "file_size_mb": round(file_size_mb, 1)},
            "sections": [],
            "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
            "analysis_framework": {},
            "full_text": "",
            "table_validation": {},
        }

        try:
            toc_entries = self._extract_toc(file_path)
            all_text, all_tables = self._extract_text_and_tables(file_path)

            result["meta"]["page_count"] = len(all_text)
            result["meta"]["has_bookmarks"] = bool(toc_entries)
            result["meta"]["year"] = self._extract_year(file_path, all_text[:5] if all_text else [])

            if extract_sections:
                if toc_entries:
                    result["sections"] = self._split_by_toc(all_text, toc_entries)
                else:
                    result["sections"] = await self._split_by_llm(all_text)

                result["analysis_framework"] = await self._generate_analysis_framework(
                    sections=result["sections"],
                    meta=result["meta"],
                    user_requirement=user_requirement,
                )

            if extract_tables:
                result["financial_tables"] = await self._extract_financial_tables_smart(all_tables)

            result["full_text"] = "\n\n".join(t for t in all_text if t)
            result["table_validation"] = self._validate_tables(result["financial_tables"])

            scanned_pages = self._detect_scanned_pages(file_path, all_text)
            if scanned_pages:
                result["meta"]["scanned_pages"] = scanned_pages
                ocr_text = await self._ocr_pages_via_vision(file_path, scanned_pages)
                if ocr_text:
                    result["ocr_text"] = ocr_text
                    result["full_text"] += "\n\n" + "\n\n".join(ocr_text.values())

            chart_pages = self._detect_chart_pages(file_path, all_text, all_tables)
            if chart_pages:
                result["meta"]["chart_pages"] = chart_pages
                chart_descs = await self._describe_charts_via_vision(file_path, chart_pages)
                if chart_descs:
                    result["chart_descriptions"] = chart_descs

        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}", exc_info=True)
            return self._failure(f"Parse error: {e}")

        return self._success({"data": result}, "Report parsed")

    def _extract_toc(self, file_path: str) -> List[Dict]:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            outlines = reader.outline
            if not outlines:
                return []
            return self._flatten_outlines(reader, outlines, level=1)
        except ImportError:
            logger.warning("PyPDF2 not installed, skipping TOC extraction")
            return []
        except Exception as e:
            logger.warning(f"TOC extraction failed: {e}")
            return []

    def _flatten_outlines(self, reader, outlines, level: int = 1) -> List[Dict]:
        result = []
        if not outlines:
            return result
        for entry in outlines:
            if isinstance(entry, list):
                result.extend(self._flatten_outlines(reader, entry, level + 1))
            else:
                try:
                    title = entry.title if hasattr(entry, 'title') else str(entry)
                    page_num = None
                    if hasattr(entry, 'page') and entry.page:
                        try:
                            page_num = reader.get_destination_page_number(entry) + 1
                        except Exception:
                            pass
                    result.append({"title": title, "page": page_num, "level": level})
                except Exception:
                    pass
        return result

    def _extract_text_and_tables(self, file_path: str):
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not installed")
            return [], []

        all_text = []
        all_tables = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)

                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = [str(h).strip() if h else "" for h in table[0]]
                    rows = []
                    for row in table[1:]:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        if any(c for c in cleaned):
                            rows.append(cleaned)
                    if rows:
                        all_tables.append({"headers": headers, "rows": rows})

        return all_text, all_tables

    def _split_by_toc(self, all_text: List[str], toc_entries: List[Dict]) -> List[Dict]:
        sections = []
        for i, entry in enumerate(toc_entries):
            if entry.get("level", 1) > 2:
                continue

            title = entry.get("title", "").strip()
            page = entry.get("page")

            if not title:
                continue

            next_page = None
            for j in range(i + 1, len(toc_entries)):
                if toc_entries[j].get("level", 1) <= entry.get("level", 1) and toc_entries[j].get("page"):
                    next_page = toc_entries[j]["page"]
                    break

            content = ""
            if page is not None:
                start = max(0, page - 1)
                end = (next_page - 1) if next_page else min(start + 20, len(all_text))
                end = min(end, len(all_text))
                content = "\n".join(all_text[start:end])

            sections.append({
                "title": title,
                "page": page,
                "level": entry.get("level", 1),
                "content": content,
                "section_type": self._guess_section_type(title),
                "importance": self._guess_importance(title),
            })

        return sections

    async def _split_by_llm(self, all_text: List[str]) -> List[Dict]:
        if not all_text:
            return []

        toc_pages = min(10, len(all_text))
        toc_text = "\n".join(all_text[:toc_pages])
        if len(toc_text.strip()) < 100:
            return [{"title": "Full Report", "page": 1, "level": 1,
                      "content": "\n".join(all_text), "section_type": "overview", "importance": 3}]

        prompt = f"""分析以下年报文本，识别其目录结构。
输出JSON数组，每个元素包含：
- "title": 章节标题原文
- "section_type": 章节类型，从以下选一个：
  "overview"（概述/摘要）、"business"（经营/业务）、
  "financial"（财务）、"cashflow"（现金流）、"governance"（治理）、
  "strategy"（战略/展望）、"risk"（风险）、"investment"（投资价值）、
  "other"（其他）
- "importance": 1-5（5=核心章节如财务/风险，1=次要如备查文件）

年报前10页文本：
{toc_text[:6000]}

输出格式：[{{"title": "...", "section_type": "...", "importance": N}}]
仅输出JSON数组，不要解释。"""

        try:
            from src.core.llm_client import call_llm
            llm_result = await call_llm(prompt=prompt, system_prompt="你是年报结构分析专家。仅输出JSON。")
            if llm_result.get("success") and llm_result.get("content"):
                content = llm_result["content"]
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                sections = json.loads(content.strip())
                valid = [s for s in sections if isinstance(s, dict) and "title" in s]
                if valid:
                    for s in valid:
                        s.setdefault("page", None)
                        s.setdefault("level", 1)
                        s.setdefault("content", "")
                    return valid
        except Exception as e:
            logger.warning(f"LLM chapter splitting failed: {e}")

        return [{"title": "Full Report", "page": 1, "level": 1,
                  "content": "\n".join(all_text), "section_type": "overview", "importance": 3}]

    async def _generate_analysis_framework(
        self,
        sections: List[Dict],
        meta: Dict,
        user_requirement: Optional[Dict] = None,
    ) -> Dict:
        empty = {"aspects": [], "aspect_to_profile": {}, "section_to_aspect": {}, "aspect_to_section_ids": {}}
        if not sections:
            return empty

        section_summaries = []
        for i, s in enumerate(sections):
            title = s.get("title", "")
            stype = s.get("section_type", "other")
            importance = s.get("importance", 3)
            section_summaries.append(f"{i + 1}. {title} (type={stype}, importance={importance})")

        sections_text = "\n".join(section_summaries)
        user_focus = ""
        if user_requirement:
            user_focus = f"\n\n用户特别关注：{user_requirement.get('topic', '')}"

        prompt = f"""基于以下年报章节结构，设计分析框架。

年报元信息：{meta}
章节列表：
{sections_text}
{user_focus}

要求：
1. 生成5-9个分析维度(aspects)，每个维度用简洁的中文名称
2. 为每个维度指定专业分析角色profile（从以下选择）：
   financial_analysis, valuation, risk, enterprise, investment, general, executive_summary_role
3. 为每个维度标注需要分析的章节编号
4. 维度应该覆盖年报的核心内容，忽略低重要性章节(importance<=2)

输出JSON：
{{"aspects": ["维度1", ...], "aspect_to_profile": {{"维度1": "profile名", ...}}, "aspect_to_section_ids": {{"维度1": [章节编号], ...}}}}
仅输出JSON，不要解释。"""

        try:
            from src.core.llm_client import call_llm
            result = await call_llm(
                prompt=prompt,
                system_prompt="你是全球资本市场年报分析专家，熟悉各交易所年报格式。仅输出JSON。",
            )
            if result.get("success") and result.get("content"):
                content = result["content"]
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                framework = json.loads(content.strip())
                if isinstance(framework, dict) and "aspects" in framework:
                    framework.setdefault("aspect_to_profile", {})
                    framework.setdefault("section_to_aspect", {})
                    framework.setdefault("aspect_to_section_ids", {})
                    return framework
        except Exception as e:
            logger.warning(f"LLM framework generation failed: {e}")

        return self._generate_fallback_framework(sections)

    def _generate_fallback_framework(self, sections: List[Dict]) -> Dict:
        type_groups: Dict[str, List[int]] = {}
        for i, s in enumerate(sections):
            stype = s.get("section_type", "other")
            if s.get("importance", 3) < 3 and stype == "other":
                continue
            type_groups.setdefault(stype, []).append(i + 1)

        aspects = []
        aspect_to_profile = {}
        aspect_to_section_ids = {}
        for stype, indices in type_groups.items():
            aspect_name = TYPE_TO_ASPECT_NAME.get(stype, stype)
            aspects.append(aspect_name)
            aspect_to_profile[aspect_name] = TYPE_TO_PROFILE.get(stype, "general")
            aspect_to_section_ids[aspect_name] = indices

        return {
            "aspects": aspects,
            "aspect_to_profile": aspect_to_profile,
            "section_to_aspect": {},
            "aspect_to_section_ids": aspect_to_section_ids,
        }

    async def _extract_financial_tables_smart(self, all_tables: List[Dict]) -> Dict:
        result = {"income": [], "balance": [], "cashflow": [], "key_metrics": []}
        unclassified = []

        for table in all_tables:
            table_text = " ".join(
                cell for row in table.get("rows", []) for cell in row if cell
            )
            detected = False
            for table_type, keywords_by_lang in FINANCIAL_TABLE_KEYWORDS.items():
                all_keywords = []
                for lang_keywords in keywords_by_lang.values():
                    all_keywords.extend(lang_keywords)
                if any(kw in table_text for kw in all_keywords):
                    result[table_type].extend(self._normalize_financial_table(table))
                    detected = True
                    break

            if not detected and len(table.get("rows", [])) > 5:
                unclassified.append(table)

        if unclassified:
            llm_classified = await self._classify_tables_by_llm(unclassified)
            for table_type, tables in llm_classified.items():
                if table_type in result:
                    result[table_type].extend(tables)

        return result

    async def _classify_tables_by_llm(self, tables: List[Dict]) -> Dict:
        summaries = []
        for i, t in enumerate(tables[:3]):
            headers = t.get("headers", [])[:5]
            first_rows = t.get("rows", [])[:2]
            summaries.append(f"Table {i + 1}: headers={headers}, first_rows={first_rows}")

        prompt = f"""判断以下表格是否为财务报表（利润表/资产负债表/现金流量表）。
输出JSON: {{"income": [表格编号], "balance": [表格编号], "cashflow": [表格编号], "skip": [非财务表格编号]}}

表格：
{chr(10).join(summaries)}
仅输出JSON。"""

        try:
            from src.core.llm_client import call_llm
            llm_result = await call_llm(
                prompt=prompt, system_prompt="你是财务报表识别专家。仅输出JSON。",
            )
            if llm_result.get("success") and llm_result.get("content"):
                content = llm_result["content"]
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                classification = json.loads(content.strip())
                output: Dict[str, list] = {}
                for table_type in ("income", "balance", "cashflow"):
                    indices = classification.get(table_type, [])
                    for idx in indices:
                        if isinstance(idx, int) and 0 <= idx - 1 < len(tables):
                            output.setdefault(table_type, []).extend(
                                self._normalize_financial_table(tables[idx - 1])
                            )
                return output
        except Exception as e:
            logger.warning(f"LLM table classification failed: {e}")
        return {}

    def _normalize_financial_table(self, table: Dict) -> List[Dict]:
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        year_columns: Dict[int, int] = {}
        for i, h in enumerate(headers):
            year_match = re.search(r'20\d{2}', str(h))
            if year_match:
                year_columns[int(year_match.group())] = i

        normalized = []
        for row in rows:
            if not row or not row[0]:
                continue
            entry = {"科目": row[0].strip()}
            for year, col_idx in year_columns.items():
                if col_idx < len(row) and row[col_idx]:
                    try:
                        val_str = row[col_idx].replace(",", "").replace("(", "-").replace(")", "").replace("－", "-")
                        entry[str(year)] = float(val_str)
                    except (ValueError, AttributeError):
                        entry[str(year)] = row[col_idx]
            normalized.append(entry)

        return normalized

    def _validate_tables(self, financial_tables: Dict) -> Dict:
        validation = {
            "total_tables": 0,
            "valid_tables": 0,
            "warnings": [],
            "needs_manual_review": [],
        }

        for table_type, rows in financial_tables.items():
            if not isinstance(rows, list):
                continue
            validation["total_tables"] += len(rows)

            if not rows:
                # Key metrics are an optional derived section; the primary
                # statements already provide sufficient source data when
                # present, so do not request an unnecessary stock-data
                # supplement merely because this optional table is empty.
                if table_type == "key_metrics":
                    continue
                validation["warnings"].append(
                    f"{table_type}: 未提取到任何表格数据，将补充stock_data API数据"
                )
                continue

            non_numeric_count = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for k, v in row.items():
                    if k == "科目":
                        continue
                    if isinstance(v, str) and v.strip():
                        try:
                            float(v.replace(",", "").replace("(", "-").replace(")", ""))
                        except ValueError:
                            non_numeric_count += 1

            if non_numeric_count > len(rows) * 0.3:
                validation["needs_manual_review"].append(
                    f"{table_type}: {non_numeric_count}个非数值单元格（可能因合并单元格导致），建议人工核对"
                )

            if len(rows) < 3:
                validation["warnings"].append(
                    f"{table_type}: 仅{len(rows)}行数据，可能因跨页断裂导致不完整"
                )

            validation["valid_tables"] += 1

        return validation

    def _guess_section_type(self, title: str) -> str:
        t = title.lower()
        if any(kw in t for kw in ["overview", "summary", "概述", "摘要", "目录", "高管"]):
            return "overview"
        if any(kw in t for kw in ["business", "operation", "经营", "业务", "主营"]):
            return "business"
        if any(kw in t for kw in ["financial", "finance", "财务", "会计", "income", "balance sheet"]):
            return "financial"
        if any(kw in t for kw in ["cash flow", "cashflow", "现金流"]):
            return "cashflow"
        if any(kw in t for kw in ["governance", "corporate", "治理", "董事", "内控", "股东"]):
            return "governance"
        if any(kw in t for kw in ["strategy", "outlook", "战略", "展望", "future", "前景"]):
            return "strategy"
        if any(kw in t for kw in ["risk", "风险", "uncertaint"]):
            return "risk"
        if any(kw in t for kw in ["investment", "投资", "valuation", "估值"]):
            return "investment"
        return "other"

    def _guess_importance(self, title: str) -> int:
        t = title.lower()
        if any(kw in t for kw in ["财务", "financial", "risk", "风险", "经营", "business"]):
            return 5
        if any(kw in t for kw in ["cashflow", "现金流", "governance", "治理", "strategy", "战略"]):
            return 4
        if any(kw in t for kw in ["overview", "概述", "summary", "investment", "投资"]):
            return 3
        if any(kw in t for kw in ["目录", "备查", "supplementary", "definition"]):
            return 1
        return 2

    def _merge_reports(self, reports: List[Dict]) -> Dict:
        if len(reports) == 1:
            result = reports[0]
            if "table_validation" not in result:
                result["table_validation"] = self._validate_tables(result.get("financial_tables", {}))
            return result

        merged = {
            "meta": {"report_count": len(reports)},
            "sections": [],
            "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
            "analysis_framework": {},
            "full_text": "",
            "table_validation": {},
        }

        for i, r in enumerate(reports):
            prefix = f"report_{i + 1}"
            meta = r.get("meta", {})
            meta["report_index"] = i + 1
            merged["meta"][prefix] = meta

            for s in r.get("sections", []):
                s_copy = dict(s)
                s_copy["report_index"] = i + 1
                merged["sections"].append(s_copy)

            for table_type in ("income", "balance", "cashflow", "key_metrics"):
                merged["financial_tables"][table_type].extend(
                    r.get("financial_tables", {}).get(table_type, [])
                )

            if not merged["analysis_framework"] and r.get("analysis_framework"):
                merged["analysis_framework"] = r["analysis_framework"]

        merged["table_validation"] = self._validate_tables(merged["financial_tables"])

        if len(reports) > 1:
            merged["cross_year"] = self._align_cross_year(reports)

        return merged

    def _extract_year(self, file_path: str, first_pages: List[str]) -> Optional[int]:
        import os
        filename = os.path.basename(file_path)
        year_match = re.search(r'20\d{2}', filename)
        if year_match:
            return int(year_match.group())
        text = "\n".join(first_pages)
        year_matches = re.findall(r'(?:20\d{2})\s*(?:年|年度|annual|fiscal)?\s*(?:报告|年报|report)', text, re.IGNORECASE)
        if year_matches:
            ym = re.search(r'20\d{2}', year_matches[0])
            if ym:
                return int(ym.group())
        all_years = re.findall(r'20\d{2}', text[:3000])
        if all_years:
            from collections import Counter
            return int(Counter(all_years).most_common(1)[0][0])
        return None

    def _align_cross_year(self, reports: List[Dict]) -> Dict:
        all_metrics: Dict[str, Dict[int, float]] = {}
        for report in reports:
            year = report.get("meta", {}).get("year")
            if not year:
                continue
            year = int(year)
            for table_type in ("income", "balance", "cashflow", "key_metrics"):
                for entry in report.get("financial_tables", {}).get(table_type, []):
                    if not isinstance(entry, dict):
                        continue
                    metric_name = entry.get("科目", "")
                    value = entry.get(str(year))
                    if metric_name and value is not None and isinstance(value, (int, float)):
                        all_metrics.setdefault(metric_name, {})[year] = value

        cross_year_summary = {}
        for metric, year_values in all_metrics.items():
            years = sorted(year_values.keys())
            if len(years) < 2:
                continue
            first_val = year_values[years[0]]
            last_val = year_values[years[-1]]
            n = years[-1] - years[0]
            if first_val and first_val != 0 and n > 0:
                cagr = ((last_val / first_val) ** (1 / n) - 1) * 100
                cross_year_summary[f"{metric}_cagr_{n}y"] = round(cagr, 2)
            for i in range(1, len(years)):
                prev = year_values[years[i - 1]]
                curr = year_values[years[i]]
                if prev and prev != 0:
                    yoy = (curr - prev) / abs(prev) * 100
                    cross_year_summary[f"{metric}_yoy_{years[i]}"] = round(yoy, 2)

        return {
            "metrics_by_year": all_metrics,
            "cross_year_summary": cross_year_summary,
        }

    SCANNED_PAGE_MIN_CHARS = 30
    SCANNED_PAGE_MAX_IMAGES = 1

    def _detect_scanned_pages(self, file_path: str, all_text: List[str]) -> List[int]:
        scanned = []
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = all_text[i] if i < len(all_text) else ""
                    text_len = len(text.strip()) if text else 0
                    images = page.images
                    if text_len < self.SCANNED_PAGE_MIN_CHARS and len(images) >= self.SCANNED_PAGE_MAX_IMAGES:
                        scanned.append(i)
        except Exception as e:
            logger.warning(f"Scanned page detection failed: {e}")
        return scanned

    def _detect_chart_pages(self, file_path: str, all_text: List[str], all_tables: List[Dict]) -> List[int]:
        chart_pages = []
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    images = page.images
                    if not images:
                        continue
                    text = all_text[i] if i < len(all_text) else ""
                    text_len = len(text.strip()) if text else 0
                    if text_len > 50 and len(images) >= 1:
                        has_chart_keyword = False
                        if text:
                            chart_kws = ["图", "图表", "chart", "graph", "figure", "趋势", "对比", "分布"]
                            has_chart_keyword = any(kw in text.lower() for kw in chart_kws)
                        if has_chart_keyword or len(images) >= 2:
                            chart_pages.append(i)
        except Exception as e:
            logger.warning(f"Chart page detection failed: {e}")
        return chart_pages

    async def _ocr_pages_via_vision(self, file_path: str, page_indices: List[int]) -> Dict[int, str]:
        from src.core.llm_client import call_llm_vision
        from src.config import settings

        vision_model = getattr(settings.llm, 'vision_model', None)
        if not vision_model:
            logger.info("No vision_model configured, skipping OCR")
            return {}

        api_key = getattr(settings.llm, 'vision_api_key', None) or settings.llm.api_key
        base_url = getattr(settings.llm, 'vision_base_url', None) or settings.llm.base_url

        result = {}
        batch_size = 3
        for start in range(0, len(page_indices), batch_size):
            batch = page_indices[start:start + batch_size]
            for idx in batch:
                try:
                    img_b64 = self._render_page_to_base64(file_path, idx)
                    if not img_b64:
                        continue
                    resp = await call_llm_vision(
                        prompt="请将此页面中的所有文字精确提取出来，保持原始格式和结构。如果有表格，用Markdown表格格式输出。只输出提取的文字，不要添加解释。",
                        images=[img_b64],
                        model=vision_model,
                        api_key=api_key,
                        base_url=base_url,
                        max_tokens=2000,
                        temperature=0.1,
                    )
                    if resp.get("success"):
                        result[idx] = resp["content"]
                    else:
                        logger.warning(f"Vision OCR failed for page {idx}: {resp.get('message', '')}")
                except Exception as e:
                    logger.warning(f"Vision OCR error on page {idx}: {e}")
        return result

    async def _describe_charts_via_vision(self, file_path: str, page_indices: List[int]) -> Dict[int, str]:
        from src.core.llm_client import call_llm_vision
        from src.config import settings

        vision_model = getattr(settings.llm, 'vision_model', None)
        if not vision_model:
            logger.info("No vision_model configured, skipping chart description")
            return {}

        api_key = getattr(settings.llm, 'vision_api_key', None) or settings.llm.api_key
        base_url = getattr(settings.llm, 'vision_base_url', None) or settings.llm.base_url

        result = {}
        for idx in page_indices:
            try:
                img_b64 = self._render_page_to_base64(file_path, idx)
                if not img_b64:
                    continue
                resp = await call_llm_vision(
                    prompt="请分析此页面中的图表，提供：1）图表标题 2）图表类型（柱状图/折线图/饼图/散点图等）3）关键数据点和趋势 4）核心结论。用结构化文本输出。",
                    images=[img_b64],
                    model=vision_model,
                    api_key=api_key,
                    base_url=base_url,
                    max_tokens=1000,
                    temperature=0.2,
                )
                if resp.get("success"):
                    result[idx] = resp["content"]
                else:
                    logger.warning(f"Vision chart description failed for page {idx}: {resp.get('message', '')}")
            except Exception as e:
                logger.warning(f"Vision chart description error on page {idx}: {e}")
        return result

    def _render_page_to_base64(self, file_path: str, page_index: int) -> Optional[str]:
        try:
            import pdfplumber
            from PIL import Image
            import io
            import base64

            with pdfplumber.open(file_path) as pdf:
                if page_index >= len(pdf.pages):
                    return None
                page = pdf.pages[page_index]
                img = page.to_image(resolution=200)
                buf = io.BytesIO()
                img.original.save(buf, format="PNG", optimize=True)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Page render failed for {file_path} page {page_index}: {e}")
            return None

    def search_sections(self, parse_data: dict, keywords: list) -> list:
        results = []
        for section in parse_data.get("sections", []):
            content = section.get("content", "")
            for kw in keywords:
                if kw in content or kw in section.get("title", ""):
                    results.append(section)
                    break
        return results

    def find_line_items(self, parse_data: dict, metric_keywords: list) -> list:
        results = []
        for table_type, rows in parse_data.get("financial_tables", {}).items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                subject = row.get("科目", "")
                for kw in metric_keywords:
                    if kw in subject:
                        results.append({"table_type": table_type, "row": row})
                        break
        return results

    def extract_for_hypothesis(self, parse_data: dict, hypothesis: str, data_needs: list) -> dict:
        sections = self.search_sections(parse_data, data_needs)
        line_items = self.find_line_items(parse_data, data_needs)
        return {
            "hypothesis": hypothesis,
            "relevant_sections": sections,
            "relevant_line_items": line_items,
            "section_count": len(sections),
            "line_item_count": len(line_items),
        }

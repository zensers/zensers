# -*- coding: utf-8 -*-
"""
Chart Planner Agent
===================

Plans professional chart schemes from section content via LLM semantic analysis.
Core innovation: when content has insights but lacks data, agent proactively
fetches structured data (via skill/MCP/search), composes and normalizes it,
then generates charts — making reports truly professional.

Decides: "whether to chart", "what chart type", "where to insert",
         "what data is needed", "how to get it", "how to normalize it".
Does NOT handle rendering (delegated to ChartGenerator).
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.services.chart_generator import ChartType

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    headers: List[str]
    rows: List[List[str]]
    numeric_columns: List[int]
    raw_text: str
    topic_relevance: str = "unknown"


@dataclass
class DataRequest:
    source: str
    params: Dict[str, Any]
    purpose: str


@dataclass
class ChartPlan:
    chart_type: ChartType
    title: str
    subtitle: str
    data: Dict[str, Any]
    caption: str
    xlabel: str
    ylabel: str
    confidence: float
    reason: str
    insertion_anchor: str
    anchor_type: str
    unit: str
    data_source: str = "content"


_CHART_TYPE_MAP = {ct.value: ct for ct in ChartType}

_EXTENDED_CHART_TYPE_MAP = {
    "area": ChartType.LINE,
    "heatmap": ChartType.BAR,
    "donut": ChartType.PIE,
    "stacked_bar": ChartType.BAR,
    "grouped_bar": ChartType.BAR,
    "multi_line": ChartType.LINE,
}

_CHART_TYPE_SELECTION_RULES = """
| 数据特征 | 推荐图表类型 | 条件 | data格式 |
|----------|-------------|------|---------|
| 不同类别的数值对比 | bar | 类别数 <= 12，量纲一致 | categories+values |
| 排名/排行对比 | hbar | 适合展示排名，按值排序 | categories+values |
| 时间序列趋势 | line | 有序时间序列，>=2个时间点 | years+scenarios |
| 构成/占比分布 | pie | 类别数 <= 6，值非负 | labels+values |
| 多维度评估 | radar | 维度数 3-8，值自动归一化到0-100 | categories+values |
| 增减拆解 | waterfall | 有正有负的累计变化 | factors[].label+value+is_total |
| 绝对值+变化率同图 | bar_line | 双Y轴：绝对值(柱)+速率(线) | years+bar+line+bar_label+line_label |
| 多组对比 | bar (分组series) | 2-3组系列，量纲一致 | categories+series[].name+values |
| 多实体走势对比 | line (多scenarios) | 归一化后同图对比 | years+scenarios |
| 相关性分布 | scatter | 两个连续变量的关系 | x+y+labels |
| 规模-位置关系 | bubble | 三维数据(x/y/size) | sectors[].x+y+size+name |
| 竞争格局 | quadrant | 四象限定位 | players[].x+y+size+name |
"""

_ANCHOR_TYPE_RULES = """
| 场景 | anchor_type | insertion_anchor |
|------|-------------|-----------------|
| 图表是对某段分析的可视化 | after_paragraph | 该段的关键短语(10-20字) |
| 图表是对表格数据的可视化 | after_table | 表格的caption或标题关键词 |
| 图表是章节总览/概要 | section_start | 章节标题 |
| 图表是章节总结 | section_end | 章节标题 |
"""

_DATA_SOURCES = """
## 可用数据源

你可以通过 data_requests 声明需要的数据，系统会自动获取并填入图表。

| source | 说明 | params示例 |
|--------|------|-----------|
| stock_price | A股个股历史行情 | {{"symbol": "002594", "days": 120}} |
| index_price | A股指数历史行情 | {{"symbol": "000300", "days": 120}} |
| stock_financials | 个股财务报表 | {{"symbol": "002594", "periods": 4}} |
| stock_metrics | 个股关键指标 | {{"symbol": "002594"}} |
| search | 网络搜索补充数据 | {{"query": "比亚迪2025年销量"}} |

### symbol对照表（常见）
- 比亚迪: 002594
- 特斯拉: TSLA (美股)
- 沪深300: 000300
- 上证指数: 000001
- 创业板指: 399006
- 中证500: 000905

### 数据组合策略 (data_strategy)
当 data_requests 返回多组数据时，需要指定组合策略：

| strategy | 说明 | 适用场景 |
|----------|------|---------|
| raw | 原始值直接使用 | 同量纲数据 |
| normalize_pct | 归一化为首日=100的百分比 | 股价/指数走势对比 |
| pct_change | 转为涨跌幅(%) | 增速对比 |
| align_and_merge | 对齐时间轴后合并 | 多实体时间序列 |
"""

_JSON_SCHEMA = """
{{
    "data_requests": [
        {{
            "id": "req1",
            "source": "stock_price",
            "params": {{"symbol": "002594", "days": 120}},
            "purpose": "比亚迪近120日股价走势"
        }}
    ],
    "charts": [
        {{
            "chart_type": "bar",
            "title": "具体语义标题，传达分析洞察",
            "subtitle": "数据来源说明",
            "data_strategy": "raw",
            "data_ref": [],
            "data": {{
                "categories": ["类别A", "类别B", "类别C"],
                "values": [10, 20, 15]
            }},
            "caption": "图注",
            "xlabel": "X轴",
            "ylabel": "Y轴（含单位）",
            "confidence": 0.9,
            "reason": "理由",
            "insertion_anchor": "正文关键短语",
            "anchor_type": "after_paragraph",
            "unit": ""
        }}
    ],
    "skip_reason": null
}}

=== 各图表类型的 data 格式 ===

bar (单系列):
  {{"categories": ["A","B","C"], "values": [10,20,15]}}

bar (分组):
  {{"categories": ["Q1","Q2","Q3"], "series": [{{"name":"比亚迪","values":[100,120,130]}}, {{"name":"宁德时代","values":[200,210,220]}}]}}

hbar:
  {{"categories": ["公司A","公司B","公司C"], "values": [500,350,200]}}

line:
  {{"years": ["2023Q1","2023Q2","2023Q3"], "scenarios": {{"比亚迪": [100,120,130], "沪深300": [100,105,110]}}}}

pie:
  {{"labels": ["比亚迪","宁德时代","其他"], "values": [35, 20, 45]}}

radar:
  {{"categories": ["营收规模","盈利能力","技术实力","市场地位"], "values": [85, 72, 90, 88]}}

waterfall:
  {{"factors": [{{"label":"上期利润","value":300,"is_total":true}}, {{"label":"营收增长","value":150}}, {{"label":"成本上升","value":-80}}, {{"label":"本期利润","value":370,"is_total":true}}]}}

bar_line:
  {{"years": ["2021","2022","2023","2024"], "bar": [1502,4215,5022,6038], "line": [null,180.4,19.1,20.3], "bar_label": "营业收入(亿元)", "line_label": "同比增速(%)"}}

scatter:
  {{"x": [10,20,30], "y": [5,15,25], "labels": ["A","B","C"]}}

bubble:
  {{"sectors": [{{"name":"新能源","x":5,"y":8,"size":3}}, {{"name":"半导体","x":7,"y":6,"size":2}}]}}

quadrant:
  {{"players": [{{"name":"比亚迪","x":8,"y":9,"size":5}}, {{"name":"特斯拉","x":7,"y":7,"size":4}}]}}
"""

_SYSTEM_PROMPT = f"""你是一个专业的数据可视化规划师，同时也是一个数据分析agent。

你的核心任务是：**深入理解报告的思想和洞察，设计最能支撑这些洞察的专业图表。**

## 核心原则

1. **洞察驱动**：图表必须支撑报告中的分析结论。如果文中说"比亚迪股价走势弱于大盘"，就要生成股价vs大盘的对比图——即使文中没有提供这些数据。
2. **主动补数据**：当文中只有结论没有数据时，通过 data_requests 声明需要的数据，系统会自动获取。这是你最重要的能力。
3. **宁缺毋滥**：每章节最多2张图表。不要为了画图而画图。
4. **语义优先**：图表标题必须传达具体洞察，如"比亚迪股价跑输沪深300达25个百分点"，而非"股价对比"。
5. **量纲一致**：同一图表中的数值必须量纲统一。不同量级的数据必须归一化(data_strategy)。
6. **类型匹配**：根据数据特征选择图表类型，而非一律柱状图。

## 图表类型选择规则

{_CHART_TYPE_SELECTION_RULES}

## 插入位置规则

{_ANCHOR_TYPE_RULES}

{_DATA_SOURCES}

## 输出格式

严格输出JSON，不要输出其他内容：
{_JSON_SCHEMA}

当无法生成有效图表时：
{{"data_requests": [], "charts": [], "skip_reason": "原因说明"}}

## 关键：data_requests 的使用时机

**只要文中出现了以下类型的论断，就应该生成 data_requests：**

- "X公司股价走势..." → stock_price + index_price
- "X跑输/跑赢大盘" → stock_price + index_price, data_strategy=normalize_pct
- "X vs Y 市值对比" → stock_price(symbol=X) + stock_price(symbol=Y)
- "X利润增速高于Y" → stock_financials(symbol=X) + stock_financials(symbol=Y)
- "X行业份额..." → 如果文中无数据，search补充
- 任何涉及**时间序列对比**的论断 → 对应的price/financials数据

**如果文中已有完整表格数据，不需要 data_requests，直接用 data 字段填入。**

## data_ref 关联规则

每个 chart 必须通过 data_ref 字段声明它需要哪些 data_requests 的数据。

示例：如果要画"比亚迪 vs 沪深300 走势对比"，需要两个 data_requests：
- req1: stock_price(比亚迪)
- req2: index_price(沪深300)
然后在 chart 中设置 data_ref: ["req1", "req2"]

如果 chart 使用文中已有的表格数据（不需要 data_requests），则 data_ref 为空数组 []。

## 图表 data 格式规范

你必须严格按照以下格式填充 data 字段。格式错误会导致图表生成失败。

### bar / hbar
- 单系列：{{"categories": [...], "values": [...]}}
- 分组：{{"categories": [...], "series": [{{"name": "系列名", "values": [...]}}]}}
- categories 和 values 长度必须一致

### line
- {{"years": [...], "scenarios": {{"系列名": [值1, 值2, ...]}}}}
- 每个 scenario 的值数量必须等于 years 长度

### pie
- {{"labels": [...], "values": [...]}}
- 值必须非负，类别数 <= 6

### radar
- {{"categories": [...], "values": [...]}}
- 如果原始值不在0-100范围，系统会自动归一化

### waterfall
- {{"factors": [{{"label": "项目名", "value": 数值, "is_total": true/false}}]}}
- is_total=true 表示累计汇总行（如"上期利润"、"本期利润"）

### bar_line（营收+增速等双Y轴场景）
- {{"years": [...], "bar": [绝对值...], "line": [速率值...], "bar_label": "柱形标签", "line_label": "折线标签"}}
- line 第一个值可为 null（首期无同比）
- 当 data_requests 包含 stock_financials 时，优先考虑 bar_line

### scatter / bubble / quadrant
- 这些图表需要自定义数据，直接在 data 中填入完整数据
- scatter: {{"x": [...], "y": [...], "labels": [...]}}
- bubble: {{"sectors": [{{"name": ..., "x": ..., "y": ..., "size": ...}}]}}
- quadrant: {{"players": [{{"name": ..., "x": ..., "y": ..., "size": ...}}]}}"""


class ChartPlannerAgent:

    def __init__(self, output_dir: str = "output/charts", search_gateway=None):
        self.output_dir = output_dir
        # Production report generation injects the task-scoped gateway.  Keep
        # the optional argument for legacy callers that use this service in
        # isolation.
        self.search_gateway = search_gateway

    async def plan(
        self,
        content: str,
        topic: str,
        section_title: str,
    ) -> List[ChartPlan]:
        tables = self._extract_tables(content)
        filtered = self._prefilter_tables(tables, topic, section_title)

        plans = await self._llm_plan(content, filtered, topic, section_title)

        validated = self._validate_plans(plans)

        logger.info(
            f"ChartPlanner: section='{section_title}', "
            f"tables_found={len(tables)}, "
            f"tables_after_filter={len(filtered)}, "
            f"plans_generated={len(plans)}, "
            f"plans_after_validation={len(validated)}"
        )

        return validated

    def _extract_chinese_keywords(self, text: str) -> set:
        segments = re.findall(r"[\u4e00-\u9fff]+", text)
        keywords = set()
        for seg in segments:
            for n in range(2, min(len(seg) + 1, 5)):
                for i in range(len(seg) - n + 1):
                    keywords.add(seg[i : i + n])
        return keywords

    def _extract_tables(self, content: str) -> List[ExtractedTable]:
        content_normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        table_pattern = r"\|(.+)\|\n\|[-\s|:]+\|\n((?:\|.+\|\n?)+)"
        raw_tables = re.findall(table_pattern, content_normalized)

        results = []
        for header_row, data_rows in raw_tables:
            headers = [h.strip() for h in header_row.split("|") if h.strip()]
            rows = []
            for row in data_rows.strip().split("\n"):
                cells = [c.strip() for c in row.split("|") if c.strip()]
                if cells and not all(
                    c.replace("-", "").replace(":", "") == "" for c in cells
                ):
                    rows.append(cells)

            if not headers or not rows:
                continue

            numeric_cols = []
            for col_idx in range(len(headers)):
                numeric_count = 0
                for row in rows:
                    if col_idx < len(row):
                        cleaned = re.sub(r"[^\d.\-]", "", row[col_idx])
                        if cleaned and cleaned not in ("-", ".", "-."):
                            try:
                                float(cleaned)
                                numeric_count += 1
                            except ValueError:
                                pass
                if numeric_count >= max(1, len(rows) * 0.3):
                    numeric_cols.append(col_idx)

            raw_text = f"|{'|'.join(headers)}|\n"
            for row in rows:
                raw_text += f"|{'|'.join(row)}|\n"

            results.append(
                ExtractedTable(
                    headers=headers,
                    rows=rows,
                    numeric_columns=numeric_cols,
                    raw_text=raw_text,
                )
            )

        return results

    def _prefilter_tables(
        self,
        tables: List[ExtractedTable],
        topic: str,
        section_title: str,
    ) -> List[ExtractedTable]:
        results = []
        for table in tables:
            if len(table.rows) < 2:
                continue

            numeric_cols = len(table.numeric_columns)
            total_cols = len(table.headers)
            if total_cols == 0 or numeric_cols / total_cols < 0.3:
                continue

            has_valid_values = False
            for col_idx in table.numeric_columns:
                values = self._extract_numeric_values(table, col_idx)
                if any(v != 0 for v in values):
                    has_valid_values = True
                    break
            if not has_valid_values:
                continue

            table_keywords = set()
            for h in table.headers:
                table_keywords.update(self._extract_chinese_keywords(h))
            for row in table.rows[:2]:
                for cell in row:
                    table_keywords.update(self._extract_chinese_keywords(cell))

            topic_keywords = self._extract_chinese_keywords(topic + section_title)
            overlap = len(table_keywords & topic_keywords)

            table.topic_relevance = (
                "high"
                if overlap >= 2
                else "low"
                if overlap == 0
                else "medium"
            )

            if table.topic_relevance == "low":
                continue

            results.append(table)

        return results

    def _extract_numeric_values(
        self, table: ExtractedTable, col_idx: int
    ) -> List[float]:
        values = []
        for row in table.rows:
            if col_idx < len(row):
                cleaned = re.sub(r"[^\d.\-]", "", row[col_idx])
                if cleaned and cleaned not in ("-", ".", "-."):
                    try:
                        values.append(float(cleaned))
                    except ValueError:
                        values.append(0.0)
                else:
                    values.append(0.0)
            else:
                values.append(0.0)
        return values

    def _prepare_llm_input(
        self, content: str, tables: List[ExtractedTable]
    ) -> Tuple[str, str]:
        numeric_sentences = []
        for line in content.split("\n"):
            if re.search(r"\d+\.?\d*[万亿%％]?", line):
                numeric_sentences.append(line.strip())

        paragraph_first_sentences = []
        prev_empty = True
        for line in content.split("\n"):
            if line.strip() and prev_empty:
                first_sentence = re.split(r"[。！？；]", line.strip())[0]
                if len(first_sentence) > 5:
                    paragraph_first_sentences.append(first_sentence[:50])
            prev_empty = not line.strip()

        if len(content) <= 2000:
            content_summary = content
        else:
            head = content[:1500]
            tail = content[-500:]
            content_summary = head + "\n\n[...中间省略...]\n\n" + tail
        if numeric_sentences:
            content_summary += (
                "\n\n关键数据句：\n" + "\n".join(numeric_sentences[:20])
            )
        if paragraph_first_sentences:
            content_summary += (
                "\n\n段落首句（可选锚点位置）：\n"
                + "\n".join(paragraph_first_sentences[:30])
            )

        tables_json = json.dumps(
            [
                {
                    "headers": t.headers,
                    "rows": t.rows,
                    "topic_relevance": t.topic_relevance,
                }
                for t in tables
            ],
            ensure_ascii=False,
            indent=2,
        )

        return content_summary, tables_json

    async def _llm_plan(
        self,
        content: str,
        filtered: List[ExtractedTable],
        topic: str,
        section_title: str,
    ) -> List[ChartPlan]:
        try:
            from src.core.llm_client import call_llm
            from src.config.llm_profiles import RoutingHint
        except ImportError:
            logger.warning("ChartPlanner: call_llm not available, skipping LLM")
            return []

        content_summary, tables_json = self._prepare_llm_input(content, filtered)

        user_prompt = (
            f"## 研究主题\n{topic}\n\n"
            f"## 当前章节\n{section_title}\n\n"
            f"## 章节内容\n{content_summary}\n\n"
            f"## 可用表格数据\n{tables_json}\n\n"
            f"---\n\n"
            f"请深入分析上述内容，规划图表方案。关键要求：\n\n"
            f"1. **洞察驱动**：识别文中的分析论断，设计支撑这些论断的图表\n"
            f"2. **主动补数据**：如果文中只有结论没有数据（如'股价走势弱于大盘'），"
            f"通过data_requests声明需要的数据\n"
            f"3. 只使用与\"{topic}\"主题相关的数据\n"
            f"4. 每张图表的标题必须传达具体的分析洞察\n"
            f"5. 量纲不一致的数据必须用data_strategy归一化\n"
            f"6. 图表的insertion_anchor应选择正文中实际存在的关键短语\n"
            f"7. **先输出 JSON，后写说明**：首先输出完整 JSON（```json ... ```），"
            f"推理过程写在 JSON 之后。输出预算有限时优先保证 JSON 完整。"
        )

        result = await call_llm(
            prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=self._get_llm_max_tokens(),
            temperature=0.3,
            routing_hint=RoutingHint(
                agent_type="generic", action="chart_planning"
            ),
        )

        if not result.get("success"):
            logger.warning(
                f"ChartPlanner LLM call failed: {result.get('error')}"
            )
            return []

        content = result.get("content", "")
        if not str(content).strip():
            logger.warning(
                "ChartPlanner: empty LLM response for section='%s'; retrying compact plan",
                section_title,
            )
            result = await call_llm(
                prompt=user_prompt + "\nReturn compact JSON only. If no chart is justified, return {\"charts\": [], \"skip_reason\": \"insufficient evidence\"}.",
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=self._get_llm_max_tokens(),
                temperature=0,
                routing_hint=RoutingHint(agent_type="generic", action="chart_planning"),
            )
            if not result.get("success"):
                logger.warning("ChartPlanner retry failed: %s", result.get("error"))
                return []
            content = result.get("content", "")
            if not str(content).strip():
                logger.warning("ChartPlanner: retry also returned empty response")
                return []
        logger.debug(
            "ChartPlanner: LLM response received section='%s' chars=%d",
            section_title,
            len(content),
        )
        return await self._parse_and_resolve(content, topic)

    @staticmethod
    def _get_llm_max_tokens() -> int:
        """Return the chart-planning output budget without imposing a runtime limit."""
        try:
            from src.config import settings
            value = int(getattr(settings.chart_planner, "llm_max_tokens", 4096))
        except (ImportError, TypeError, ValueError, AttributeError):
            value = 4096
        return max(2048, value)

    def _clean_json_string(self, json_str: str) -> str:
        lines = []
        for line in json_str.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        return cleaned

    @staticmethod
    def _repair_truncated_json(json_str: str) -> Optional[Any]:
        """Progressively close open scopes of a truncated planner reply."""
        decoder = json.JSONDecoder()
        for end in range(len(json_str), 0, -1):
            prefix = json_str[:end].rstrip()
            if len(prefix) < len(json_str) - 512:
                break
            closers: List[str] = []
            in_string = False
            escaped = False
            stack: List[str] = []
            for ch in prefix:
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                elif ch == '"':
                    in_string = True
                elif ch in "{[":
                    stack.append(ch)
                elif ch in "}]":
                    if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                        stack.pop()
            if in_string:
                closers.append('"')
            for opener in reversed(stack):
                closers.append("}" if opener == "{" else "]")
            try:
                return json.loads(prefix + "".join(closers))
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    async def _parse_and_resolve(
        self, llm_content: str, topic: str
    ) -> List[ChartPlan]:
        json_str = llm_content.strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", json_str, re.DOTALL)
        if fence_match:
            json_str = fence_match.group(1).strip()

        json_str = self._clean_json_string(json_str)

        parsed = None
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            brace_start = json_str.find("{")
            brace_end = json_str.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                try:
                    parsed = json.loads(json_str[brace_start : brace_end + 1])
                except json.JSONDecodeError:
                    parsed = self._repair_truncated_json(json_str[brace_start:])
            else:
                parsed = self._repair_truncated_json(json_str)
        if parsed is None:
            logger.warning(
                "ChartPlanner: failed to parse LLM JSON response "
                "chars=%d likely_truncated=%s tail=%r",
                len(json_str),
                not json_str.rstrip().endswith(("}", "]", "```")),
                json_str[-120:],
            )
            return []

        if not isinstance(parsed, dict):
            return []

        data_requests_raw = parsed.get("data_requests", [])
        charts_raw = parsed.get("charts", [])

        skip_reason = parsed.get("skip_reason")
        if skip_reason and not charts_raw:
            logger.info(f"ChartPlanner: LLM skipped charts - {skip_reason}")
            return []

        fetched_data = {}
        if data_requests_raw and isinstance(data_requests_raw, list):
            fetched_data = await self._fetch_data(data_requests_raw, topic)

        plans = []
        for chart_raw in charts_raw:
            if not isinstance(chart_raw, dict):
                continue
            plan = await self._resolve_chart(chart_raw, fetched_data)
            if plan:
                plans.append(plan)

        return plans

    async def _fetch_data(
        self, requests_raw: List[Dict], topic: str
    ) -> Dict[str, Any]:
        self._current_topic = topic

        async def _fetch_one(req: Dict) -> Optional[Tuple[str, Dict]]:
            if not isinstance(req, dict):
                return None
            source = req.get("source", "")
            params = req.get("params", {})
            purpose = req.get("purpose", "")
            req_id = req.get("id", "")
            key = f"{source}:{json.dumps(params, sort_keys=True)}"

            try:
                if source in ("stock_price", "index_price", "stock_financials", "stock_metrics"):
                    data = await self._fetch_stock_data(source, params)
                elif source == "search":
                    data = await self._fetch_search_data(params, topic)
                else:
                    logger.warning(f"ChartPlanner: unknown data source '{source}'")
                    return None

                if data:
                    return key, {
                        "id": req_id,
                        "source": source,
                        "params": params,
                        "purpose": purpose,
                        "data": data,
                    }
            except Exception:
                logger.exception(f"ChartPlanner: data fetch failed for {source}")
            return None

        tasks = [_fetch_one(req) for req in requests_raw]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        failed_count = 0
        for r in results_list:
            if isinstance(r, Exception):
                failed_count += 1
                continue
            if r is not None:
                key, info = r
                results[key] = info
            else:
                failed_count += 1

        if failed_count == len(requests_raw) and requests_raw:
            logger.warning(f"ChartPlanner: all {len(requests_raw)} data requests failed")

        return results

    def _format_index_symbol(self, symbol: str) -> str:
        symbol = symbol.strip()
        if symbol.startswith("sh") or symbol.startswith("sz"):
            return symbol
        if symbol.startswith("399"):
            return f"sz{symbol}"
        return f"sh{symbol}"

    def _sanitize_params(self, source: str, params: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(params)
        sanitized["symbol"] = str(sanitized.get("symbol", "")).strip()
        max_days = 365
        try:
            from src.config import settings
            max_days = getattr(settings.chart_planner, 'max_data_days', 365)
        except Exception:
            pass
        if "days" in sanitized:
            try:
                days = int(sanitized["days"])
                sanitized["days"] = max(1, min(days, max_days))
            except (ValueError, TypeError):
                sanitized["days"] = 120
        if "periods" in sanitized:
            try:
                periods = int(sanitized["periods"])
                sanitized["periods"] = max(1, min(periods, 8))
            except (ValueError, TypeError):
                sanitized["periods"] = 4
        return sanitized

    def _is_a_share_symbol(self, symbol: str) -> bool:
        symbol = symbol.strip()
        if not symbol:
            return False
        if symbol.isdigit() and len(symbol) == 6:
            return True
        return False

    async def _fetch_stock_data(
        self, source: str, params: Dict[str, Any]
    ) -> Optional[Any]:
        params = self._sanitize_params(source, params)
        symbol = str(params.get("symbol", ""))
        if not symbol:
            return None

        # LLM plans naturally use company names/aliases, while AkShare's
        # A-share endpoints require a six-digit security code.  Canonicalize
        # through the shared entity resolver before deciding to fall back to
        # web search; otherwise a valid listed company is misclassified as a
        # non-A-share symbol and structured data is never attempted.
        if source in ("stock_price", "stock_financials", "stock_metrics"):
            resolved = await self._canonicalize_stock_symbol(symbol)
            if resolved:
                symbol = resolved
                params["symbol"] = resolved

        if source in ("stock_price", "stock_financials", "stock_metrics"):
            if not self._is_a_share_symbol(symbol):
                logger.info(f"Symbol '{symbol}' is not A-share, falling back to search")
                return await self._fetch_search_data(
                    {"query": f"{symbol} 股价走势" if source == "stock_price" else f"{symbol} 财务数据"},
                    getattr(self, '_current_topic', ''),
                )

        max_retries = 2
        try:
            from src.config import settings
            max_retries = getattr(settings.chart_planner, 'max_data_retries', 2)
        except Exception:
            pass

        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    self._fetch_stock_data_impl(source, params, symbol),
                    timeout=30,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(f"Stock data fetch timeout (attempt {attempt+1}/{max_retries}): {source}/{symbol}")
            except Exception:
                logger.exception(f"Stock data fetch failed (attempt {attempt+1}/{max_retries}): {source}/{symbol}")

        return None

    async def _canonicalize_stock_symbol(self, symbol: str) -> str:
        """Resolve a company name/alias to the canonical A-share code."""
        symbol = str(symbol or "").strip()
        if self._is_a_share_symbol(symbol):
            return symbol
        try:
            from src.core.entity_resolver import get_entity_resolver

            entities = await get_entity_resolver().resolve(symbol)
            for entity in entities:
                code = getattr(entity, "resolved_code", None)
                if code and self._is_a_share_symbol(str(code)):
                    logger.info(
                        "ChartPlanner: canonicalized stock symbol '%s' -> '%s'",
                        symbol,
                        code,
                    )
                    return str(code)
        except Exception as exc:
            logger.debug(
                "ChartPlanner: stock symbol resolution failed for '%s': %s",
                symbol,
                exc,
            )
        return ""

    async def _fetch_stock_data_impl(
        self, source: str, params: Dict[str, Any], symbol: str
    ) -> Optional[Any]:
        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare not installed, cannot fetch stock data")
            return None

        try:
            if source == "stock_price":
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
                if df is not None and not df.empty:
                    days = int(params.get("days", 120))
                    records = df.tail(days).to_dict(orient="records")
                    return self._normalize_price_records(records)

            elif source == "index_price":
                formatted_symbol = self._format_index_symbol(symbol)
                df = ak.stock_zh_index_daily(symbol=formatted_symbol)
                if df is not None and not df.empty:
                    days = int(params.get("days", 120))
                    records = df.tail(days).to_dict(orient="records")
                    return self._normalize_price_records(records, is_index=True)

            elif source == "stock_financials":
                periods = int(params.get("periods", 4))
                df = ak.stock_profit_sheet_by_report_em(symbol=symbol)
                if df is not None and not df.empty:
                    return df.head(periods).to_dict(orient="records")

            elif source == "stock_metrics":
                df = ak.stock_financial_analysis_indicator(symbol=symbol)
                if df is not None and not df.empty:
                    return df.head(8).to_dict(orient="records")

        except Exception:
            logger.exception(f"Stock data fetch impl failed: source={source}, symbol={symbol}")

        return None

    def _normalize_price_records(
        self, records: List[Dict], is_index: bool = False
    ) -> Dict[str, Any]:
        date_close_map = {}
        for r in records:
            date_val = str(r.get("日期", r.get("date", "")))[-10:]
            close_val = r.get("收盘", r.get("close", 0))
            try:
                close_val = float(close_val)
            except (ValueError, TypeError):
                continue
            if date_val:
                date_close_map[date_val] = close_val

        sorted_items = sorted(date_close_map.items(), key=lambda x: x[0])
        dates = [d for d, _ in sorted_items]
        closes = [c for _, c in sorted_items]

        return {"dates": dates, "closes": closes}

    async def _fetch_search_data(
        self, params: Dict[str, Any], topic: str
    ) -> Optional[Any]:
        query = params.get("query", "")
        if not query:
            return None

        # Search-backed chart data must come from the search Skill first.
        # Previously this method sent only the query to an LLM, which is not
        # retrieval and made the result unverifiable (especially for company
        # abbreviations and fuzzy names).
        try:
            if self.search_gateway is not None:
                from src.core.search import SearchRequest

                gateway_response = await asyncio.wait_for(
                    self.search_gateway.search(
                        SearchRequest(
                            query=query,
                            objective="chart_data",
                            region="cn-cn",
                            max_results=5,
                        ),
                        scope="report_generation",
                    ),
                    timeout=120,
                )
                search_result = {
                    "success": bool(gateway_response.success),
                    "results": [
                        {
                            "title": item.title,
                            "snippet": item.snippet or item.excerpt,
                            "content": item.excerpt or item.snippet,
                            "url": item.url,
                            "source": item.source,
                            "evidence_id": item.evidence_id,
                            "provenance_id": item.provenance_id,
                        }
                        for item in (gateway_response.results or [])
                    ],
                }
            else:
                from src.skills.search_skill import MultiSearchSkill

                search_result = await asyncio.wait_for(
                    MultiSearchSkill().execute(
                        query=query,
                        max_results=5,
                        context={"topic": topic, "purpose": "chart_data"},
                    ),
                    timeout=120,
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("ChartPlanner: search timed out for '%s'; skipping fetch", query)
            return None
        except Exception as exc:
            logger.warning("ChartPlanner: search provider failed for '%s': %s", query, exc)
            return None

        if not isinstance(search_result, dict) or not search_result.get("success"):
            logger.warning("ChartPlanner: search skill returned no evidence for '%s'", query)
            return None
        search_results = search_result.get("results")
        if search_results is None and isinstance(search_result.get("data"), dict):
            search_results = search_result["data"].get("results")
        if not isinstance(search_results, list) or not search_results:
            logger.warning("ChartPlanner: search skill returned empty evidence for '%s'", query)
            return None

        evidence = []
        for item in search_results[:5]:
            if isinstance(item, dict):
                evidence.append({
                    key: item.get(key, "")
                    for key in ("title", "snippet", "content", "url", "source")
                    if item.get(key)
                })
            elif item:
                evidence.append({"content": str(item)})
        if not evidence:
            return None

        try:
            from src.core.llm_client import call_llm
            from src.config.llm_profiles import RoutingHint
        except ImportError:
            return None

        result = await call_llm(
            prompt=(
                f"请仅根据下列搜索证据提取查询所需的具体数值，以JSON格式返回。\n"
                f"查询：{query}\n"
                f"搜索证据：{json.dumps(evidence, ensure_ascii=False)}\n\n"
                f"返回格式要求：\n"
                f'{{"dates": ["2025-01", "2025-02", ...], "values": [数值1, 数值2, ...], "unit": "单位"}}\n\n'
                f"注意：\n"
                f"1. dates 必须是具体时间点，不能是范围\n"
                f"2. values 必须是纯数字，不含文字\n"
                f'3. 如果无法获取准确数据，返回 {{"error": "原因说明"}}'
            ),
            system_prompt="你是精确数据提取助手。只返回可验证的数值数据，不猜测。如果数据不可获取，明确说明原因。",
            max_tokens=500,
            temperature=0.2,
            routing_hint=RoutingHint(agent_type="generic", action="data_search"),
        )

        if result.get("success"):
            try:
                content = result.get("content", "")
                brace_start = content.find("{")
                brace_end = content.rfind("}")
                if brace_start != -1 and brace_end > brace_start:
                    parsed = json.loads(content[brace_start:brace_end+1])
                    if "error" in parsed:
                        logger.warning(f"Search data unavailable: {parsed['error']}")
                        return None
                    if parsed.get("dates") and parsed.get("values"):
                        if len(parsed["dates"]) == len(parsed["values"]):
                            return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _filter_fetched_by_ref(
        self, fetched_data: Dict[str, Any], data_ref: List[str]
    ) -> Dict[str, Any]:
        if not data_ref:
            return fetched_data
        ref_set = set(data_ref)
        filtered = {}
        for key, info in fetched_data.items():
            req_id = info.get("id", "")
            if req_id in ref_set:
                filtered[key] = info
        if not filtered:
            for key, info in fetched_data.items():
                purpose = info.get("purpose", "")
                params = info.get("params", {})
                symbol = params.get("symbol", "")
                for ref_id in data_ref:
                    if ref_id in key or ref_id in purpose or ref_id == symbol:
                        filtered[key] = info
                        break
        return filtered if filtered else fetched_data

    async def _resolve_chart(
        self, chart_raw: Dict[str, Any], fetched_data: Dict[str, Any]
    ) -> Optional[ChartPlan]:
        chart_type_str = chart_raw.get("chart_type", "bar")
        chart_type = _CHART_TYPE_MAP.get(chart_type_str)
        if chart_type is None:
            chart_type = _EXTENDED_CHART_TYPE_MAP.get(chart_type_str, ChartType.BAR)
            logger.info(f"ChartPlanner: mapped unknown chart_type '{chart_type_str}' to {chart_type.value}")

        confidence = chart_raw.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.5

        data = chart_raw.get("data", {})
        data_strategy = chart_raw.get("data_strategy", "raw")
        data_ref = chart_raw.get("data_ref", [])

        if not data or not isinstance(data, dict):
            data = {}

        has_empty_data = self._has_empty_chart_data(data, chart_type)

        if has_empty_data and fetched_data:
            filtered_data = self._filter_fetched_by_ref(fetched_data, data_ref)
            data = self._compose_chart_data(
                chart_raw, filtered_data, data_strategy
            )

        if not data or self._has_empty_chart_data(data, chart_type):
            return None

        return ChartPlan(
            chart_type=chart_type,
            title=str(chart_raw.get("title", ""))[:100],
            subtitle=str(chart_raw.get("subtitle", ""))[:200],
            data=data,
            caption=str(chart_raw.get("caption", ""))[:200],
            xlabel=str(chart_raw.get("xlabel", ""))[:50],
            ylabel=str(chart_raw.get("ylabel", ""))[:50],
            confidence=max(0.0, min(1.0, confidence)),
            reason=str(chart_raw.get("reason", ""))[:300],
            insertion_anchor=str(chart_raw.get("insertion_anchor", ""))[:100],
            anchor_type=str(chart_raw.get("anchor_type", "section_end")),
            unit=str(chart_raw.get("unit", ""))[:20],
            data_source="fetched" if has_empty_data else "content",
        )

    def _has_empty_chart_data(self, data: Dict, chart_type: ChartType) -> bool:
        if not data:
            return True

        if chart_type == ChartType.LINE:
            scenarios = data.get("scenarios", {})
            if not scenarios:
                return True
            for vals in scenarios.values():
                if isinstance(vals, list) and len(vals) > 0:
                    return False
            return True

        if chart_type in (ChartType.BAR, ChartType.HBAR):
            categories = data.get("categories", data.get("labels", []))
            if "series" in data:
                series = data["series"]
                if not series:
                    return True
                return all(len(s.get("values", [])) == 0 for s in series)
            values = data.get("values", [])
            return len(values) == 0 or len(categories) == 0

        if chart_type == ChartType.PIE:
            labels = data.get("labels", data.get("categories", []))
            values = data.get("values", [])
            return len(values) == 0 or len(labels) == 0

        if chart_type == ChartType.BAR_LINE:
            years = data.get("years", [])
            bar = data.get("bar", [])
            line = data.get("line", [])
            return len(years) == 0 or len(bar) == 0 or len(line) == 0

        if chart_type == ChartType.RADAR:
            return len(data.get("values", [])) == 0 or len(data.get("categories", [])) == 0

        if chart_type == ChartType.WATERFALL:
            return len(data.get("factors", [])) == 0

        if chart_type == ChartType.SCATTER:
            return len(data.get("x", [])) == 0 or len(data.get("y", [])) == 0

        if chart_type == ChartType.BUBBLE:
            return len(data.get("sectors", [])) == 0

        if chart_type == ChartType.QUADRANT:
            return len(data.get("players", [])) == 0

        return len(data) == 0

    def _compose_chart_data(
        self,
        chart_raw: Dict[str, Any],
        fetched_data: Dict[str, Any],
        strategy: str,
    ) -> Dict[str, Any]:
        chart_type_str = chart_raw.get("chart_type", "line")
        chart_type = _CHART_TYPE_MAP.get(chart_type_str, ChartType.LINE)

        time_series_data = []
        categorical_data = []

        for key, info in fetched_data.items():
            payload = info.get("data", {})
            source = info.get("source", "")
            purpose = info.get("purpose", "")
            params = info.get("params", {})
            symbol = params.get("symbol", "")

            if source in ("stock_price", "index_price"):
                dates = payload.get("dates", [])
                closes = payload.get("closes", [])
                if not dates or not closes:
                    continue
                name = self._make_series_name(purpose, symbol, source)
                time_series_data.append({"name": name, "dates": dates, "values": closes})

            elif source == "stock_financials":
                records = payload if isinstance(payload, list) else []
                if not records:
                    continue
                periods = []
                revenue_vals = []
                for r in records:
                    period = r.get("报告期", r.get("REPORT_DATE", r.get("截止日期", "")))
                    rev = r.get("营业总收入", r.get("营业收入", r.get("TOTAL_OPERATE_INCOME", 0)))
                    if period:
                        periods.append(str(period)[:10])
                        try:
                            revenue_vals.append(float(rev))
                        except (ValueError, TypeError):
                            revenue_vals.append(0)
                if periods and revenue_vals:
                    name = self._make_series_name(purpose, symbol, "营收")
                    if chart_type in (ChartType.BAR, ChartType.HBAR, ChartType.PIE):
                        categorical_data.append({"name": name, "categories": periods, "values": revenue_vals})
                    else:
                        time_series_data.append({"name": name, "dates": periods, "values": revenue_vals})

            elif source == "stock_metrics":
                records = payload if isinstance(payload, list) else []
                if not records:
                    continue
                categories = []
                values = []
                skip_keys = {"股票代码", "股票简称", "日期", "report_date", "code", "name"}
                for r in records:
                    for k, v in r.items():
                        if k in skip_keys:
                            continue
                        try:
                            float_val = float(v)
                            categories.append(k[:15])
                            values.append(float_val)
                        except (ValueError, TypeError):
                            continue
                if categories and values:
                    name = self._make_series_name(purpose, symbol, "指标")
                    categorical_data.append({"name": name, "categories": categories, "values": values})

            elif source == "search":
                dates = payload.get("dates", [])
                values = payload.get("values", [])
                if dates and values:
                    name = self._make_series_name(purpose, "", "数据")
                    if chart_type in (ChartType.BAR, ChartType.HBAR) and len(dates) <= 12:
                        categorical_data.append({"name": name, "categories": dates, "values": values})
                    else:
                        time_series_data.append({"name": name, "dates": dates, "values": values})

        if chart_type == ChartType.RADAR:
            if categorical_data:
                result = self._compose_categorical(categorical_data, chart_type)
                if result and "values" in result:
                    result["values"] = self._normalize_radar_values(result["values"])
                return result
            return {}

        if chart_type == ChartType.BAR_LINE:
            return self._compose_bar_line(fetched_data, time_series_data, categorical_data)

        if categorical_data and chart_type in (ChartType.BAR, ChartType.HBAR, ChartType.PIE):
            return self._compose_categorical(categorical_data, chart_type)

        if time_series_data:
            return self._compose_time_series(time_series_data, strategy)

        if categorical_data:
            return self._compose_categorical(categorical_data, chart_type)

        return {}

    def _make_series_name(self, purpose: str, symbol: str, fallback: str) -> str:
        if purpose and len(purpose) <= 25:
            return purpose
        if symbol:
            return symbol
        return fallback

    def _compose_categorical(
        self, categorical_data: List[Dict], chart_type: ChartType
    ) -> Dict[str, Any]:
        if not categorical_data:
            return {}
        if len(categorical_data) == 1:
            cd = categorical_data[0]
            return {"categories": cd["categories"], "values": cd["values"]}
        all_categories = []
        seen = set()
        for cd in categorical_data:
            for c in cd["categories"]:
                if c not in seen:
                    all_categories.append(c)
                    seen.add(c)
        series_list = []
        for cd in categorical_data:
            cat_to_val = dict(zip(cd["categories"], cd["values"]))
            aligned_vals = [cat_to_val.get(c, None) for c in all_categories]
            series_list.append({"name": cd["name"], "values": aligned_vals})
        return {"categories": all_categories, "series": series_list}

    def _compose_bar_line(
        self,
        fetched_data: Dict[str, Any],
        time_series_data: List[Dict],
        categorical_data: List[Dict],
    ) -> Dict[str, Any]:
        financial_series = []
        for key, info in fetched_data.items():
            source = info.get("source", "")
            if source == "stock_financials":
                payload = info.get("data", {})
                purpose = info.get("purpose", "")
                params = info.get("params", {})
                symbol = params.get("symbol", "")
                extract = params.get("extract", "revenue")

                records = payload if isinstance(payload, list) else []
                if not records:
                    continue

                periods = []
                revenue_vals = []
                profit_vals = []
                for r in records:
                    period = r.get("报告期", r.get("REPORT_DATE", r.get("截止日期", "")))
                    if period:
                        periods.append(str(period)[:10])
                    else:
                        continue
                    rev = r.get("营业总收入", r.get("营业收入", r.get("TOTAL_OPERATE_INCOME", 0)))
                    np_ = r.get("净利润", r.get("NETPROFIT", r.get("归母净利润", 0)))
                    try:
                        revenue_vals.append(float(rev))
                    except (ValueError, TypeError):
                        revenue_vals.append(0)
                    try:
                        profit_vals.append(float(np_))
                    except (ValueError, TypeError):
                        profit_vals.append(0)

                if periods and revenue_vals:
                    financial_series.append({
                        "name": self._make_series_name(purpose, symbol, "营收"),
                        "periods": periods,
                        "revenue": revenue_vals,
                        "profit": profit_vals,
                        "extract": extract,
                    })

        if not financial_series:
            if time_series_data and len(time_series_data) == 1:
                td = time_series_data[0]
                vals = td["values"]
                bar_vals = vals
                line_vals = [None]
                for i in range(1, len(vals)):
                    if vals[i-1] != 0:
                        line_vals.append(round((vals[i] - vals[i-1]) / abs(vals[i-1]) * 100, 1))
                    else:
                        line_vals.append(0)
                return {
                    "years": td["dates"],
                    "bar": bar_vals,
                    "line": line_vals,
                    "bar_label": td["name"],
                    "line_label": "环比变化(%)",
                }
            return {}

        fs = financial_series[0]
        paired = sorted(zip(fs["periods"], fs["revenue"]), key=lambda x: x[0])
        periods = [p for p, _ in paired]
        revenue = [r for _, r in paired]

        line_vals = [None]
        for i in range(1, len(revenue)):
            if revenue[i-1] != 0:
                line_vals.append(round((revenue[i] - revenue[i-1]) / abs(revenue[i-1]) * 100, 1))
            else:
                line_vals.append(0)

        return {
            "years": periods,
            "bar": revenue,
            "line": line_vals,
            "bar_label": fs["name"],
            "line_label": "同比增速(%)",
        }

    def _normalize_radar_values(self, values: List[float]) -> List[float]:
        if not values:
            return values
        max_val = max(abs(v) for v in values)
        if max_val == 0:
            return values
        if max_val <= 100:
            return values
        return [round(v / max_val * 100, 1) for v in values]

    def _compose_time_series(
        self, time_series_data: List[Dict], strategy: str
    ) -> Dict[str, Any]:
        if not time_series_data:
            return {}
        aligned = self._align_time_series(time_series_data)
        if strategy == "normalize_pct":
            scenarios = {}
            for s in aligned:
                vals = s["values"]
                if vals and vals[0] != 0:
                    base = vals[0]
                    scenarios[s["name"]] = [round(v / base * 100, 2) for v in vals]
                else:
                    scenarios[s["name"]] = vals
            return {
                "years": aligned[0]["dates"] if aligned else [],
                "scenarios": scenarios,
                "unit": "%",
            }
        elif strategy == "pct_change":
            scenarios = {}
            for s in aligned:
                vals = s["values"]
                changes = []
                for i in range(1, len(vals)):
                    if vals[i-1] != 0:
                        changes.append(round((vals[i] - vals[i-1]) / abs(vals[i-1]) * 100, 2))
                    else:
                        changes.append(0)
                scenarios[s["name"]] = changes
            dates = aligned[0]["dates"][1:] if aligned else []
            return {
                "years": dates,
                "scenarios": scenarios,
                "unit": "%",
            }
        else:
            scenarios = {s["name"]: s["values"] for s in aligned}
            return {
                "years": aligned[0]["dates"] if aligned else [],
                "scenarios": scenarios,
            }

    def _align_time_series(
        self, series_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not series_data:
            return []

        all_dates = set()
        for s in series_data:
            all_dates.update(s["dates"])

        sorted_dates = sorted(all_dates)
        date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

        result = []
        for s in series_data:
            aligned_values = [None] * len(sorted_dates)
            for d, v in zip(s["dates"], s["values"]):
                if d in date_to_idx:
                    aligned_values[date_to_idx[d]] = v

            filled = []
            last_valid = None
            for v in aligned_values:
                if v is not None:
                    last_valid = v
                    filled.append(v)
                elif last_valid is not None:
                    filled.append(last_valid)
                else:
                    filled.append(0)

            result.append({"name": s["name"], "dates": sorted_dates, "values": filled})

        return result

    def _validate_plans(self, plans: List[ChartPlan]) -> List[ChartPlan]:
        try:
            from src.config import settings
            min_confidence = settings.chart_planner.min_confidence
            max_per_section = settings.chart_planner.max_per_section
        except Exception:
            min_confidence = 0.5
            max_per_section = 2

        validated = []
        for plan in plans:
            if plan.confidence < min_confidence:
                continue
            if not self._check_unit_consistency(plan):
                continue
            if not self._check_chart_type_match(plan):
                continue
            if not self._check_value_range(plan):
                continue
            validated.append(plan)

        validated.sort(key=lambda p: p.confidence, reverse=True)
        return validated[:max_per_section]

    def _check_unit_consistency(self, plan: ChartPlan) -> bool:
        data = plan.data
        if not data:
            return False

        if "series" in data:
            units = set()
            for s in data["series"]:
                u = s.get("unit", "")
                if u:
                    units.add(u)
            if len(units) > 1:
                return False

        if "factors" in data:
            units = set()
            for f in data["factors"]:
                u = f.get("unit", data.get("unit", ""))
                if u:
                    units.add(u)
            if len(units) > 1:
                return False

        return True

    def _check_chart_type_match(self, plan: ChartPlan) -> bool:
        data = plan.data
        if not data:
            return False

        if plan.chart_type == ChartType.PIE:
            values = data.get("values", [])
            if not all(isinstance(v, (int, float)) for v in values):
                return False
            if any(v < 0 for v in values):
                return False
            if len(values) > 6:
                return False

        if plan.chart_type == ChartType.LINE:
            years = data.get("years", [])
            if not years or len(years) < 2:
                return False
            scenarios = data.get("scenarios", {})
            for label, vals in scenarios.items():
                if isinstance(vals, list) and len(vals) != len(years):
                    return False

        if plan.chart_type == ChartType.RADAR:
            categories = data.get("categories", [])
            if not (3 <= len(categories) <= 8):
                return False
            values = data.get("values", [])
            if not values or not all(isinstance(v, (int, float)) for v in values):
                return False

        if plan.chart_type in (ChartType.BAR, ChartType.HBAR):
            categories = data.get("categories", data.get("labels", []))
            if len(categories) > 12:
                return False

        if plan.chart_type == ChartType.BAR_LINE:
            years = data.get("years", [])
            bar = data.get("bar", [])
            line = data.get("line", [])
            if not years or len(years) < 2:
                return False
            if len(bar) != len(years):
                return False
            if len(line) != len(years):
                return False

        if plan.chart_type == ChartType.WATERFALL:
            factors = data.get("factors", [])
            if len(factors) < 2:
                return False

        if plan.chart_type == ChartType.SCATTER:
            x = data.get("x", [])
            y = data.get("y", [])
            if len(x) < 2 or len(x) != len(y):
                return False

        return True

    def _check_value_range(self, plan: ChartPlan) -> bool:
        data = plan.data
        if not data:
            return False
        if plan.chart_type == ChartType.WATERFALL:
            return True
        if plan.unit == "%" and "scenarios" in data:
            scenarios = data["scenarios"]
            all_vals = []
            for vals in scenarios.values():
                if isinstance(vals, list):
                    all_vals.extend([v for v in vals if isinstance(v, (int, float))])
            if all_vals and max(abs(v) for v in all_vals) <= 500:
                return True
        all_values = []
        if "values" in data:
            for v in data["values"]:
                if isinstance(v, (int, float)):
                    all_values.append(v)
        if "series" in data:
            for s in data["series"]:
                for v in s.get("values", []):
                    if isinstance(v, (int, float)):
                        all_values.append(v)
        if "scenarios" in data:
            for vals in data["scenarios"].values():
                if isinstance(vals, list):
                    for v in vals:
                        if isinstance(v, (int, float)):
                            all_values.append(v)
        if "factors" in data:
            for f in data["factors"]:
                v = f.get("value", 0)
                if isinstance(v, (int, float)):
                    all_values.append(v)
        if not all_values:
            return True
        for v in all_values:
            if abs(v) > 1e13:
                return False
        non_zero = [abs(v) for v in all_values if v != 0]
        if len(non_zero) >= 2:
            max_val = max(non_zero)
            min_val = min(non_zero)
            if min_val > 0 and max_val / min_val > 1000:
                return False
        return True

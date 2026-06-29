# 报告生成Agent深度升级方案 v2：基于真实代码环境的框架驱动设计

> 日期：2026-06-26
> 状态：设计方案 v2（基于真实数据环境重写，所有接口对齐真实代码，经深度审计修复21个缺陷）
> 关联问题：报告质量失控——机械组装数据，缺乏研究框架驱动的逻辑连贯性
> 审计历史：v1经过两轮审计共发现20个缺陷；v2经逐行深度审计发现21个缺陷（5 CRITICAL / 8 HIGH / 8 MEDIUM），已全部修复；v2第三轮审计发现6个缺陷（2 HIGH / 4 MEDIUM），已全部修复；v2代码实现深度审计发现7个缺陷（1 CRITICAL / 3 HIGH / 3 MEDIUM），已全部修复

---

## 0. 真实代码环境映射

### 0.1 现有数据结构（不可修改，必须对接）

| 真实类 | 文件 | 关键字段 | 用途 |
|--------|------|----------|------|
| `SectionSpec` | `src/core/task_structure.py:56` | section_id, section_name, section_role(SectionRole枚举), content_dependency, can_parallel, priority | 任务结构中的章节定义 |
| `TaskStructure` | `src/core/task_structure.py:117` | task_id, topic, sections: List[SectionSpec], dependencies, parallel_groups, critical_path | 任务结构（由TaskStructureAnalyzer生成） |
| `AggregationResult` | `src/core/orchestrator/aggregation/result_aggregator.py:252` | data, conflicts, stats, section_details, sources, layered_content, content_provenance | 聚合结果 |
| `ContentProvenance` | `src/core/orchestrator/aggregation/result_aggregator.py:233` | source_key, stage, agent_type, section_target | 内容来源追踪（layered_content的元数据） |
| `ResearchFrameworkConfig` | `src/core/research_framework_manager.py:72` | name, description, agent_config, section_weights, interaction_parameters | 研究框架配置（**无to_dict()方法，需手动序列化**） |
| `ConflictRecord` | `src/core/orchestrator/aggregation/result_aggregator.py:204` | key, values, sources, resolution(ConflictResolution枚举), resolved_value | 聚合阶段的数据冲突 |
| `ConflictResolution` | `src/core/orchestrator/aggregation/result_aggregator.py:193` | Enum: KEEP_FIRST, KEEP_LAST, KEEP_HIGHEST_PRIORITY, MERGE, MANUAL, AUTO | 冲突解决策略枚举（**不可作为dataclass名复用**） |

### 0.2 真实LLM接口

```python
# src/skills/llm_skill.py:32
# 调用方式：
result = await llm_skill.execute(
    prompt="...",
    model="gpt-4o",
    system_prompt="...",
    max_tokens=4096,
    temperature=0.7,
)
# 返回值：
# {"success": bool, "content": str, "model": str, "usage": dict, "fallback_used": bool}
# 文本在 result["content"] 中
```

### 0.3 真实搜索/抓取接口

```python
# src/skills/search_skill.py:112 (MultiSearchSkill)
search_result = await search_skill.execute(
    query="...",
    max_results=10,
    region="cn",
)
# 返回：{"success": bool, "results": List[Dict], "query": str, "total": int, ...}
# results[i] = {"title": str, "href": str, "body": str, ...}
# 注意：URL字段名是 "href"（非"url"），摘要字段名是 "body"（非"snippet"）

# src/skills/web_scraper_skill.py:120 (WebScraperSkill)
scrape_result = await scraper_skill.execute(
    url="...",
    action="extract_markdown",  # or "extract_text", "extract_tables"
    timeout=30,
    max_chars=5000,
)
# 返回：{"success": bool, "text": str, "title": str, "url": str, "content_length": int}
```

### 0.4 真实数据格式（research_result_cache.json）

```json
{
  "topic": "测试主题",
  "title": "测试主题",
  "aspects": ["Market Size", "Competitive Landscape", "Development Trends"],
  "sections": [
    {
      "id": "phase_2_agent_1",
      "title": "Phase 2 Agent 1",
      "content": "### 核心判断：...（Markdown文本）",
      "subsections": [],
      "charts": [],
      "data_points": [],
      "sources": []
    }
  ],
  "sources": [
    {"title": "...", "url": "...", "type": "web", "agent_id": "phase_1_agent_1"}
  ]
}
```

### 0.5 真实编排器调用点（orchestrator.py:974-980）

```python
preview_result = await self._document_agent.execute({
    "action": "get_preview",
    "output_format": "html",
    "research_result": research_result_data,  # AggregationResult.to_dict() 的输出
    "task_id": task_id,
    "output_dir": str(output_dir_path),
})
```

### 0.6 关键对接约束

> **⚠️ `AggregationResult.to_dict()` 不序列化 `layered_content` 和 `content_provenance`**
>
> 真实代码（result_aggregator.py:282-309）的 `to_dict()` 只输出 `data`, `conflicts`, `stats`,
> `aggregated_at`, `sources`, `sections`, `key_findings`。`layered_content` 和
> `content_provenance` 两个属性虽然存在于 `AggregationResult` 对象上，但不在序列化输出中。
>
> **解决方案**：`generate_report()` 直接接收 `AggregationResult` **对象**（而非 `to_dict()` 的
> 输出字典），在 `_extract_chapter_data()` 中直接访问对象属性。这样既避免修改现有
> `to_dict()` 的接口，又能获取完整的分层数据。

> **⚠️ `ResearchFrameworkConfig` 无 `to_dict()` 方法**
>
> 需手动构建字典：`{"name": config.name, "description": config.description, ...}`

> **⚠️ `orchestrator.py` 中获取 Skill 的方式**
>
> Orchestrator 中没有 `_get_llm_skill()` 方法。获取方式：
> - LLM Skill：`self._skill_registry.get("llm_skill")`（返回 Skill 实例）
> - Search Skill：`self._skill_registry.get("search_skill")`（注意注册名是 `search_skill`，不是 `search`）
> - Web Scraper：`self._skill_registry.get("web_scraper")`
>
> 获取 FrameworkConfig 方式：`from src.core.research_framework_manager import get_framework_config`（模块级便捷函数，内部自动创建单例）

---

## 1. 问题诊断（保持v1，无变化）

> 同v1第1节，此处省略。核心问题：机械组装 → 数据矛盾、内容重复、逻辑断裂、摘要失真、质量不可控。

---

## 2. 新方案：框架驱动·逐章生成·全局审查

### 2.1 核心理念（保持v1）

```
旧模式：数据 → 机械组装 → 报告（排版工）
新模式：框架 → 逐章撰写（研究员）→ 逐章审查（资深研究员）→ 重写闭环 → 全局审查（总监）→ 报告
```

### 2.2 新流程

```
Phase 1: 框架理解
  └─ 从 TaskStructure 和 ResearchFrameworkConfig 构建叙事上下文

Phase 2: 逐章撰写 + 自审 + 独立审查（闭环迭代）
  ├─ Chapter 1: Writer撰写 + 实时自审 → ChapterReviewAgent独立审查 → 通过/重写
  ├─ Chapter 2: 同样流程
  └─ ...

Phase 3: 全局审查（两步审查：摘要审查 → 原文验证）

Phase 4: 修正与优化
  └─ 数据缺失：DataRepairAgent 定向补充搜索
  └─ 数据冲突：ConflictResolver 裁决规范值
  └─ 修补后重新审查 + 重建前文摘要
```

---

## 3. 详细设计

### 3.1 新增数据结构

> 基于真实代码环境，所有数据结构使用 `dataclass`，可被现有代码直接导入使用。

```python
# src/agents/fixed_agents/report_upgrade/models.py

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class DataPoint:
    """数据点：报告中的一个具体数据引用"""
    metric: str
    value: str
    unit: str
    source: str
    chapter_id: str = ""
    confidence: float = 1.0


@dataclass
class MetricEntry:
    """数据注册表中的一个指标条目"""
    metric: str
    value: str
    unit: str
    canonical_chapter: str
    source: str
    conflicts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ChapterWriteInput:
    """ChapterWriter 的输入"""
    framework_config: Dict[str, Any]         # ResearchFrameworkConfig 手动序列化的字典（该类无to_dict()方法）
    task_structure: Dict[str, Any]           # TaskStructure.to_dict() 的序列化结果
    chapter_spec: Dict[str, Any]             # SectionSpec.to_dict() 的序列化结果
    chapter_data: Dict[str, Any]             # 从 AggregationResult.layered_content 中提取
    preceding_summary: str                   # 前文核心结论摘要
    used_metrics_summary: str                # 已使用的数据指标摘要（从DataRegistry序列化）


@dataclass
class ChapterWriteOutput:
    """ChapterWriter 的输出"""
    chapter_id: str
    title: str
    content: str                             # Markdown格式的章节正文
    data_points_used: List[DataPoint] = field(default_factory=list)
    key_conclusions: List[str] = field(default_factory=list)
    self_check_passed: bool = True
    self_check_issues: List[str] = field(default_factory=list)


@dataclass
class ChapterReviewInput:
    """ChapterReviewAgent 的输入"""
    framework_config: Dict[str, Any]
    chapter_spec: Dict[str, Any]
    chapter_content: str
    preceding_summary: str
    used_metrics_summary: str
    topic: str = ""
    writer_self_check_issues: List[str] = field(default_factory=list)


@dataclass
class ChapterIssue:
    """章节审查发现的问题"""
    category: str                            # data_support / logic / completeness / redundancy / style
    severity: str                            # CRITICAL / HIGH / MEDIUM / LOW
    location: str                            # Markdown定位："paragraph:3" / "heading:2.1" / "data:市场规模"
    description: str
    suggestion: str


@dataclass
class ChapterReviewOutput:
    """ChapterReviewAgent 的输出"""
    passed: bool
    score: float
    issues: List[ChapterIssue] = field(default_factory=list)


@dataclass
class ReviewInput:
    """GlobalReviewAgent 的输入"""
    framework_config: Dict[str, Any]
    report_summary: str                      # 结构化报告摘要（紧凑）
    conflicts_summary: str                   # 数据冲突摘要


@dataclass
class ReviewIssue:
    """全局审查发现的问题"""
    dimension: str                           # data_consistency / content_uniqueness / logic_coherence / narrative_completeness / style_uniformity
    severity: str
    description: str
    location: str
    evidence: str


@dataclass
class FixSuggestion:
    """修正建议"""
    target_chapter: str
    issue_id: str
    fix_type: str                            # rewrite / patch / data_fix
    fix_instruction: str
    priority: str


@dataclass
class ReviewOutput:
    """GlobalReviewAgent 的输出"""
    overall_score: float
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[ReviewIssue] = field(default_factory=list)
    fix_suggestions: List[FixSuggestion] = field(default_factory=list)


@dataclass
class DataGap:
    """数据缺失描述"""
    chapter_id: str
    metric: str
    context: str
    search_keywords: List[str] = field(default_factory=list)


@dataclass
class DataRepairResult:
    """数据修补结果"""
    gap: DataGap
    found: bool
    value: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = 0.0


@dataclass
class DataConflict:
    """数据冲突描述"""
    metric: str
    entries: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DataConflictResolution:
    """冲突解决结果（命名避免与 result_aggregator.py:193 的 ConflictResolution Enum 冲突）"""
    conflict: DataConflict
    canonical_value: str
    canonical_unit: str
    canonical_source: str
    reason: str
    chapters_to_update: List[str] = field(default_factory=list)
```

### 3.2 DataRegistry：全局数据注册表

```python
# src/agents/fixed_agents/report_upgrade/data_registry.py

import re
import json
import logging
from typing import Dict, List, Optional, Any
from .models import DataPoint, MetricEntry, DataConflict

logger = logging.getLogger(__name__)


class DataRegistry:
    """全局数据注册表：跟踪所有已使用的数据点，检测数据冲突"""

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
```

### 3.3 ChapterWriter：章节撰写器

```python
# src/agents/fixed_agents/report_upgrade/chapter_writer.py

import re
import json
import logging
from typing import Dict, Any, List, Optional

from .models import ChapterWriteInput, ChapterWriteOutput, DataPoint

DATAPOINT_FIELDS = {"metric", "value", "unit", "source", "chapter_id", "confidence"}

logger = logging.getLogger(__name__)


class ChapterWriter:
    """章节撰写器：基于研究框架和前文上下文，使用LLM撰写单个章节（研究员角色）"""

    def __init__(self, llm_skill) -> None:
        self._llm = llm_skill

    async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
        prompt = self._build_write_prompt(input_data)
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, input_data.chapter_spec)

    async def rewrite(self, original_chapter: ChapterWriteOutput,
                      review_feedback, framework_config: Dict,
                      chapter_spec: Dict, preceding_summary: str) -> ChapterWriteOutput:
        issue_instructions = []
        for issue in review_feedback.issues:
            issue_instructions.append(
                f"- [{issue.severity}] {issue.description}\n  修正方向：{issue.suggestion}"
            )

        prompt = f"""# 章节重写任务

## 当前章节内容
{original_chapter.content}

## 资深研究员反馈（必须逐条修正）
{chr(10).join(issue_instructions)}

## 重写要求
1. 逐条修正资深研究员指出的每一个问题
2. 不要删除没有问题的内容
3. 修正后确保整体逻辑仍然连贯
4. 保持原有的数据引用，除非资深研究员指出数据有误

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{{
  "title": "章节标题",
  "content": "Markdown格式的重写后章节正文",
  "data_points_used": [{{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}}],
  "key_conclusions": ["结论1", "结论2"],
  "self_check_passed": true,
  "self_check_issues": []
}}
```"""
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, chapter_spec)

    async def patch_data(self, chapter: ChapterWriteOutput,
                         patch_instructions: List[str],
                         framework_config: Dict) -> ChapterWriteOutput:
        prompt = f"""# 数据修补任务

## 当前章节内容
{chapter.content}

## 需要修补的数据（只修正涉及这些数据的段落，不要重写整章）
{chr(10).join(f'- {inst}' for inst in patch_instructions)}

## 修补要求
1. 只修改涉及上述数据的句子，逐句替换，不要重写段落
2. 替换格式：将"旧数值 旧单位"替换为"新数值 新单位"，其他文字不变
3. 不要改动与数据无关的任何内容
4. 补充数据来源标注

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{{
  "title": "章节标题",
  "content": "Markdown格式的修补后完整章节正文",
  "data_points_used": [{{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}}],
  "key_conclusions": ["结论1", "结论2"],
  "self_check_passed": true,
  "self_check_issues": []
}}
```"""
        raw_output = await self._call_llm(prompt)
        chapter_spec = {"section_id": chapter.chapter_id, "section_name": chapter.title}
        return self._parse_output(raw_output, chapter_spec)

    def _build_write_prompt(self, input_data: ChapterWriteInput) -> str:
        chapter_spec = input_data.chapter_spec
        framework = input_data.framework_config
        return f"""# 章节撰写任务

## 研究框架
核心问题：{input_data.task_structure.get('topic', '')}
框架配置：{framework.get('name', '通用研究报告')}

## 你的章节角色
章节名：{chapter_spec.get('section_name', '')}
章节ID：{chapter_spec.get('section_id', '')}
章节角色：{chapter_spec.get('section_role', '')}

## 前文脉络
{input_data.preceding_summary}

## 已使用的数据指标（避免重复引用，如有冲突请标注）
{input_data.used_metrics_summary}

## 可用数据
{json.dumps(input_data.chapter_data, ensure_ascii=False, indent=2) if input_data.chapter_data else '无可用数据'}

## 撰写要求
1. 基于研究框架和前文脉络，撰写本章内容
2. 与前文逻辑衔接，避免重复前文已述内容
3. 使用尚未使用的数据点，避免数据重复引用
4. 每个核心判断必须有数据支撑，标注数据来源
5. 如发现与前文数据矛盾，明确标注并给出判断
6. 输出纯Markdown格式，不要包含HTML标签

## 自审检查（生成后立即执行）
完成撰写后，请自行检查：
- [ ] 格式是否规范（Markdown标题层级、列表格式、表格格式）
- [ ] 是否遗漏了关键数据点
- [ ] 数据数值是否与已使用的数据指标中的已有值矛盾
- [ ] 是否有大段与前文重复的内容
如发现问题，请直接修正后输出最终版本。

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{{
  "title": "章节标题",
  "content": "Markdown格式的章节正文",
  "data_points_used": [{{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}}],
  "key_conclusions": ["结论1", "结论2"],
  "self_check_passed": true,
  "self_check_issues": []
}}
```"""

    async def _call_llm(self, prompt: str) -> str:
        result = await self._llm.execute(
            prompt=prompt,
            max_tokens=8192,
            temperature=0.7,
        )
        if not result.get("success"):
            raise RuntimeError(f"LLM call failed: {result}")
        return result["content"]

    def _parse_output(self, raw: str, chapter_spec: Dict) -> ChapterWriteOutput:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                return ChapterWriteOutput(
                    chapter_id=chapter_spec.get("section_id", ""),
                    title=data.get("title", chapter_spec.get("section_name", "")),
                    content=data.get("content", ""),
                    data_points_used=[
                        DataPoint(**{k: v for k, v in dp.items() if k in DATAPOINT_FIELDS})
                        for dp in data.get("data_points_used", [])
                    ],
                    key_conclusions=data.get("key_conclusions", []),
                    self_check_passed=data.get("self_check_passed", True),
                    self_check_issues=data.get("self_check_issues", []),
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse structured output: {e}")

        return ChapterWriteOutput(
            chapter_id=chapter_spec.get("section_id", ""),
            title=chapter_spec.get("section_name", ""),
            content=raw,
            data_points_used=[],
            key_conclusions=self._extract_conclusions(raw),
            self_check_passed=False,
            self_check_issues=["JSON解析失败，输出格式不规范"],
        )

    @staticmethod
    def _extract_conclusions(text: str) -> List[str]:
        lines = text.split("\n")
        conclusions = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- **") and "结论" in stripped:
                conclusions.append(stripped.lstrip("- ").strip("*"))
        return conclusions[:5]
```

### 3.4 ChapterReviewAgent：章节审查Agent

```python
# src/agents/fixed_agents/report_upgrade/chapter_reviewer.py

import re
import json
import logging
from typing import Dict, Any

from .models import ChapterReviewInput, ChapterReviewOutput, ChapterIssue

logger = logging.getLogger(__name__)


class ChapterReviewAgent:
    """章节审查Agent：独立审查单章质量（资深研究员角色）"""

    def __init__(self, llm_skill) -> None:
        self._llm = llm_skill

    async def review(self, input_data: ChapterReviewInput) -> ChapterReviewOutput:
        chapter_spec = input_data.chapter_spec
        prompt = f"""# 章节审查任务

你是一位资深研究员，负责审查初级研究员撰写的章节，你的职责是找出章节中的一切问题。

## 研究框架
核心问题：{input_data.topic}
章节名：{chapter_spec.get('section_name', '')}
章节角色：{chapter_spec.get('section_role', '')}

## 前文脉络
{input_data.preceding_summary}

## 已使用的数据指标（用于检查数据一致性）
{input_data.used_metrics_summary}

## 待审查章节内容
{input_data.chapter_content}

## 作者自审遗留问题（需重点关注）
{chr(10).join(f'- {issue}' for issue in input_data.writer_self_check_issues) if input_data.writer_self_check_issues else '无'}

## 审查维度与标准

### 1. 数据支撑度（权重30%）
- 每个核心判断是否有数据支撑？
- 数据是否标注了来源？
- 数据是否与前文引用的数据一致？

### 2. 逻辑清晰度（权重25%）
- 论点之间是否有逻辑递进？
- 是否存在逻辑跳跃或循环论证？

### 3. 内容完整度（权重20%）
- 框架定义的子问题是否都被回答？
- 是否遗漏了关键论点？

### 4. 内容冗余度（权重15%）
- 是否与前文有大段重复？

### 5. 风格规范性（权重10%）
- 术语使用是否一致？

## 输出要求
1. 给出总分（0-100），60分以下为不通过
2. 每个问题必须给出具体的修正建议
3. 问题按严重程度排序

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{{
  "passed": true,
  "score": 85,
  "issues": [
    {{
      "category": "data_support",
      "severity": "HIGH",
      "location": "data:市场规模",
      "description": "市场规模断言无数据支撑",
      "suggestion": "在第3段补充市场规模数据及来源"
    }}
  ]
}}
```"""

        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Chapter review LLM call failed: {result}")

        return self._parse_output(result["content"])

    def _parse_output(self, raw: str) -> ChapterReviewOutput:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                issues = [
                    ChapterIssue(
                        category=iss.get("category", "style"),
                        severity=iss.get("severity", "MEDIUM"),
                        location=iss.get("location", ""),
                        description=iss.get("description", ""),
                        suggestion=iss.get("suggestion", ""),
                    )
                    for iss in data.get("issues", [])
                ]
                return ChapterReviewOutput(
                    passed=data.get("passed", True),
                    score=float(data.get("score", 100.0)),
                    issues=issues,
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse review output: {e}")

        return ChapterReviewOutput(passed=False, score=0.0)
```

### 3.5 GlobalReviewAgent：全局审查Agent

```python
# src/agents/fixed_agents/report_upgrade/global_reviewer.py

import re
import json
import logging
from typing import Dict, Any, List

from .models import (
    ReviewInput, ReviewOutput, ReviewIssue, FixSuggestion, ChapterWriteOutput,
)

logger = logging.getLogger(__name__)


class GlobalReviewAgent:
    """全局审查Agent：对完整报告进行两步审查"""

    def __init__(self, llm_skill) -> None:
        self._llm = llm_skill

    async def review(self, input_data: ReviewInput) -> ReviewOutput:
        prompt = f"""# 全局审查任务

你是一位研究总监，关注跨章节的系统性问题。

## 研究框架
{input_data.framework_config.get('name', '通用研究报告')}

## 报告结构化摘要
{input_data.report_summary}

## 已知数据冲突
{input_data.conflicts_summary}

## 审查维度
1. 数据一致性（CRITICAL）：同一指标跨章节是否一致
2. 内容去重（HIGH）：跨章节是否有大段重复
3. 逻辑连贯性（HIGH）：章节间逻辑递进是否清晰
4. 叙事完整性（HIGH）：核心问题是否被完整回答
5. 术语和风格统一性（MEDIUM）：术语、语气是否一致

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{{
  "overall_score": 75,
  "dimension_scores": {{"data_consistency": 60, "content_uniqueness": 90, "logic_coherence": 70, "narrative_completeness": 80, "style_uniformity": 85}},
  "issues": [
    {{
      "dimension": "data_consistency",
      "severity": "CRITICAL",
      "description": "市场规模在概述章为2000亿，细分章为1800亿",
      "location": "chapter_1, chapter_3",
      "evidence": "概述章'约2000亿元' vs 细分章'达1800亿元'"
    }}
  ],
  "fix_suggestions": [
    {{
      "target_chapter": "chapter_3",
      "issue_id": "issue_1",
      "fix_type": "patch",
      "fix_instruction": "将细分章市场规模统一为2000亿元",
      "priority": "CRITICAL"
    }}
  ]
}}
```"""

        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Global review LLM call failed: {result}")

        return self._parse_output(result["content"])

    async def verify_issues(self, issues: List[ReviewIssue],
                            chapters: List[ChapterWriteOutput]) -> List[ReviewIssue]:
        """两步审查的Step 2：批量对摘要审查发现的问题读原文确认"""
        if not issues:
            return []

        # 批量构造验证Prompt（一次LLM调用验证所有问题）
        all_contexts = []
        for issue in issues:
            relevant_content = self._extract_relevant_chapters(issue, chapters)
            all_contexts.append(f"问题：{issue.description}\n位置：{issue.location}\n相关原文：\n{relevant_content[:2000]}")

        prompt = f"""以下问题是在摘要审查中发现的，请逐条阅读原文确认：

{chr(10).join(f'### 问题{i+1}{chr(10)}{ctx}' for i, ctx in enumerate(all_contexts))}

请对每个问题确认：1=确实存在 0=误报。如确认存在，补充精确的问题描述。

输出JSON数组：[{{"confirmed": true, "refined_description": "...", "refined_evidence": "..."}}, ...]"""

        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            return issues

        try:
            json_match = re.search(r'\[.*\]', result["content"], re.DOTALL)
            if json_match:
                parsed_list = json.loads(json_match.group())
                verified = []
                for i, parsed in enumerate(parsed_list):
                    if i >= len(issues):
                        break
                    if parsed.get("confirmed"):
                        verified.append(ReviewIssue(
                            dimension=issues[i].dimension,
                            severity=issues[i].severity,
                            description=parsed.get("refined_description", issues[i].description),
                            location=issues[i].location,
                            evidence=parsed.get("refined_evidence", issues[i].evidence),
                        ))
                return verified
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return issues

    @staticmethod
    def _extract_relevant_chapters(issue: ReviewIssue,
                                   chapters: List[ChapterWriteOutput]) -> str:
        location_ids = [loc.strip() for loc in issue.location.split(",")]
        parts = []
        for ch in chapters:
            if ch.chapter_id in location_ids:
                parts.append(f"### {ch.title}（{ch.chapter_id}）\n{ch.content[:3000]}")
        return "\n\n".join(parts) if parts else "未找到相关章节"

    def _parse_output(self, raw: str) -> ReviewOutput:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                issues = [
                    ReviewIssue(
                        dimension=iss.get("dimension", ""),
                        severity=iss.get("severity", "MEDIUM"),
                        description=iss.get("description", ""),
                        location=iss.get("location", ""),
                        evidence=iss.get("evidence", ""),
                    )
                    for iss in data.get("issues", [])
                ]
                fix_suggestions = [
                    FixSuggestion(
                        target_chapter=fix.get("target_chapter", ""),
                        issue_id=fix.get("issue_id", ""),
                        fix_type=fix.get("fix_type", "rewrite"),
                        fix_instruction=fix.get("fix_instruction", ""),
                        priority=fix.get("priority", "MEDIUM"),
                    )
                    for fix in data.get("fix_suggestions", [])
                ]
                return ReviewOutput(
                    overall_score=float(data.get("overall_score", 100.0)),
                    dimension_scores=data.get("dimension_scores", {}),
                    issues=issues,
                    fix_suggestions=fix_suggestions,
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse global review output: {e}")

        return ReviewOutput(overall_score=0.0)


def serialize_report_for_review(chapters: List[ChapterWriteOutput],
                                data_registry) -> str:
    """将完整报告序列化为全局审查用的紧凑摘要"""
    sections_summary = []
    for i, ch in enumerate(chapters):
        data_summary = []
        for dp in ch.data_points_used:
            data_summary.append(f"  {dp.metric}: {dp.value} {dp.unit}")
        sections_summary.append(
            f"### 第{i+1}章：{ch.title}\n"
            f"核心结论：{'; '.join(ch.key_conclusions)}\n"
            f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
        )
    return "\n\n".join(sections_summary)
```

### 3.6 DataRepairAgent + ConflictResolver

```python
# src/agents/fixed_agents/report_upgrade/data_repair.py

import re
import json
import logging
from typing import Dict, Any, List, Optional

from .models import DataGap, DataRepairResult, DataConflict, DataConflictResolution

logger = logging.getLogger(__name__)


class DataRepairAgent:
    """数据修补Agent：定向搜索缺失数据"""

    def __init__(self, search_skill, web_scraper_skill, llm_skill) -> None:
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._llm = llm_skill

    async def repair_gap(self, gap: DataGap, topic: str) -> DataRepairResult:
        query = f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}"
        search_result = await self._search.execute(query=query, max_results=10) or {}

        if not search_result.get("success") or not search_result.get("results"):
            return DataRepairResult(gap=gap, found=False)

        scraped_contents = []
        for result in search_result["results"][:3]:
            url = result.get("href", "")    # 真实搜索结果字段名为 href（非 url）
            if url:
                scrape_result = await self._scraper.execute(
                    url=url, action="extract_markdown", max_chars=3000,
                )
                if scrape_result.get("success") and scrape_result.get("text"):
                    scraped_contents.append({
                        "url": url,
                        "title": result.get("title", ""),
                        "content": scrape_result["text"][:3000],
                    })

        if not scraped_contents:
            return DataRepairResult(gap=gap, found=False)

        extraction_prompt = f"""从以下搜索结果中提取"{gap.metric}"的具体数值。
缺失上下文：{gap.context}
研究主题：{topic}

搜索结果：
{chr(10).join(f'--- 来源: {c["title"]} ({c["url"]}) ---{chr(10)}{c["content"]}' for c in scraped_contents)}

要求：
1. 只提取有明确来源的数据，不要推断
2. 如果多个来源给出不同数值，列出所有及来源
3. 如果搜索结果中没有相关数据，返回 found=false

输出JSON：{{"found": true/false, "value": "...", "unit": "...", "source": "...", "source_title": "...", "confidence": 0.8}}"""

        llm_result = await self._llm.execute(prompt=extraction_prompt, max_tokens=2048)
        if not llm_result.get("success"):
            return DataRepairResult(gap=gap, found=False)

        return self._parse_extraction(llm_result["content"], gap)

    async def repair_batch(self, gaps: List[DataGap], topic: str) -> List[DataRepairResult]:
        import asyncio
        semaphore = asyncio.Semaphore(5)  # 限制并发搜索数，避免触发搜索引擎限流

        async def _limited_repair(gap: DataGap) -> DataRepairResult:
            async with semaphore:
                return await self.repair_gap(gap, topic)

        tasks = [_limited_repair(gap) for gap in gaps]
        return await asyncio.gather(*tasks)

    def _parse_extraction(self, raw: str, gap: DataGap) -> DataRepairResult:
        try:
            json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("found"):
                    return DataRepairResult(
                        gap=gap, found=True,
                        value=data.get("value"),
                        unit=data.get("unit"),
                        source=data.get("source"),
                        source_title=data.get("source_title"),
                        confidence=float(data.get("confidence", 0.5)),
                    )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse extraction result: {e}")
        return DataRepairResult(gap=gap, found=False)


class ConflictResolver:
    """数据冲突裁决器"""

    SOURCE_AUTHORITY = {
        "gov.cn": 10, "gov": 8,
        "worldbank.org": 9, "imf.org": 9, "oecd.org": 9,
        "iimedia.cn": 8, "iresearch.cn": 8,
        "mckinsey.com": 8, "bcg.com": 8, "idc.com": 8, "gartner.com": 8,
        "statista.com": 7,
        "nature.com": 8, "arxiv.org": 7, "sciencedirect.com": 7,
        "bloomberg.com": 6, "reuters.com": 6,
        "eastmoney.com": 6, "10jqka.com.cn": 6,
        "36kr.com": 4, "sohu.com": 3,
    }

    DESCRIPTION_RULES = [
        (r"国家统计局|官方统计|政府公告", 10),
        (r"年报|季报|财报|IPO招股书", 8),
        (r"研究报告|白皮书|行业报告", 7),
        (r"新闻报道|媒体报道", 4),
    ]

    def __init__(self, llm_skill, search_skill=None, web_scraper_skill=None) -> None:
        self._llm = llm_skill
        self._search = search_skill
        self._scraper = web_scraper_skill

    async def resolve(self, conflict: DataConflict, topic: str) -> DataConflictResolution:
        best_entry = None
        best_score = -1

        for entry in conflict.entries:
            score = self._score_entry(entry)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= 6:
            chapters_to_update = [
                e["chapter_id"] for e in conflict.entries
                if e["value"] != best_entry["value"]
            ]
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=best_entry["value"],
                canonical_unit=best_entry.get("unit", ""),
                canonical_source=best_entry.get("source", ""),
                reason=f"来源 {best_entry.get('source', '')} 权威性更高（评分={best_score}）",
                chapters_to_update=chapters_to_update,
            )

        return await self._resolve_by_search(conflict, topic)

    async def _resolve_by_search(self, conflict: DataConflict, topic: str) -> DataConflictResolution:
        if not self._search:
            first = conflict.entries[0] if conflict.entries else {}
            return DataConflictResolution(
                conflict=conflict,
                canonical_value=first.get("value", ""),
                canonical_unit=first.get("unit", ""),
                canonical_source=first.get("source", ""),
                reason="无搜索能力，采用首个条目",
                chapters_to_update=[e["chapter_id"] for e in conflict.entries[1:]],
            )

        search_query = f"{topic} {conflict.metric} 最新数据"
        search_result = await self._search.execute(query=search_query, max_results=5)
        results = search_result.get("results", []) if search_result.get("success") else []

        resolution_prompt = f"""以下数据存在冲突，请裁决：
指标：{conflict.metric}
冲突条目：
{chr(10).join(f'- 章节{e.get("chapter_id","")}：{e.get("value","")} {e.get("unit","")}（来源：{e.get("source","")}）' for e in conflict.entries)}

补充搜索结果：
{chr(10).join(f'- {r.get("title","")}: {r.get("body","")}' for r in results[:5])}

裁决要求：
1. 优先采用官方统计/权威研究机构的数据
2. 优先采用更新日期更近的数据
3. 给出裁决理由

输出JSON：{{"canonical_value": "...", "canonical_unit": "...", "canonical_source": "...", "reason": "..."}}"""

        llm_result = await self._llm.execute(prompt=resolution_prompt, max_tokens=2048)
        first = conflict.entries[0] if conflict.entries else {}
        canonical_value = first.get("value", "")
        canonical_unit = first.get("unit", "")
        canonical_source = first.get("source", "")
        reason = "LLM裁决"

        if llm_result.get("success"):
            try:
                json_match = re.search(r'\{[^{}]*\}', llm_result["content"], re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    canonical_value = data.get("canonical_value", canonical_value)
                    canonical_unit = data.get("canonical_unit", canonical_unit)
                    canonical_source = data.get("canonical_source", canonical_source)
                    reason = data.get("reason", reason)
            except (json.JSONDecodeError, KeyError):
                pass

        return DataConflictResolution(
            conflict=conflict,
            canonical_value=canonical_value,
            canonical_unit=canonical_unit,
            canonical_source=canonical_source,
            reason=reason,
            chapters_to_update=[
                e["chapter_id"] for e in conflict.entries
                if e.get("value") != canonical_value
            ],
        )

    def _score_entry(self, entry: Dict[str, Any]) -> int:
        source = entry.get("source", "")
        score = 0
        for domain, authority in self.SOURCE_AUTHORITY.items():
            if domain in source:
                score = authority
                break
        if score == 0 and source:
            for pattern, rule_score in self.DESCRIPTION_RULES:
                if re.search(pattern, source):
                    score = rule_score
                    break
        return score
```

### 3.7 ReportOrchestrator：报告编排器

```python
# src/agents/fixed_agents/report_upgrade/orchestrator.py

import re
import json
import asyncio
import logging
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

from .models import (
    ChapterWriteInput, ChapterWriteOutput, ChapterReviewInput, ChapterReviewOutput,
    ReviewInput, ReviewOutput, DataGap, DataConflict, DataPoint, DataConflictResolution,
)
from .data_registry import DataRegistry
from .chapter_writer import ChapterWriter
from .chapter_reviewer import ChapterReviewAgent
from .global_reviewer import GlobalReviewAgent, serialize_report_for_review
from .data_repair import DataRepairAgent, ConflictResolver

logger = logging.getLogger(__name__)


class RetryPolicy:
    MAX_CHAPTER_RETRIES = 3
    MAX_REVIEW_RETRIES = 2
    MAX_FULL_RETRIES = 1
    RETRY_BACKOFF_BASE = 2

    @staticmethod
    def get_delay(attempt: int) -> float:
        return RetryPolicy.RETRY_BACKOFF_BASE ** attempt


class ReportOrchestrator:
    """报告编排器：框架驱动·逐章生成·独立审查·全局审查"""

    def __init__(
        self,
        llm_skill,
        chapter_writer: ChapterWriter,
        chapter_reviewer: ChapterReviewAgent,
        global_reviewer: GlobalReviewAgent,
        data_repair_agent: DataRepairAgent,
        conflict_resolver: ConflictResolver,
    ) -> None:
        self._llm = llm_skill
        self._chapter_writer = chapter_writer
        self._chapter_reviewer = chapter_reviewer
        self._global_reviewer = global_reviewer
        self._data_repair_agent = data_repair_agent
        self._conflict_resolver = conflict_resolver
        self._data_registry = DataRegistry()
        self._task_structure: Dict[str, Any] = {}
        self._MAX_PRECEDING_SUMMARY_LENGTH = 3000

    async def generate_report(
        self,
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
        aggregated_result: Any,  # AggregationResult 对象（非 to_dict() 输出，因 to_dict() 不含 layered_content）
        topic: str = "",
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成报告（新流程）

        对接真实代码：
          - task_structure: TaskStructure.to_dict() 的输出
          - framework_config: ResearchFrameworkConfig 手动序列化的字典（该类无 to_dict() 方法）
          - aggregated_result: AggregationResult **对象**（非 to_dict() 输出）
            原因：to_dict() 不序列化 layered_content 和 content_provenance，
            而 _extract_chapter_data() 需要这两个字段
          - 返回值格式与 ContentOrchestrator.transform_to_html() 的输入一致
        """
        last_error = None

        for full_attempt in range(RetryPolicy.MAX_FULL_RETRIES + 1):
            try:
                # 重试时：优先从检查点恢复，否则重建
                if task_id:
                    restored = await self._restore_from_checkpoint(task_id)
                    if restored:
                        chapters, registry_snapshot = restored
                        self._data_registry = DataRegistry.from_snapshot(registry_snapshot)
                        preceding_summary = self._rebuild_preceding_summary(chapters)
                        completed_section_ids = {ch.chapter_id for ch in chapters}
                        logger.info(f"Restored {len(chapters)} chapters from checkpoint (attempt {full_attempt+1})")
                    else:
                        self._data_registry = DataRegistry()
                        chapters = []
                        preceding_summary = ""
                        completed_section_ids = set()
                else:
                    self._data_registry = DataRegistry()
                    chapters = []
                    preceding_summary = ""
                    completed_section_ids = set()

                self._task_structure = task_structure

                # Phase 1: 框架理解（从task_structure和framework_config构建叙事上下文）
                narrative_context = self._understand_framework(task_structure, framework_config)

                # Phase 2: 逐章撰写 + 独立审查闭环

                for section_spec in task_structure.get("sections", []):
                    section_id = section_spec.get("section_id", "")

                    if section_id in completed_section_ids:
                        continue

                    chapter_data = self._extract_chapter_data(
                        aggregated_result, section_id,
                        section_spec.get("content_dependency", []),
                    )

                    chapter = None
                    last_chapter_error = None

                    for chapter_attempt in range(RetryPolicy.MAX_CHAPTER_RETRIES):
                        try:
                            chapter = await self._chapter_writer.write(
                                ChapterWriteInput(
                                    framework_config=framework_config,
                                    task_structure=task_structure,
                                    chapter_spec=section_spec,
                                    chapter_data=chapter_data,
                                    preceding_summary=preceding_summary,
                                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                                )
                            )

                            # 数据点注册（验证后注册）
                            validated_dps = self._extract_and_validate_data_points(chapter)
                            for dp in validated_dps:
                                self._data_registry.register(
                                    metric=dp.metric, value=dp.value, unit=dp.unit,
                                    chapter_id=chapter.chapter_id, source=dp.source,
                                )

                            # 独立审查闭环（版本对比保底）
                            best_chapter = chapter
                            best_score = 0.0

                            for rewrite_round in range(2):
                                review = await self._chapter_reviewer.review(
                                    ChapterReviewInput(
                                        framework_config=framework_config,
                                        chapter_spec=section_spec,
                                        chapter_content=chapter.content,
                                        preceding_summary=preceding_summary,
                                        used_metrics_summary=self._data_registry.serialize_used_metrics(),
                                        topic=task_structure.get('topic', ''),
                                        writer_self_check_issues=chapter.self_check_issues,
                                    )
                                )

                                if review.passed:
                                    if review.score > best_score:
                                        best_chapter = chapter
                                        best_score = review.score
                                    break

                                if review.score > best_score:
                                    best_chapter = chapter
                                    best_score = review.score

                                chapter = await self._chapter_writer.rewrite(
                                    original_chapter=chapter,
                                    review_feedback=review,
                                    framework_config=framework_config,
                                    chapter_spec=section_spec,
                                    preceding_summary=preceding_summary,
                                )

                            chapter = best_chapter
                            break

                        except (asyncio.TimeoutError, RuntimeError) as e:
                            last_chapter_error = str(e)
                            delay = RetryPolicy.get_delay(chapter_attempt)
                            logger.warning(f"Chapter attempt {chapter_attempt+1} failed: {e}")
                            await asyncio.sleep(delay)

                    if chapter is None:
                        logger.error(f"Chapter {section_id} failed after retries")
                        continue

                    chapters.append(chapter)
                    preceding_summary = self._append_preceding_summary(
                        preceding_summary, chapter
                    )

                    if task_id:
                        self._checkpoint_chapter(task_id, chapter)

                # Phase 3: 全局审查（两步审查）
                report_summary = serialize_report_for_review(chapters, self._data_registry)
                conflicts_summary = self._data_registry.serialize_conflicts()

                review = await self._global_reviewer.review(
                    ReviewInput(
                        framework_config=framework_config,
                        report_summary=report_summary,
                        conflicts_summary=conflicts_summary,
                    )
                )

                if review.issues:
                    verified_issues = await self._global_reviewer.verify_issues(
                        review.issues, chapters,
                    )
                    review.issues = verified_issues

                # Phase 4: 修正与优化
                if review.overall_score < 80:
                    chapters = await self._phase4_fix_and_optimize(
                        chapters, review, framework_config, topic,
                    )

                # 重新生成执行摘要
                exec_summary = await self._generate_exec_summary(chapters, task_structure, topic)

                # 组装最终报告
                original_sources = getattr(aggregated_result, 'sources', [])
                return self._assemble_final_report(chapters, exec_summary, review, topic, original_sources)

            except Exception as e:
                last_error = e
                if full_attempt < RetryPolicy.MAX_FULL_RETRIES:
                    delay = RetryPolicy.get_delay(full_attempt)
                    logger.warning(f"Full attempt {full_attempt+1} failed: {e}")
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Report generation failed after {RetryPolicy.MAX_FULL_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )

    # === Phase 1 ===

    @staticmethod
    def _understand_framework(task_structure: Dict, framework_config: Dict) -> str:
        sections = task_structure.get("sections", [])
        section_names = [s.get("section_name", "") for s in sections]
        return (
            f"研究主题：{task_structure.get('topic', '')}\n"
            f"框架配置：{framework_config.get('name', '通用研究报告')}\n"
            f"章节结构：{' → '.join(section_names)}"
        )

    # === Phase 4 ===

    async def _phase4_fix_and_optimize(
        self,
        chapters: List[ChapterWriteOutput],
        review: ReviewOutput,
        framework_config: Dict,
        topic: str,
    ) -> List[ChapterWriteOutput]:
        data_gaps = []
        data_conflicts = self._data_registry.get_conflicts()

        for issue in review.issues:
            if issue.dimension == "data_consistency":
                pass  # 已从 DataRegistry 获取冲突
            elif "缺失" in issue.description or "无数据" in issue.description:
                data_gaps.append(DataGap(
                    chapter_id=issue.location,
                    metric=self._extract_metric(issue.description),
                    context=issue.description,
                    search_keywords=[issue.description[:20]],
                ))

        repair_task = self._data_repair_agent.repair_batch(data_gaps, topic)
        resolve_tasks = [self._conflict_resolver.resolve(c, topic) for c in data_conflicts]

        import asyncio
        repair_results, *resolution_results = await asyncio.gather(
            repair_task, *resolve_tasks,
        )

        chapters, patched_chapter_ids = self._apply_data_repairs(
            chapters, repair_results, resolution_results, framework_config,
        )

        # 修补后重新审查（使用重建的前文摘要）
        preceding_summary = self._rebuild_preceding_summary(chapters)

        for i, chapter in enumerate(chapters):
            if chapter.chapter_id not in patched_chapter_ids:
                continue
            chapter_spec = self._find_section_spec(chapter.chapter_id, framework_config)
            re_review = await self._chapter_reviewer.review(
                ChapterReviewInput(
                    framework_config=framework_config,
                    chapter_spec=chapter_spec,
                    chapter_content=chapter.content,
                    preceding_summary=preceding_summary,
                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                    topic=self._task_structure.get('topic', ''),
                )
            )
            if not re_review.passed:
                chapters[i] = await self._chapter_writer.rewrite(
                    original_chapter=chapter,
                    review_feedback=re_review,
                    framework_config=framework_config,
                    chapter_spec=chapter_spec,
                    preceding_summary=preceding_summary,
                )

        # 重建前文摘要 + 验证下游一致性
        preceding_summary = self._rebuild_preceding_summary(chapters)
        self._verify_downstream_consistency(chapters, patched_chapter_ids)

        return chapters

    async def _apply_data_repairs(
        self,
        chapters: List[ChapterWriteOutput],
        repair_results: List[DataRepairResult],
        conflict_resolutions: List[DataConflictResolution],
        framework_config: Dict,
    ) -> Tuple[List[ChapterWriteOutput], Set[str]]:
        chapter_updates: Dict[str, List[Dict]] = {}

        for result in repair_results:
            if result.found:
                chapter_updates.setdefault(result.gap.chapter_id, []).append({
                    "type": "gap_filled",
                    "metric": result.gap.metric,
                    "new_value": result.value,
                    "unit": result.unit,
                    "source": result.source,
                })

        for resolution in conflict_resolutions:
            for chapter_id in resolution.chapters_to_update:
                chapter_updates.setdefault(chapter_id, []).append({
                    "type": "conflict_resolved",
                    "metric": resolution.conflict.metric,
                    "canonical_value": resolution.canonical_value,
                    "canonical_unit": resolution.canonical_unit,
                    "canonical_source": resolution.canonical_source,
                    "reason": resolution.reason,
                })

        patched_chapter_ids: Set[str] = set()

        for i, chapter in enumerate(chapters):
            updates = chapter_updates.get(chapter.chapter_id, [])
            if not updates:
                continue

            patch_instructions = []
            for update in updates:
                if update["type"] == "gap_filled":
                    patch_instructions.append(
                        f"补充缺失数据：{update['metric']} = {update['new_value']} {update['unit']}"
                        f"（来源：{update['source']}）"
                    )
                elif update["type"] == "conflict_resolved":
                    patch_instructions.append(
                        f"数据冲突修正：{update['metric']} 统一为 {update['canonical_value']} "
                        f"{update['canonical_unit']}（来源：{update['canonical_source']}，"
                        f"理由：{update['reason']}）"
                    )

            chapters[i] = await self._chapter_writer.patch_data(
                chapter=chapter,
                patch_instructions=patch_instructions,
                framework_config=framework_config,
            )
            patched_chapter_ids.add(chapter.chapter_id)

            for update in updates:
                if update["type"] == "conflict_resolved":
                    self._data_registry.set_canonical_value(
                        metric=update["metric"],
                        value=update["canonical_value"],
                        source=update["canonical_source"],
                    )

        return chapters, patched_chapter_ids

    # === 辅助方法 ===

    @staticmethod
    def _extract_chapter_data(
        aggregated_result: Any, section_id: str, content_dependencies: List[str],
    ) -> Dict[str, Any]:
        # 直接访问 AggregationResult 对象属性（非 to_dict() 输出，因 to_dict() 不含这两个字段）
        layered_content = getattr(aggregated_result, 'layered_content', {})
        content_provenance = getattr(aggregated_result, 'content_provenance', {})

        # 优先：从 content_provenance 找到指向此 section_id 的 key
        for key, provenance in content_provenance.items():
            # 兼容 ContentProvenance 对象和 dict
            if hasattr(provenance, 'section_target'):
                target = provenance.section_target
            elif isinstance(provenance, dict):
                target = provenance.get("section_target", "")
            else:
                continue
            if target == section_id:
                for stage_content in layered_content.values():
                    if key in stage_content:
                        return stage_content[key]

        # Fallback：从 layered_content 的 analysis 阶段搜索
        for stage_name, stage_data in layered_content.items():
            if not isinstance(stage_data, dict):
                continue
            for key, value in stage_data.items():
                if section_id in key or any(dep in key for dep in content_dependencies):
                    return value

        return {}

    @staticmethod
    def _extract_and_validate_data_points(chapter: ChapterWriteOutput) -> List[DataPoint]:
        validated = list(chapter.data_points_used)

        # 正则从内容中提取数据点（补充LLM自报遗漏）
        pattern = re.compile(
            r'(\d[\d,.]*)\s*'
            r'(亿元|万元|元|%|亿美元|千万|百万|万亿美元'
            r'|billion|million|trillion|thousand|percent|%\s*)',
            re.IGNORECASE
        )
        for match in pattern.finditer(chapter.content):
            value = match.group(1)
            unit = match.group(2)
            already_reported = any(
                dp.value.replace(",", "") == value.replace(",", "") and dp.unit == unit
                for dp in validated
            )
            if not already_reported:
                context_start = max(0, match.start() - 30)
                context = chapter.content[context_start:match.start()].strip()
                validated.append(DataPoint(
                    metric=context[-15:] if context else "未命名指标",
                    value=value, unit=unit, source="",
                    chapter_id=chapter.chapter_id,
                ))

        return validated

    @staticmethod
    def _rebuild_preceding_summary(chapters: List[ChapterWriteOutput]) -> str:
        return "\n".join(
            f"【{ch.title}】{'; '.join(ch.key_conclusions)}" for ch in chapters
        )

    def _append_preceding_summary(self, existing: str, chapter: ChapterWriteOutput) -> str:
        new_entry = f"\n【{chapter.title}】{'; '.join(chapter.key_conclusions)}"
        result = existing + new_entry
        if len(result) > self._MAX_PRECEDING_SUMMARY_LENGTH:
            lines = result.split("\n")
            while len(result) > self._MAX_PRECEDING_SUMMARY_LENGTH and len(lines) > 2:
                lines = lines[1:]
                result = "\n".join(lines)
        return result

    @staticmethod
    def _verify_downstream_consistency(
        chapters: List[ChapterWriteOutput], patched_chapter_ids: Set[str],
    ) -> None:
        for chapter in chapters:
            if chapter.chapter_id in patched_chapter_ids:
                continue
            for patched_id in patched_chapter_ids:
                patched_ch = next(
                    (c for c in chapters if c.chapter_id == patched_id), None
                )
                if not patched_ch:
                    continue
                for dp in patched_ch.data_points_used:
                    if dp.metric and dp.metric in chapter.content:
                        pattern = re.compile(
                            re.escape(dp.value) + r'\s*' + re.escape(dp.unit)
                        )
                        if not pattern.search(chapter.content):
                            logger.warning(
                                f"Chapter {chapter.chapter_id} references '{dp.metric}' "
                                f"with outdated value after patch of chapter {patched_id}"
                            )

    def _find_section_spec(self, section_id: str, framework_config: Dict) -> Dict:
        """从 task_structure 中查找真实的 SectionSpec"""
        for sec in self._task_structure.get("sections", []):
            if sec.get("section_id") == section_id:
                return sec
        return {"section_id": section_id, "section_name": section_id, "section_role": "analysis"}

    @staticmethod
    def _extract_metric(description: str) -> str:
        match = re.search(r'["「](.+?)["」]', description)
        return match.group(1) if match else description[:20]

    async def _generate_exec_summary(
        self, chapters: List[ChapterWriteOutput],
        task_structure: Dict, topic: str,
    ) -> str:
        all_conclusions = []
        for ch in chapters:
            all_conclusions.extend(ch.key_conclusions)

        conflict_descriptions = []
        for c in self._data_registry.get_conflicts():
            values_str = ", ".join(
                f'{e["value"]}{e["unit"]}（来源:{e["source"]}）' for e in c.entries
            )
            conflict_descriptions.append(f"{c.metric}: {values_str}")

        prompt = f"""# 执行摘要撰写任务

## 研究主题
{topic}

## 各章节核心结论
{chr(10).join(f'- {c}' for c in all_conclusions)}

## 数据冲突
{chr(10).join(f'- {d}' for d in conflict_descriptions) if conflict_descriptions else '无'}

## 撰写要求
1. 基于核心叙事线，将各章节结论整合为连贯的执行摘要
2. 突出最重要的3-5个发现
3. 长度：800-1200字
4. 面向决策层，语言精炼有力
5. 直接输出Markdown文本，不要JSON包装"""

        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.7)
        if result.get("success"):
            return result["content"]
        return "执行摘要生成失败。"

    @staticmethod
    def _assemble_final_report(
        chapters: List[ChapterWriteOutput],
        exec_summary: str,
        review: ReviewOutput,
        topic: str,
        original_sources: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """组装最终报告，输出格式与 ContentOrchestrator.transform_to_html() 输入一致"""
        all_sources = list(original_sources) if original_sources else []
        sections = []
        for ch in chapters:
            sections.append({
                "id": ch.chapter_id,
                "title": ch.title,
                "content": ch.content,  # Markdown，由 ContentOrchestrator 转 HTML
                "subsections": [],
                "charts": [],
                "data_points": [asdict(dp) for dp in ch.data_points_used],
                "sources": [],
            })

        return {
            "topic": topic,
            "title": topic,
            "aspects": [ch.title for ch in chapters],
            "sections": sections,
            "sources": all_sources,
            "key_findings": exec_summary.split("\n")[:10],
        }

    # === 检查点持久化 ===

    async def _checkpoint_chapter(self, task_id: str, chapter: ChapterWriteOutput) -> None:
        checkpoint_dir = Path("data") / task_id / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        chapter_data = {
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "content": chapter.content,
            "data_points_used": [asdict(dp) for dp in chapter.data_points_used],
            "key_conclusions": chapter.key_conclusions,
            "self_check_passed": chapter.self_check_passed,
            "self_check_issues": chapter.self_check_issues,
            "data_registry_snapshot": self._data_registry.to_snapshot(),
            "timestamp": datetime.now().isoformat(),
        }

        checkpoint_path = checkpoint_dir / f"chapter_{chapter.chapter_id}.json"
        await asyncio.to_thread(
            checkpoint_path.write_text,
            json.dumps(chapter_data, ensure_ascii=False, indent=2),
            "utf-8",
        )

    @staticmethod
    async def _restore_from_checkpoint(task_id: str):
        checkpoint_dir = Path("data") / task_id / "checkpoints"
        if not checkpoint_dir.exists():
            return None

        def _read_checkpoints():
            results = []
            for path in sorted(checkpoint_dir.glob("chapter_*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    results.append(data)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to restore checkpoint {path}: {e}")
            return results

        checkpoint_data_list = await asyncio.to_thread(_read_checkpoints)

        chapters = []
        registry_snapshot = {}
        for data in checkpoint_data_list:
            chapter = ChapterWriteOutput(
                chapter_id=data["chapter_id"],
                title=data["title"],
                content=data["content"],
                data_points_used=[
                    DataPoint(**{k: v for k, v in dp.items() if k in DATAPOINT_FIELDS})
                    for dp in data.get("data_points_used", [])
                ],
                key_conclusions=data.get("key_conclusions", []),
                self_check_passed=data.get("self_check_passed", True),
                self_check_issues=data.get("self_check_issues", []),
            )
            chapters.append(chapter)
            registry_snapshot = data.get("data_registry_snapshot", {})

        return (chapters, registry_snapshot) if chapters else None
```

### 3.8 PromptManager：Prompt集中管理

> 所有Prompt从代码中剥离，集中存放到 `prompts/` 目录下，使用Python `string.Template` 做变量替换，
> 避免f-string硬编码导致Prompt难以维护、审计和迭代。

#### 3.8.1 Prompt文件清单与变量

| Prompt文件 | 使用者 | 模板变量 |
|-----------|--------|---------|
| `chapter_write.tmpl` | ChapterWriter.write() | `topic`, `framework_name`, `section_name`, `section_id`, `section_role`, `preceding_summary`, `used_metrics_summary`, `chapter_data` |
| `chapter_rewrite.tmpl` | ChapterWriter.rewrite() | `original_content`, `review_feedback`, `section_name`, `section_id` |
| `chapter_patch_data.tmpl` | ChapterWriter.patch_data() | `chapter_content`, `patch_instructions`, `section_name`, `section_id` |
| `chapter_review.tmpl` | ChapterReviewAgent.review() | `topic`, `section_name`, `section_role`, `preceding_summary`, `used_metrics_summary`, `chapter_content`, `writer_self_check_issues` |
| `global_review.tmpl` | GlobalReviewAgent.review() | `framework_name`, `report_summary`, `conflicts_summary` |
| `global_verify_issues.tmpl` | GlobalReviewAgent.verify_issues() | `issues_context` |
| `data_extraction.tmpl` | DataRepairAgent.repair_gap() | `metric`, `context`, `topic`, `search_results` |
| `conflict_resolution.tmpl` | ConflictResolver._resolve_by_search() | `metric`, `conflict_entries`, `search_results` |
| `exec_summary.tmpl` | ReportOrchestrator._generate_exec_summary() | `topic`, `all_conclusions`, `conflict_descriptions` |

#### 3.8.2 PromptManager 实现

```python
# src/agents/fixed_agents/report_upgrade/prompt_manager.py

import logging
from string import Template
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptManager:
    """Prompt集中管理：从文件系统加载模板，使用string.Template做变量替换"""

    def __init__(self, prompts_dir: Path = _PROMPTS_DIR) -> None:
        self._prompts_dir = prompts_dir
        self._cache: Dict[str, Template] = {}

    def get(self, name: str, **kwargs: Any) -> str:
        """
        加载并渲染Prompt模板。

        Args:
            name: 模板名（不含扩展名），如 "chapter_write"
            **kwargs: 模板变量

        Returns:
            渲染后的Prompt字符串

        Raises:
            KeyError: 模板变量缺失
            FileNotFoundError: 模板文件不存在
        """
        template = self._load_template(name)
        try:
            return template.substitute(**kwargs)
        except KeyError as e:
            logger.error(f"Prompt template '{name}' missing variable: {e}")
            raise

    def _load_template(self, name: str) -> Template:
        if name not in self._cache:
            path = self._prompts_dir / f"{name}.tmpl"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {path}")
            content = path.read_text(encoding="utf-8")
            self._cache[name] = Template(content)
            logger.debug(f"Loaded prompt template: {name}")
        return self._cache[name]

    def reload(self, name: str = None) -> None:
        """清除缓存，强制重新加载（用于热更新Prompt）"""
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()
```

#### 3.8.3 模板文件示例（chapter_write.tmpl）

```
# 章节撰写任务

## 研究框架
核心问题：${topic}
框架配置：${framework_name}

## 你的章节角色
章节名：${section_name}
章节ID：${section_id}
章节角色：${section_role}

## 前文脉络
${preceding_summary}

## 已使用的数据指标（避免重复引用，如有冲突请标注）
${used_metrics_summary}

## 可用数据
${chapter_data}

## 撰写要求
1. 基于研究框架和前文脉络，撰写本章内容
2. 与前文逻辑衔接，避免重复前文已述内容
3. 使用尚未使用的数据点，避免数据重复引用
4. 每个核心判断必须有数据支撑，标注数据来源
5. 如发现与前文数据矛盾，明确标注并给出判断
6. 输出纯Markdown格式，不要包含HTML标签

## 自审检查（生成后立即执行）
完成撰写后，请自行检查：
- [ ] 格式是否规范（Markdown标题层级、列表格式、表格格式）
- [ ] 是否遗漏了关键数据点
- [ ] 数据数值是否与已使用的数据指标中的已有值矛盾
- [ ] 是否有大段与前文重复的内容
如发现问题，请直接修正后输出最终版本。

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{
  "title": "章节标题",
  "content": "Markdown格式的章节正文",
  "data_points_used": [{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}],
  "key_conclusions": ["结论1", "结论2"],
  "self_check_passed": true,
  "self_check_issues": []
}
```
```

#### 3.8.4 各Agent的Prompt调用改造

所有Agent通过构造函数注入 `PromptManager`，将 `f"""..."""` 替换为 `self._prompts.get(name, **kwargs)`：

**ChapterWriter 改造示例**：

```python
class ChapterWriter:

    def __init__(self, llm_skill, prompt_manager: PromptManager) -> None:
        self._llm = llm_skill
        self._prompts = prompt_manager

    async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
        chapter_spec = input_data.chapter_spec
        prompt = self._prompts.get(
            "chapter_write",
            topic=input_data.task_structure.get('topic', ''),
            framework_name=input_data.framework_config.get('name', '通用研究报告'),
            section_name=chapter_spec.get('section_name', ''),
            section_id=chapter_spec.get('section_id', ''),
            section_role=str(chapter_spec.get('section_role', '')),
            preceding_summary=input_data.preceding_summary,
            used_metrics_summary=input_data.used_metrics_summary,
            chapter_data=json.dumps(input_data.chapter_data, ensure_ascii=False, indent=2)
                         if input_data.chapter_data else '无可用数据',
        )
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, chapter_spec)

    async def rewrite(self, original_chapter: ChapterWriteOutput,
                      review_feedback, framework_config: Dict,
                      chapter_spec: Dict, preceding_summary: str) -> ChapterWriteOutput:
        issue_instructions = chr(10).join(
            f"- [{issue.severity}] {issue.description}\n  修正方向：{issue.suggestion}"
            for issue in review_feedback.issues
        )
        prompt = self._prompts.get(
            "chapter_rewrite",
            original_content=original_chapter.content,
            review_feedback=issue_instructions,
            section_name=chapter_spec.get('section_name', ''),
            section_id=chapter_spec.get('section_id', ''),
        )
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, chapter_spec)

    async def patch_data(self, chapter: ChapterWriteOutput,
                         patch_instructions: List[str],
                         framework_config: Dict) -> ChapterWriteOutput:
        prompt = self._prompts.get(
            "chapter_patch_data",
            chapter_content=chapter.content,
            patch_instructions=chr(10).join(f'- {inst}' for inst in patch_instructions),
            section_name=chapter.title,
            section_id=chapter.chapter_id,
        )
        raw_output = await self._call_llm(prompt)
        chapter_spec = {"section_id": chapter.chapter_id, "section_name": chapter.title}
        return self._parse_output(raw_output, chapter_spec)
```

**ChapterReviewAgent 改造示例**：

```python
class ChapterReviewAgent:

    def __init__(self, llm_skill, prompt_manager: PromptManager) -> None:
        self._llm = llm_skill
        self._prompts = prompt_manager

    async def review(self, input_data: ChapterReviewInput) -> ChapterReviewOutput:
        chapter_spec = input_data.chapter_spec
        prompt = self._prompts.get(
            "chapter_review",
            topic=input_data.topic,
            section_name=chapter_spec.get('section_name', ''),
            section_role=str(chapter_spec.get('section_role', '')),
            preceding_summary=input_data.preceding_summary,
            used_metrics_summary=input_data.used_metrics_summary,
            chapter_content=input_data.chapter_content,
            writer_self_check_issues=(
                chr(10).join(f'- {issue}' for issue in input_data.writer_self_check_issues)
                if input_data.writer_self_check_issues else '无'
            ),
        )
        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Chapter review LLM call failed: {result}")
        return self._parse_output(result["content"])
```

**GlobalReviewAgent 改造示例**：

```python
class GlobalReviewAgent:

    def __init__(self, llm_skill, prompt_manager: PromptManager) -> None:
        self._llm = llm_skill
        self._prompts = prompt_manager

    async def review(self, input_data: ReviewInput) -> ReviewOutput:
        prompt = self._prompts.get(
            "global_review",
            framework_name=input_data.framework_config.get('name', '通用研究报告'),
            report_summary=input_data.report_summary,
            conflicts_summary=input_data.conflicts_summary,
        )
        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            raise RuntimeError(f"Global review LLM call failed: {result}")
        return self._parse_output(result["content"])

    async def verify_issues(self, issues: List[ReviewIssue],
                            chapters: List[ChapterWriteOutput]) -> List[ReviewIssue]:
        if not issues:
            return []
        all_contexts = []
        for issue in issues:
            relevant_content = self._extract_relevant_chapters(issue, chapters)
            all_contexts.append(
                f"问题：{issue.description}\n位置：{issue.location}\n相关原文：\n{relevant_content[:2000]}"
            )
        issues_context = chr(10).join(
            f"### 问题{i+1}{chr(10)}{ctx}" for i, ctx in enumerate(all_contexts)
        )
        prompt = self._prompts.get("global_verify_issues", issues_context=issues_context)
        result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            return issues
        # ... 后续解析逻辑不变
```

**DataRepairAgent / ConflictResolver 改造示例**：

```python
class DataRepairAgent:

    def __init__(self, search_skill, web_scraper_skill, llm_skill,
                 prompt_manager: PromptManager) -> None:
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._llm = llm_skill
        self._prompts = prompt_manager

    async def repair_gap(self, gap: DataGap, topic: str) -> DataRepairResult:
        # ... 搜索和抓取逻辑不变 ...
        search_results_str = chr(10).join(
            f'--- 来源: {c["title"]} ({c["url"]}) ---{chr(10)}{c["content"]}'
            for c in scraped_contents
        )
        prompt = self._prompts.get(
            "data_extraction",
            metric=gap.metric,
            context=gap.context,
            topic=topic,
            search_results=search_results_str,
        )
        # ... 后续逻辑不变


class ConflictResolver:

    def __init__(self, llm_skill, search_skill=None, web_scraper_skill=None,
                 prompt_manager: PromptManager = None) -> None:
        self._llm = llm_skill
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._prompts = prompt_manager or PromptManager()

    async def _resolve_by_search(self, conflict: DataConflict, topic: str) -> DataConflictResolution:
        # ... 搜索逻辑不变 ...
        conflict_entries_str = chr(10).join(
            f'- 章节{e.get("chapter_id","")}：{e.get("value","")} {e.get("unit","")}（来源：{e.get("source","")}）'
            for e in conflict.entries
        )
        search_results_str = chr(10).join(
            f'- {r.get("title","")}: {r.get("body","")}' for r in results[:5]
        )
        prompt = self._prompts.get(
            "conflict_resolution",
            metric=conflict.metric,
            conflict_entries=conflict_entries_str,
            search_results=search_results_str,
        )
        # ... 后续逻辑不变
```

**ReportOrchestrator 中 _generate_exec_summary 改造示例**：

```python
async def _generate_exec_summary(self, chapters, task_structure, topic):
    # ... 构造 all_conclusions, conflict_descriptions 逻辑不变 ...
    prompt = self._prompts.get(
        "exec_summary",
        topic=topic,
        all_conclusions=chr(10).join(f'- {c}' for c in all_conclusions),
        conflict_descriptions=(
            chr(10).join(f'- {d}' for d in conflict_descriptions)
            if conflict_descriptions else '无'
        ),
    )
    result = await self._llm.execute(prompt=prompt, max_tokens=4096, temperature=0.7)
    if result.get("success"):
        return result["content"]
    return "执行摘要生成失败。"
```

#### 3.8.5 ReportOrchestrator 构造函数改造

```python
class ReportOrchestrator:

    def __init__(
        self,
        llm_skill,
        chapter_writer: ChapterWriter,
        chapter_reviewer: ChapterReviewAgent,
        global_reviewer: GlobalReviewAgent,
        data_repair_agent: DataRepairAgent,
        conflict_resolver: ConflictResolver,
        prompt_manager: PromptManager = None,
    ) -> None:
        self._llm = llm_skill
        self._chapter_writer = chapter_writer
        self._chapter_reviewer = chapter_reviewer
        self._global_reviewer = global_reviewer
        self._data_repair_agent = data_repair_agent
        self._conflict_resolver = conflict_resolver
        self._prompts = prompt_manager or PromptManager()
        self._data_registry = DataRegistry()
        self._task_structure: Dict[str, Any] = {}
        self._MAX_PRECEDING_SUMMARY_LENGTH = 3000
```

#### 3.8.6 设计决策：为什么用 `string.Template` 而非 Jinja2

| 维度 | `string.Template` | Jinja2 |
|------|-------------------|--------|
| 依赖 | 标准库，零依赖 | 需额外安装 |
| 复杂度 | `$var` 简单替换，Prompt不需要逻辑分支 | 支持循环/条件，但Prompt模板不需要 |
| 安全性 | 不会意外执行代码 | 模板注入风险（对本项目影响小） |
| 可读性 | 非技术人员可直接编辑 | 需了解Jinja语法 |

Prompt模板是纯文本替换场景，`string.Template` 完全够用且最简。

---

## 4. 与现有代码的集成方案

### 4.1 改造 orchestrator.py 调用点

```python
# src/core/orchestrator/orchestrator.py 第967行附近（在 aggregated.to_dict() 之后、
# _document_agent.execute() 之前）
#
# 重要前置条件：
# 1. routing_result 必须在当前方法作用域内可访问（research() 和
#    _execute_interactive_research() 方法中均在 line 750/1608 处生成并保留在作用域内）
# 2. aggregated 是 AggregationResult 对象（非 to_dict() 的字典输出）

from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent, ConflictResolver
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager

# 获取 Skill 实例（注意：_skill_registry.get() 返回 Skill 实例，非类）
llm_skill = self._skill_registry.get("llm_skill")
search_skill = self._skill_registry.get("search_skill")  # 注册名是 "search_skill"（非 "search"）
web_scraper_skill = self._skill_registry.get("web_scraper")

# 初始化 PromptManager（从 prompts/ 目录加载模板）
prompt_manager = PromptManager()

report_orchestrator = ReportOrchestrator(
    llm_skill=llm_skill,
    chapter_writer=ChapterWriter(llm_skill=llm_skill, prompt_manager=prompt_manager),
    chapter_reviewer=ChapterReviewAgent(llm_skill=llm_skill, prompt_manager=prompt_manager),
    global_reviewer=GlobalReviewAgent(llm_skill=llm_skill, prompt_manager=prompt_manager),
    data_repair_agent=DataRepairAgent(
        search_skill=search_skill,
        web_scraper_skill=web_scraper_skill,
        llm_skill=llm_skill,
        prompt_manager=prompt_manager,
    ),
    conflict_resolver=ConflictResolver(
        llm_skill=llm_skill,
        search_skill=search_skill,
        web_scraper_skill=web_scraper_skill,
        prompt_manager=prompt_manager,
    ),
    prompt_manager=prompt_manager,
)

# 获取真实的 task_structure
task_structure_dict = {}
# routing_result 在 research() 方法中从 self._routing_adapter.analyze() 获得，
# 在 _execute_interactive_research() 中从 self._routing_adapter.analyze() 获得。
# 两处均保留在当前方法作用域中。
if hasattr(routing_result, 'task_structure') and routing_result.task_structure:
    task_structure_dict = routing_result.task_structure.to_dict()

# 获取 framework_config（ResearchFrameworkConfig 无 to_dict() 方法，需手动序列化）
from src.core.research_framework_manager import get_framework_config
output_type_value = requirement.output_type.value if hasattr(
    requirement.output_type, 'value') else str(requirement.output_type)
framework_config_obj = get_framework_config(output_type_value)
framework_config_dict = {
    "name": framework_config_obj.name,
    "description": framework_config_obj.description,
    "agent_config": {
        "search": {
            "max_queries_per_section": framework_config_obj.agent_config.search.max_queries_per_section,
            "max_results_per_query": framework_config_obj.agent_config.search.max_results_per_query,
            "priority_sources": framework_config_obj.agent_config.search.priority_sources,
        },
        "analysis": {
            "depth": framework_config_obj.agent_config.analysis.depth,
            "focus_areas": framework_config_obj.agent_config.analysis.focus_areas,
            "metrics": framework_config_obj.agent_config.analysis.metrics,
        },
        "content": {
            "min_section_length": framework_config_obj.agent_config.content.min_section_length,
            "require_data_points": framework_config_obj.agent_config.content.require_data_points,
            "require_sources": framework_config_obj.agent_config.content.require_sources,
        },
    },
    "section_weights": framework_config_obj.section_weights,
}

# 传递 AggregationResult **对象**（非 to_dict() 输出）
# 原因：to_dict() 不序列化 layered_content 和 content_provenance
enriched_report = await report_orchestrator.generate_report(
    task_structure=task_structure_dict,
    framework_config=framework_config_dict,
    aggregated_result=aggregated,  # 直接传递 AggregationResult 对象
    topic=getattr(requirement, 'topic', ''),
    task_id=task_id,
)

# 使用 DocumentGenerationAgent 做格式转换（不变）
# enriched_report 是字典格式，与 AggregationResult.to_dict() 输出格式一致，
# 可直接传入 _document_agent
preview_result = await self._document_agent.execute({
    "action": "get_preview",
    "output_format": "html",
    "research_result": enriched_report,
    "task_id": task_id,
    "output_dir": str(output_dir_path),
})
```

### 4.2 文件结构

```
src/agents/fixed_agents/report_upgrade/
├── __init__.py
├── models.py              # 所有数据结构定义
├── data_registry.py       # DataRegistry
├── prompt_manager.py      # PromptManager：Prompt集中加载与渲染
├── prompts/               # Prompt模板文件（.tmpl，使用string.Template语法）
│   ├── chapter_write.tmpl
│   ├── chapter_rewrite.tmpl
│   ├── chapter_patch_data.tmpl
│   ├── chapter_review.tmpl
│   ├── global_review.tmpl
│   ├── global_verify_issues.tmpl
│   ├── data_extraction.tmpl
│   ├── conflict_resolution.tmpl
│   └── exec_summary.tmpl
├── chapter_writer.py      # ChapterWriter
├── chapter_reviewer.py    # ChapterReviewAgent
├── global_reviewer.py     # GlobalReviewAgent + serialize_report_for_review
├── data_repair.py         # DataRepairAgent + ConflictResolver
└── orchestrator.py        # ReportOrchestrator + RetryPolicy
```

---

## 5. 实施路线图

### Phase 1: 基础设施（1-2天）
- [ ] 创建 `src/agents/fixed_agents/report_upgrade/` 目录及 `prompts/` 子目录
- [ ] 实现 `models.py`（所有数据结构）
- [ ] 实现 `data_registry.py`
- [ ] 实现 `prompt_manager.py`（Prompt集中管理）
- [ ] 编写9个 `.tmpl` Prompt模板文件
- [ ] 在 `orchestrator.py` 中确保 task_structure 和 framework_config 传递到报告生成阶段

### Phase 2: ChapterWriter + ChapterReviewAgent（3-4天）
- [ ] 实现 `chapter_writer.py`（含LLM输出解析）
- [ ] 实现 `chapter_reviewer.py`
- [ ] 实现审查反馈→重写的闭环 + 版本对比保底

### Phase 3: GlobalReviewAgent + DataRepairAgent + ConflictResolver（3-4天）
- [ ] 实现 `global_reviewer.py`（含两步审查）
- [ ] 实现 `data_repair.py`
- [ ] 实现 patch_data 后重新审查 + preceding_summary 重建

### Phase 4: ReportOrchestrator 集成（2-3天）
- [ ] 实现 `orchestrator.py`
- [ ] 改造 `src/core/orchestrator/orchestrator.py` 调用点
- [ ] 实现检查点持久化

### Phase 5: 测试与调优（2-3天）
- [ ] 用真实数据（如 research_233fdf0e）做端到端测试
- [ ] Prompt 模板调优（直接编辑 .tmpl 文件，无需改代码）
- [ ] 性能测试

**总预估工期：12-17天**

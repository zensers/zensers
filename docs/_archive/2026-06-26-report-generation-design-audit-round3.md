# v2 设计文档第三轮审计

> 日期：2026-06-26
> 审计对象：v2 最终版（含前两轮21个缺陷修复后的版本）

## 审计结论

前两轮的致命/严重缺陷已全部修复，代码质量显著提升。本轮发现 **6个缺陷**（2 HIGH / 4 MEDIUM），均为实现细节层面的遗漏，无架构级问题。

| # | 等级 | 缺陷 |
|---|------|------|
| C1 | HIGH | 集成代码 `from ... import get_framework_config` 不存在——真实代码是 `ResearchFrameworkManager` 类的实例方法 |
| C2 | HIGH | `_restore_from_checkpoint` 是同步方法，含 `path.read_text()` 和 `glob()` 会阻塞事件循环 |
| C3 | MEDIUM | `_assemble_final_report` 返回 `"sources": []`，丢失所有来源信息，最终报告将无引用 |
| C4 | MEDIUM | ChapterReviewAgent Prompt 用 `section_name` 作"核心问题"，应为 `task_structure.topic` |
| C5 | MEDIUM | `DataPoint(**dp)` 在 LLM 输出含额外字段时 TypeError 崩溃 |
| C6 | MEDIUM | `_extract_and_validate_data_points` 正则仅匹配中文单位（亿元/万元），国际报告数据点全漏 |

---

## C1【HIGH】`get_framework_config` 导入不存在

**位置**：4.1 集成代码

**问题**：

```python
from src.core.research_framework_manager import get_framework_config
```

真实代码中 `ResearchFrameworkManager` 是一个类，`get_framework_config` 是其实例方法，不是模块级函数。此导入会抛 `ImportError`。

**修正**：

```python
from src.core.research_framework_manager import ResearchFrameworkManager
framework_manager = ResearchFrameworkManager()
framework_config_obj = framework_manager.get_framework_config(output_type_value)
```

---

## C2【HIGH】`_restore_from_checkpoint` 同步文件IO阻塞事件循环

**位置**：3.7 ReportOrchestrator

**问题**：

`_checkpoint_chapter` 已修正为 `async def` + `asyncio.to_thread`，但 `_restore_from_checkpoint` 仍是 `@staticmethod` 同步方法，内含 `path.read_text()` 和 `checkpoint_dir.glob()` 调用，在 async 上下文中会阻塞。

**修正**：

```python
@staticmethod
async def _restore_from_checkpoint(task_id: str):
    checkpoint_dir = Path("data") / task_id / "checkpoints"
    if not checkpoint_dir.exists():
        return None

    chapters = []
    registry_snapshot = {}
    
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
    
    for data in checkpoint_data_list:
        chapter = ChapterWriteOutput(
            chapter_id=data["chapter_id"],
            title=data["title"],
            content=data["content"],
            data_points_used=[DataPoint(**dp) for dp in data.get("data_points_used", [])],
            key_conclusions=data.get("key_conclusions", []),
            self_check_passed=data.get("self_check_passed", True),
            self_check_issues=data.get("self_check_issues", []),
        )
        chapters.append(chapter)
        registry_snapshot = data.get("data_registry_snapshot", {})

    return (chapters, registry_snapshot) if chapters else None
```

---

## C3【MEDIUM】`_assemble_final_report` 丢失所有来源信息

**位置**：3.7 `_assemble_final_report`

**问题**：

返回值中 `"sources": []`，但真实 `research_result_cache.json` 的 sources 列表包含所有引用来源（URL、标题、agent_id）。丢失来源会导致最终报告无引用/参考列表。

**修正**：

```python
@staticmethod
def _assemble_final_report(
    chapters: List[ChapterWriteOutput],
    exec_summary: str,
    review: ReviewOutput,
    topic: str,
    original_sources: List[Dict[str, Any]] = None,  # 新增：从聚合结果传入原始来源
) -> Dict[str, Any]:
    sections = []
    all_sources = list(original_sources) if original_sources else []
    
    for ch in chapters:
        sections.append({
            "id": ch.chapter_id,
            "title": ch.title,
            "content": ch.content,
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
```

调用处传入原始来源：

```python
# 在 generate_report 中：
original_sources = getattr(aggregated_result, 'sources', [])
return self._assemble_final_report(chapters, exec_summary, review, topic, original_sources)
```

---

## C4【MEDIUM】ChapterReviewAgent Prompt 核心问题字段错误

**位置**：3.4 ChapterReviewAgent.review()

**问题**：

```python
核心问题：{chapter_spec.get('section_name', '')}
```

`section_name` 只是章节名（如"市场规模"），不是研究核心问题。审查Agent无法基于正确的核心问题评估章节是否完整回答了研究问题。

**修正**：

ChapterReviewInput 需增加 `topic` 字段，Prompt 中使用 `topic` 而非 `section_name`：

```python
@dataclass
class ChapterReviewInput:
    framework_config: Dict[str, Any]
    chapter_spec: Dict[str, Any]
    chapter_content: str
    preceding_summary: str
    used_metrics_summary: str
    topic: str = ""                              # 新增：研究主题/核心问题
    writer_self_check_issues: List[str] = field(default_factory=list)
```

Prompt 中：

```markdown
## 研究框架
核心问题：{input_data.topic}
章节名：{chapter_spec.get('section_name', '')}
章节角色：{chapter_spec.get('section_role', '')}
```

调用处传入 topic：

```python
ChapterReviewInput(
    ...,
    topic=task_structure.get('topic', ''),
)
```

---

## C5【MEDIUM】`DataPoint(**dp)` 在 LLM 输出含额外字段时崩溃

**位置**：3.3 ChapterWriter._parse_output()

**问题**：

LLM 可能输出 `{"metric": "...", "value": "...", "unit": "...", "source": "...", "year": 2025}`，`DataPoint(**dp)` 会因 `year` 不是 DataPoint 字段而抛 TypeError。

**修正**：

```python
DATAPOINT_FIELDS = {"metric", "value", "unit", "source", "chapter_id", "confidence"}

# 在 _parse_output 中：
data_points_used=[
    DataPoint(**{k: v for k, v in dp.items() if k in DATAPOINT_FIELDS})
    for dp in data.get("data_points_used", [])
],
```

同样修正 `_restore_from_checkpoint` 中的 `DataPoint(**dp)`。

---

## C6【MEDIUM】数据点正则仅匹配中文单位

**位置**：3.7 `_extract_and_validate_data_points`

**问题**：

```python
pattern = re.compile(r'(\d[\d,.]*)\s*(亿元|万元|元|%|亿美元|千万|百万|万亿美元)')
```

仅匹配中文单位。国际报告中的 "billion USD"、"million"、"trillion"、"thousand" 等全部漏提取。

**修正**：

```python
pattern = re.compile(
    r'(\d[\d,.]*)\s*'
    r'(亿元|万元|元|%|亿美元|千万|百万|万亿美元'
    r'|billion|million|trillion|thousand|percent|%\s*)',
    re.IGNORECASE
)
```

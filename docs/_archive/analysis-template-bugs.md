# 问题分析报告

## 问题 1：后端反复加载全部模板

### 现象

每次 `/template` 或执行研究时，后端都会加载 `config/templates/` 下全部 13 个 YAML 模板文件。

### 根因

`research_api.py:2513` 的 `_get_section_details_for_type()` 方法创建一个**新的** `TemplateLoader()` 实例，不引用模块级全局单例 `_template_loader`：

```python
def _get_section_details_for_type(self, output_type: str):
    from src.core.orchestrator.smart_clarifier import OutputType, TemplateLoader
    loader = TemplateLoader()  # ← 新实例！_loaded = False，总是读磁盘
```

而 `smart_clarifier.py:341` 已存在全局单例：

```python
_template_loader = TemplateLoader()  # ← 全局单例，有 _loaded 缓存标记
```

### 影响

- 每次 `quick_start()`（含 `auto_confirm` 路径）都读一遍 13 个 YAML 文件
- 执行研究时 orchestrator 新建 SmartClarifier，引用的全局单例可能未缓存

### 修复方案

`_get_section_details_for_type()` 改用全局单例：

```python
def _get_section_details_for_type(self, output_type: str):
    from src.core.orchestrator.smart_clarifier import OutputType, _template_loader
    templates = _template_loader.get_templates_by_type(OutputType(output_type))
    if templates:
        return templates[0].sections
```

---

## 问题 2：确认研究后创建新 session

### 现象

用户在 conversation session A 中定制模板，点击"开始研究"后，创建了一个新的 research session B，对话历史和模板定制状态丢失。

### 根因

`handleStartResearch` → `quickStartResearch` → `api.quickStart` → 后端 `quick_start(auto_confirm=True)` **总是生成新 UUID**：

```python
# research_api.py:2326
task_id = f"research_{uuid.uuid4().hex[:8]}"
session_manager.create(task_id, session_data)  # 新 session
```

而正常对话流的确认路径 (`interact()` Step 6) **复用已有 session_id**：

```python
# research_api.py:1519 — reuses existing session_id
executor.execute(session_id, final_plan, session_manager)
```

### 两条路径对比

| 路径 | Session 创建 | 对话历史 |
|------|-------------|----------|
| 正常对话 → 确认研究 | 创建一次 `ses_xxx`，确认时复用 | ✅ 保留 |
| `/template` → 对话 → 开始研究 | `startResearch` 创建 `ses_xxx` + `quickStart` 创建 `research_xxx` | ❌ 分到两个 session |

### 修复方案

不再通过 `quickStartResearch` 创建新 session，而是在现有 chat session 中触发执行：

```
当前：
  startResearch("使用模板...") → session A (对话)
  → 用户点"开始研究"
  → quickStartResearch() → quick_start() → session B (新会话)

修复：
  startResearch("使用模板...") → session A (对话)
  → 用户点"开始研究"
  → 在 session A 内部触发交互确认 → executor.execute(session_A_id, final_plan)
  → 研究在 session A 中执行
```

具体实现：`handleStartResearch` 不再调 `quickStartResearch`，改为向后端现有 session 发送确认指令，让后端走 `interact()` Step 6 路径，复用已有 session。

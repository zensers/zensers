# 修复方案评估报告 v2

> 基于 deep review 修正，补充 2 个实现缺口、纠正 1 个根因误判、调整 1 个风险评级

---

## 问题 1：研究标题被污染（P0）

### 根因

`handleStartResearch` 把 `collectTemplateContext()` 的多行输出当作 `user_input` 传给后端，后端 `final_plan["topic"] = user_input`，导致标题包含换行和模板上下文文本。

### 修复方案（含实现缺口补全）

**前端 `handleStartResearch`：**只传 topic 作为研究主题，context 拆出单独传：

```typescript
// web/src/hooks/useResearch.ts
const topic = useResearchStore.getState().researchTopic || active?.name || '';
const context = collectTemplateContext(active, allMessages, topic);

await quickStartResearch(topic, active.id, undefined, undefined, {
  templateContext: context,     // ← 单独传，不作为 user_input
  ...active.parameters,
  autoConfirm: true,
});
```

**前端 `api.ts`：**`templateContext` 在 `options.parameters` 内部，需在循环前剥离并单独发送：

```typescript
// web/src/lib/api.ts quickStart() 中，parameters 循环之前
const { templateContext: _ctx, ...restParams } = options?.parameters || {};
if (_ctx) formData.append('template_context', String(_ctx));
// 然后用 restParams 走后续循环
```

**后端 `main.py`：**端点签名增加 `template_context: Optional[str] = Form(None)`，并传递：

```python
# main.py:335 — 追加参数传递
return await research_api.quick_start(
    user_input=user_input, template_id=template_id,
    user_id=user_id, llm_config=llm_config,
    custom_params=custom_params if custom_params else None,
    auto_confirm=auto_confirm.lower() == "true",
    template_context=template_context,     # ← 追加
)
```

**后端 `research_api.py`：**`quick_start()` 入参加 `template_context`，并从它取 LLM 提取输入：

```python
async def quick_start(self, user_input, template_id, ...
                      auto_confirm=False, template_context: Optional[str] = None):
    ...
    if auto_confirm:
        # template_context 优先，保持 user_input 干净
        extraction_context = template_context or user_input
        extracted = await self._extract_params_from_context(extraction_context, output_type, params)
```

### 影响范围

| 文件 | 修改 | 行数 |
|------|------|------|
| `web/src/hooks/useResearch.ts` | `handleStartResearch` 传参调整 | 3 |
| `web/src/lib/api.ts` | `templateContext` option 类型 + formData 发送 | 3 |
| `src/api/main.py` | 端点签名 + handler 传递到 `research_api.quick_start()` | 3 |
| `src/api/research_api.py` | `quick_start()` 入参加 `template_context` + 提取逻辑 | 4 |

**合计约 13 行代码。风险低，隔离在 template 分支内。**

---

## 问题 2：报告语言混杂（P1）

### 根因（纠正）

> 文档 v1 误判为"Document Generation Agent prompt 问题"。实际根因是多处英文源汇入结果，主文档生成路径完全不用 LLM。

**语言混杂的四个来源：**

| 来源 | 文件位置 | 内容 | 语言 |
|------|---------|------|------|
| section aspects | `research_api.py:2289-2306` | "Company Overview", "Financial Analysis" | 英文 |
| LLM 参数提取 prompt | `research_api.py:2471` | "Extract research parameters from user conversation" | 英文 |
| HTML 模板 | `word_default.html` | 无 `lang` 属性，无语言声明 | 未指定 |
| revision prompts | `document_generation_agent.py:1650-1723` | 中文但无显式输出语言指令 | 中文（隐含） |

### 修复方案

**1. aspects 中文化（或双语）：**

```python
# research_api.py: TEMPLATES — 仅示例 industry_research，实际需修改全部 5 个 template
"industry_research": {
    "output_type": "industry_report",
    "aspects": ["市场规模", "竞争格局", "产业链分析", "发展趋势", "政策环境", "投资机会"],
},
```

影响：`plan.aspects` 和 `session_data.aspects` 均为中文。后端 orchestrator 用 aspects 生成章节标题时为中文。

**2. `_extract_params_from_context` prompt 保持 JSON 纯输出：**

该 prompt 有明确的 "Return ONLY a JSON object" 约束，追加语言指令可能导致 LLM 输出中文 key 或附加说明文字，破坏 `json.loads()`。**此点不改。**

**3. revision prompts 追加语言指令：**

```python
# document_generation_agent.py
prompt += "\n请使用中文输出所有内容。"
```

**4. HTML 模板声明语言：**

```html
<!-- word_default.html -->
<html lang="zh-CN">
```

### 影响范围

| 文件 | 修改 | 行数 | 风险 |
|------|------|------|------|
| `src/api/research_api.py` | aspects 中文化、prompt 加语言指令 | 20 | 低（隔离在 TEMPLATES 和 prompt） |
| `src/agents/.../document_generation_agent.py` | revision prompt 加语言指令 | 1 | 低 |
| `config/document_templates/word_default.html` | 加 lang 属性 | 1 | 趋近于零 |

**合计约 22 行代码。**

---

## 问题 3：HTML 报告存储目录（P2）

### 目标

所有 HTML 报告集中存储在 `data/html_reports/` 下。

### 涉及文件修改

| # | 文件 | 行号 | 当前路径 | 修改为 |
|---|------|------|---------|--------|
| 1 | `src/api/main.py` | 92-94 | `Path("data/previews")` | `Path("data/html_reports")` |
| 2 | `src/api/research_api.py` | ~2548 | `Path("data/previews")` | `Path("data/html_reports")` |
| 3 | `src/api/research_executor.py` | ~283 | `Path("data/previews")` | `Path("data/html_reports")` |
| 4 | `src/core/orchestrator/orchestrator.py` | ~1812 | `Path("data/previews")` | `Path("data/html_reports")` |
| 5 | `src/agents/.../document_generation_agent.py` | ~1789 | `doc_dir.parent / "previews"` | `doc_dir.parent / "html_reports"` |

### 风险评级更新

> 文档 v1 将"前端预览 URL 未全部更新"评为中风险。
> **实际：前端零处硬编码 `/api/v1/previews/`，预览 URL 全部从后端 API 响应中获取。前端无需修改。**

**风险：低。**

### 过渡期兼容

采用中心化双写适配器，替代分散在 5 个文件中的独立路径操作：

```python
# 新建 src/core/preview_storage.py
import shutil
from pathlib import Path

class PreviewStorage:
    NEW_DIR = Path("data/html_reports")
    OLD_DIR = Path("data/previews")

    @classmethod
    def write(cls, task_id: str, html: str):
        cls.NEW_DIR.mkdir(parents=True, exist_ok=True)
        cls.OLD_DIR.mkdir(parents=True, exist_ok=True)
        (cls.NEW_DIR / f"{task_id}.html").write_text(html, encoding="utf-8")
        (cls.OLD_DIR / f"{task_id}.html").write_text(html, encoding="utf-8")  # 过渡期兼容

    @classmethod
    def copy_file(cls, task_id: str, source_path: Path):
        """Copy an existing file to both new and old dirs."""
        for d in [cls.NEW_DIR, cls.OLD_DIR]:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_path), str(d / f"{task_id}.html"))

    @classmethod
    def path(cls, task_id: str) -> Path:
        return cls.NEW_DIR / f"{task_id}.html"
```

5 处文件统一调用 `PreviewStorage.write(task_id, html)` 和 `PreviewStorage.path(task_id)`。

**数据迁移：**

```powershell
New-Item -ItemType Directory -Path data/html_reports -Force
Copy-Item -Path "data/previews/*" -Destination "data/html_reports/"
```

### 影响范围

每处修改涉及：路径替换 + URL 构造更新 + (orchestrator) copy2 适配。

| 文件 | 修改 | 行数 |
|------|------|------|
| `src/core/preview_storage.py`（新建） | 中心化存储类 + `copy_file()` 方法 | 25 |
| `src/api/main.py` | 路径替换 (L94) + URL 路由 (L499,504) | 5 |
| `src/api/research_api.py` | 路径替换 + `preview_url` 拼接 | 3 |
| `src/api/research_executor.py` | 路径替换 | 2 |
| `src/core/orchestrator/orchestrator.py` | 路径替换 + `shutil.copy2` 改为 `PreviewStorage.copy_file()` | 3 |
| `src/agents/.../document_generation_agent.py` | 路径替换 | 2 |

**合计约 40 行代码。**

---

## 实施顺序

| 优先级 | 问题 | 工作量 | 前置依赖 | 收益 |
|--------|------|--------|---------|------|
| P0 | 标题污染 | ~13 行 | 无 | 消除排版错乱，确保标题正确 |
| P1 | 语言混杂 | ~22 行 | 无 | 报告全中文，提升可用性 |
| P2 | 存储目录 | ~40 行 | P0/P1 无依赖 | 非功能改进，可延后 |

---

## 确认项

- [ ] **P0 实现缺口**：后端 `main.py` 端点签名加 `template_context` + handler 传递 + `research_api.quick_start()` 入参 — 共 3 处，约 13 行
- [ ] **P1 根因补全**：aspects 中文化 + 1 个 prompt（revision）加语言指令 + HTML 模板加 `lang` — 约 22 行
- [ ] **P1 字符串匹配风险**：检查 orchestrator/agent 是否对 aspects 做英文字符串匹配（如 `if aspect == "Company Overview"`），如有则改为 ID 匹配
- [ ] **P2 路径一致性**：5 处文件统一调用 `PreviewStorage`，不各自硬编码路径
- [ ] **P2 copy2 适配**：`orchestrator.py:1812` 的 `shutil.copy2` 改为 `PreviewStorage.copy_file()`

# 质检反馈交互修订系统 — 设计方案

> 日期: 2026-06-01
> 状态: 设计中
> 范围: 报告研究完成后的质检展示、用户交互、内容修订、预览刷新全链路
> 核心原则: **质检让问题可见，修订让对话来做**

---

## 1. 背景与问题

当前系统在报告研究完成后，质检信息无法被用户感知，更无法交互：

| 断点 | 现状 | 影响 |
|------|------|------|
| 前端SSE | `sse.ts` `subscribeSession()` 只监听 `chat_response` / `agent_message`，不监听 `quality_result` / `section_quality` | 质检分数被静默丢弃 |
| 前端组件 | 无质量面板 | 用户看不到章节评分 |
| 后端API | `handle_feedback()` (L3308) 只支持 `confirm`/`revise`，且 `revise` 为空实现 | 无质检专用操作 |
| 修订闭环 | `QualityCheckAgent.check_by_sections()` (L873) fire-and-forget | 无"修订→重检→刷新"循环 |
| 预览刷新 | 修订后无自动刷新 | 用户不知道修订是否生效 |
| 排版风险 | 修订只改 markdown 源文件 | HTML 预览可能排版错乱 |

## 2. 设计目标

1. **可见**: 研究完成后前端实时展示分章节评分、整体评分、问题列表
2. **可对话**: 质检问题通过对话发起修订，用户可精细控制修订方向和范围
3. **可观测**: 每次修订后预览自动刷新，评分实时更新
4. **可恢复**: 排版错乱时可一键回滚到修订前版本
5. **有终态**: 明确"确认交付"出口，避免无限修订循环

## 3. 整体流程

```
研究报告完成
    │
    ▼
┌─────────────────────────┐
│  阶段A: 质检展示         │  前端接收 quality_result / section_quality SSE
│  - 整体评分              │  显示质量面板 + 各章节评分卡
│  - 分章节评分            │  章节导航条高亮有问题的章节
│  - 问题列表              │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段B: 对话式修订       │  用户点击 issue → 问题详情填入聊天输入框
│  - 用户点击 issue        │    用户可补充具体要求后提交
│  - 系统预填修订指令      │    走现有 _llm_converse → _handle_v2_revision 链路
│  - 用户微调后发送        │    RevisionService 执行修订
│  - 对话驱动修订执行      │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段C: 修订后刷新       │  修订完成
│  - 重新生成预览          │    SSE 推送 preview_refresh 刷新预览
│  - 重检受影响章节        │    SSE 推送新的 section_quality
│  - 更新评分              │    修订提示条: 如排版异常可[一键回滚]
│  - 推送评分更新          │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段D: 确认交付         │  用户满意后点击"确认交付"
│  - 生成最终文档          │  生成 DOCX/PPTX/PDF
│  - 退出修订模式          │  关闭质量面板
└─────────────────────────┘
```

## 4. 数据模型

### 4.1 会话状态扩展

在 `session` dict 中新增 `quality_state`。session 由 `SessionManager.get_instance().get(session_id)` 返回，类型为 `PersistentSessionDict`（继承 `dict`，每次 `__setitem__` 自动持久化到 `data/sessions/{session_id}.json`）。

```python
# src/core/quality/quality_state.py

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel


class QualityIssue(BaseModel):
    id: str                                    # 基于 section+type+message 的稳定哈希
    type: Literal["completeness", "accuracy", "consistency", "format", "hallucination"]
    severity: Literal["high", "medium", "low"]
    message: str
    section: str
    state: Literal["open", "dismissed", "revising", "resolved", "max_retries_reached"] = "open"


class SectionScore(BaseModel):
    score: float
    status: Literal["passed", "warning"]
    issues: List[QualityIssue] = []


class VersionInfo(BaseModel):
    id: str
    created_at: str
    html_path: str
    md_path: str
    quality_state_snapshot: dict
    overall_score: float
    label: str


class QualityState(BaseModel):
    phase: Literal["reviewing", "revising", "confirmed"] = "reviewing"
    overall_score: float = 0.0
    overall_status: Literal["passed", "warning"] = "warning"
    section_scores: Dict[str, SectionScore] = {}
    version_stack: List[VersionInfo] = []
    current_version: str = "v0"
```

session 中存储方式：

```python
session["quality_state"] = quality_state.model_dump()
```

### 4.2 Issue ID 稳定生成

基于 `section + type + message` 哈希，确保重检时同一问题保持同一 ID：

```python
# src/core/quality/quality_state.py

import hashlib

def generate_issue_id(section: str, issue_type: str, message: str) -> str:
    raw = f"{section}|{issue_type}|{message}"
    hash_hex = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"q-{hash_hex}"
```

重检时，新返回的 issue 与已有 issue 通过 ID 匹配：
- ID 相同且 state 为 `resolved` → 保持 `resolved`
- ID 相同且 state 为 `dismissed` → 保持 `dismissed`
- ID 相同且 state 为 `open` → 保持 `open`
- ID 不存在 → 新增为 `open`

### 4.3 Issue 状态机

```
open ──→ revising ──→ resolved
  │                       │
  └──→ dismissed          └──→ open (回滚后)
          │
          └──→ open (重新打开)
```

| 状态 | 含义 | 用户可操作 |
|------|------|-----------|
| `open` | 待处理 | 发起修订对话 / 忽略 |
| `revising` | 对话修订中（修订消息已发送） | 继续对话 |
| `resolved` | 已修复（重检后评分改善） | 回滚 |
| `dismissed` | 用户选择忽略 | 重新打开 |

### 4.4 版本快照

每次修订执行前，创建快照到 `data/snapshots/{session_id}/`：

```
data/snapshots/{session_id}/v0.html
data/snapshots/{session_id}/v0.md
data/snapshots/{session_id}/v0_quality.json
data/snapshots/{session_id}/v1.html
data/snapshots/{session_id}/v1.md
data/snapshots/{session_id}/v1_quality.json
```

快照包含三个文件：
- `v{N}.html` — HTML 预览文件（从 `data/html_reports/{task_id}.html` 复制）
- `v{N}.md` — Markdown 源文件
- `v{N}_quality.json` — 该版本时的 `quality_state` 快照

## 5. API 设计

### 5.1 质检操作端点

#### `POST /api/v1/research/quality/action` (JSON body)

仅处理质检面板上的轻量操作，修订走现有对话链路：

| action | 必需参数 | 可选参数 | 说明 |
|--------|----------|----------|------|
| `quality_dismiss` | `session_id`, `issue_id` | — | 标记 issue 为忽略 |
| `quality_reopen` | `session_id`, `issue_id` | — | 重新打开已忽略的 issue |
| `quality_rollback` | `session_id`, `version_id` | — | 回滚到指定版本 |
| `quality_confirm` | `session_id` | — | 确认交付 |
| `quality_recheck` | `session_id` | `section_name` | 重检指定章节或全报告 |

请求体示例：

```json
{
  "session_id": "sess-abc",
  "action": "quality_dismiss",
  "issue_id": "q-a1b2c3d4"
}
```

Pydantic 模型定义：

```python
# src/api/research_api.py 新增

from typing import Optional
from pydantic import BaseModel

class QualityActionRequest(BaseModel):
    session_id: str
    action: Literal["quality_dismiss", "quality_reopen", "quality_rollback", "quality_confirm", "quality_recheck"]
    issue_id: Optional[str] = None
    version_id: Optional[str] = None
    section_name: Optional[str] = None
```

### 5.2 查询端点

#### `GET /api/v1/research/quality/{session_id}`

获取当前完整质检状态。返回 `QualityState.model_dump()` 的 JSON。

### 5.3 对话式修订的集成

用户在质检面板点击 issue 后，前端将问题描述预填入聊天输入框：

```
【质检问题】核心财务指标章节: 章节结构不完整，缺少分析框架（当前1/7项）
请帮我修订这部分内容，补充完整的分析框架。
```

用户可在此基础上补充具体要求后发送。发送走现有 `POST /api/v1/research/interact` 端点，后端 `_llm_converse()` (L909) 处理对话，识别到修订意图后调用 `_handle_v2_revision()` (L3911)。

修订完成后，后端自动：
1. 重新生成 HTML 预览（通过 `PreviewGenerator`）
2. 对修改的章节调用 `QualityCheckAgent.check_by_sections()` 重检
3. 更新 `session["quality_state"]`
4. SSE 推送 `preview_refresh` + `section_quality`

### 5.4 对话修订与质检状态的联动

在 `_handle_v2_revision()` (L3911) 执行修订前，增加质检状态联动：

```python
# src/api/research_api.py — _handle_v2_revision() 内新增

quality_state_data = session.get("quality_state", {})
if quality_state_data and quality_state_data.get("phase") in ("reviewing", "revising"):
    from src.core.quality.quality_snapshot_manager import QualitySnapshotManager
    snap_mgr = QualitySnapshotManager()
    await snap_mgr.create_snapshot(session_id, html_path, md_path, quality_state_data)
    _mark_related_issues_revising(session, section, adjustment)
```

修订完成后：

```python
if result_success and quality_state_data:
    modified_sections = [section] if section else None
    await self._post_revision_recheck(session, modified_sections)
```

## 6. SSE 事件扩展

### 6.1 新增事件类型

在 `src/core/session_streamer.py` 的 `SessionSSEEventType` (L33) 中新增：

```python
class SessionSSEEventType(str, Enum):
    """Session SSE event types"""
    CHAT_RESPONSE = "chat_response"
    AGENT_MESSAGE = "agent_message"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    QUALITY_RESULT = "quality_result"        # 已有
    SECTION_QUALITY = "section_quality"      # 已有
    PREVIEW_REFRESH = "preview_refresh"      # 新增
    QUALITY_CONFIRMED = "quality_confirmed"  # 新增
```

### 6.2 新增 push classmethod

在 `SessionStreamer` 类中新增（与现有 `push_quality_result` / `push_section_quality` 同级）：

```python
# src/core/session_streamer.py

@classmethod
def push_preview_refresh(cls, session_id: str, preview_url: str, version_id: str):
    cls._notify_subscribers(session_id, SessionSSEEventType.PREVIEW_REFRESH, {
        "session_id": session_id,
        "preview_url": preview_url,
        "version_id": version_id,
        "timestamp": datetime.now().isoformat(),
    })

@classmethod
def push_quality_confirmed(cls, session_id: str, final_document_path: str):
    cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, {
        "session_id": session_id,
        "final_document_path": final_document_path,
    })
```

### 6.3 前端事件监听

`web/src/lib/sse.ts` 的 `subscribeSession()` (L171) 当前只监听 `chat_response` 和 `agent_message`。需扩展为同时监听 `quality_result`、`section_quality`、`preview_refresh`、`quality_confirmed`：

```typescript
// web/src/lib/sse.ts — subscribeSession() 内新增

// Handle quality_result events
eventSource.addEventListener('quality_result', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionQualityCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream quality_result parse error:', e);
  }
});

// Handle section_quality events
eventSource.addEventListener('section_quality', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionSectionQualityCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream section_quality parse error:', e);
  }
});

// Handle preview_refresh events
eventSource.addEventListener('preview_refresh', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionPreviewRefreshCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream preview_refresh parse error:', e);
  }
});

// Handle quality_confirmed events
eventSource.addEventListener('quality_confirmed', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionQualityConfirmedCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream quality_confirmed parse error:', e);
  }
});
```

对应新增回调类型和存储：

```typescript
// web/src/lib/sse.ts — SSEManager 类新增

type QualityResultCallback = (data: any) => void;
type SectionQualityCallback = (data: any) => void;
type PreviewRefreshCallback = (data: any) => void;
type QualityConfirmedCallback = (data: any) => void;

private sessionQualityCallbacks: Map<string, Set<QualityResultCallback>> = new Map();
private sessionSectionQualityCallbacks: Map<string, Set<SectionQualityCallback>> = new Map();
private sessionPreviewRefreshCallbacks: Map<string, Set<PreviewRefreshCallback>> = new Map();
private sessionQualityConfirmedCallbacks: Map<string, Set<QualityConfirmedCallback>> = new Map();
```

`subscribeSession()` 签名扩展：

```typescript
subscribeSession(
  sessionId: string,
  onChatResponse: ChatResponseCallback,
  onAgentMessage?: AgentMessageCallback,
  onQualityResult?: QualityResultCallback,
  onSectionQuality?: SectionQualityCallback,
  onPreviewRefresh?: PreviewRefreshCallback,
  onQualityConfirmed?: QualityConfirmedCallback,
): () => void;
```

## 7. 前端组件设计

### 7.1 QualityPanel

位置: 报告预览右侧面板，研究完成后自动展开。

**定位**: 信息展示面板，不是操作面板。修订操作通过对话完成。

```
┌─────────────────────────────────────────┐
│  质量评分                            [✕] │
├─────────────────────────────────────────┤
│  ┌───────────────┐                       │
│  │   整体评分     │   72.5 / 100          │
│  │   状态: ⚠ 警告│                       │
│  └───────────────┘                       │
│                                         │
│  章节:                                   │
│  ┌─────────────────────────────────┐    │
│  │ 核心财务指标  52.0 ⚠            │    │
│  │  ● [medium] 章节结构不完整      │    │
│  │    [发起修订] [忽略]            │    │
│  ├─────────────────────────────────┤    │
│  │ 研发投入      88.0 ✓            │    │
│  ├─────────────────────────────────┤    │
│  │ 供应链        85.0 ✓            │    │
│  │  ○ [low] 数据密度偏低          │    │
│  │    [忽略]                      │    │
│  └─────────────────────────────────┘    │
│                                         │
│  ┌──────────┐ ┌──────────┐             │
│  │ 版本回滚  │ │ 确认交付  │             │
│  └──────────┘ └──────────┘             │
└─────────────────────────────────────────┘
```

### 7.2 IssueRow

每条 issue 的交互行：

```
● [medium] 章节结构不完整，缺少分析框架（当前1/7项）
  ┌──────────┐ ┌──────┐
  │ 发起修订  │ │ 忽略  │
  └──────────┘ └──────┘
```

**「发起修订」行为**: 点击后将 issue 描述填入聊天输入框，用户可补充要求后发送。

状态变化：

| 当前状态 | 发起修订 | 忽略 | 回滚 |
|---------|---------|------|------|
| open | → 聊天输入框预填 | → dismissed | — |
| revising | 继续对话 | — | — |
| resolved | — | — | → open (恢复旧版本) |
| dismissed | — | → open | — |

### 7.3 修订提示条

修订完成、预览刷新后，在预览区域顶部显示临时提示条：

```
┌────────────────────────────────────────────────────────┐
│ ✓ 修订完成，评分: 52.0 → 85.0   如排版异常 [一键回滚] │
└────────────────────────────────────────────────────────┘
```

提示条 5 秒后自动消失，或用户手动关闭。点击「一键回滚」回滚到上一版本。

### 7.4 章节导航条

在预览 iframe 外侧（上方）增加章节导航条：

```
┌──────────────────────────────────────────────────────────────┐
│  [核心财务指标 ⚠]  [研发投入 ✓]  [供应链 ✓]  [竞争格局 ✓]   │
└──────────────────────────────────────────────────────────────┘
│  ┌──────────────────────────────────────────────────────┐    │
│  │                  报告预览 iframe                       │    │
│  └──────────────────────────────────────────────────────┘    │
```

实现要求：
- 预览生成时，每个章节的 HTML 加锚点 `id="section-{sanitized_name}"`
- 点击导航条中的章节名，iframe 滚动到对应锚点
- 有 warning 的章节显示 ⚠ 标记

> **关于 iframe 内高亮**: 完整的 iframe 内高亮交互需要跨 iframe 通信、样式注入，
> 实现复杂度高。首期采用章节导航条 + 质检面板双栏方案。

### 7.5 VersionTimeline

版本时间线（折叠在面板底部，展开后显示）：

```
v0 (初始版本)  72.5分  ──●── v1 (修订后) 85.0分
                         │
                       [回滚到v0]
```

### 7.6 确认交付

确认交付前，显示待处理 issue 清单：

```
┌──────────────────────────────────────────────┐
│  确认交付                                     │
│                                              │
│  当前仍有 2 个待处理问题：                     │
│  ● [medium] 供应链: 数据密度偏低 (已忽略)     │
│  ● [low] 竞争格局: 格式不规范 (已忽略)        │
│                                              │
│  ⚠ 忽略的问题可能影响报告质量                  │
│                                              │
│  [仍要交付]  [继续修订]                        │
└──────────────────────────────────────────────┘
```

## 8. 后端修订流程

### 8.1 对话式修订（核心流程）

```
用户点击 issue "发起修订"
    │
    ▼
前端将 issue 描述填入聊天输入框
用户补充具体要求后发送
    │
    ▼
POST /api/v1/research/interact  {response: {user_message: "【质检问题】..."}}
    │
    ▼
后端 ResearchAPI._llm_converse() (L909) 处理对话
    │
    ├─ 识别修订意图 → _handle_v2_revision() (L3911)
    │   │
    │   ▼
    │   1. 创建版本快照（QualitySnapshotManager.create_snapshot()）
    │   2. 标记关联 issue 为 revising
    │   3. RevisionExecutor.handle_feedback() (L3935) 执行修订
    │      - 定位章节 (SectionLocator)
    │      - 生成修订内容 (content_generator callback)
    │      - 应用修订 (ContentApplier)
    │   4. 重新生成 HTML 预览 (PreviewGenerator.generate_html_preview_from_data())
    │   5. 对修改的章节调用 QualityCheckAgent.check_by_sections() 重检
    │   6. 根据重检结果更新 issue 状态
    │      - 评分改善 → revising → resolved
    │      - 评分未改善 → revising → open
    │   7. 更新 version_stack
    │   8. SSE push: SessionStreamer.push_preview_refresh()
    │   9. SSE push: SessionStreamer.push_section_quality() (已有)
    │
    └─ 非修订意图 → 正常对话处理
```

### 8.2 版本回滚 (quality_rollback)

```
POST /research/quality/action  {action: "quality_rollback", version_id: "v0"}
    │
    ▼
1. 从 version_stack 找到目标版本
2. 从快照恢复 HTML 文件 (v0.html → data/html_reports/{task_id}.html)
3. 从快照恢复 Markdown 文件 (v0.md → 当前源文件路径)
4. 从快照恢复 quality_state (v0_quality.json → session["quality_state"])
5. 对 v0 之后新增的 issue 重新标记为 open
6. SSE push: SessionStreamer.push_preview_refresh() + push_quality_result()
```

### 8.3 确认交付 (quality_confirm)

```
POST /research/quality/action  {action: "quality_confirm"}
    │
    ▼
1. 收集所有非 resolved 状态的 issue 列表
2. 如有 open 或 dismissed 的 issue:
   - 返回 issue 清单，前端弹出确认对话框
   - 用户确认后才继续
3. 调用现有文档生成流程生成 DOCX/PPTX/PDF
4. 更新 session["quality_state"]["phase"] = "confirmed"
5. SSE push: SessionStreamer.push_quality_confirmed()
6. 前端关闭质量面板，显示下载按钮
```

### 8.4 重检流程 (quality_recheck)

```
POST /research/quality/action  {action: "quality_recheck", section_name: "核心财务指标"}
    │
    ▼
1. 获取指定章节或全报告内容
2. 调用 QualityCheckAgent.check_by_sections() (L873)
3. 为返回的 issue 生成稳定 ID (generate_issue_id())
4. 与已有 issue 通过 ID 合并:
   - 已有 issue ID 在新结果中不存在 → 保持原状态
   - 已有 issue ID 在新结果中存在 → 保持原状态不变
   - 新 issue ID 不在已有列表中 → 新增为 open
5. 更新 session["quality_state"]["section_scores"]
6. SSE push: SessionStreamer.push_quality_result() + push_section_quality()
```

## 9. 排版错乱处理

### 9.1 风险分析

| 场景 | 原因 | 概率 |
|------|------|------|
| 修订后 HTML 重新生成 | 内容长度变化导致分页偏移 | 中 |
| 自动补充框架内容 | 插入新段落/表格改变布局 | 中 |
| 多次修订叠加 | 累积误差导致全局布局偏移 | 低 |
| 图表数据更新 | 图表尺寸变化 | 低 |

### 9.2 防护策略

**版本快照 + 修订提示条一键回滚**

每次修订前自动创建快照。修订完成后，预览顶部显示临时提示条，包含「一键回滚」按钮。

**Markdown 源文件为权威源**

修订时修改 markdown 源文件，从 markdown 重新生成 HTML 预览。
若 HTML 预览出现问题，始终可从 markdown 源文件重新生成。不直接修改 HTML 文件。

**修订后预览自检**

```python
# src/core/quality/preview_health.py

from pathlib import Path
from typing import Dict, List

def check_preview_health(html_path: str, old_html_length: int = 0) -> Dict[str, object]:
    issues: List[Dict[str, str]] = []
    content = Path(html_path).read_text(encoding="utf-8")

    if content.count("<table") != content.count("</table"):
        issues.append({"type": "layout", "message": "表格标签未闭合"})

    if len(content.strip()) < 500:
        issues.append({"type": "layout", "message": "预览内容异常稀疏"})

    if old_html_length > 0 and len(content) > old_html_length * 3:
        issues.append({"type": "layout", "message": "预览内容异常膨胀"})

    return {"healthy": len(issues) == 0, "issues": issues}
```

若自检不通过，SSE 推送 `agent_message` 附带排版警告，前端在提示条中显示：
「修订完成但预览可能存在排版问题，[查看] [回滚]」

**修订粒度控制**

`RevisionService` 已内置修订粒度控制（`minor` / `section` / `phase` / `full`），
对话式修订让用户可以明确指定修订范围，避免过度修改。

## 10. 并发与幂等

### 10.1 修订锁

对话修订走现有 `_pending_section_injects` 队列，已有 `_inject_in_progress` 防重入保护（`src/api/research_executor.py` L63）。

对于质检操作（dismiss/reopen/rollback），使用 session 级别的轻量锁：

```python
session["_quality_action_lock"] = {
    "locked": True,
    "action": "rollback",
    "started_at": datetime.now().isoformat(),
}
```

### 10.2 幂等性

- 同一 issue 重复点击「忽略」→ 幂等，保持 dismissed
- 同一版本重复点击「回滚」→ 幂等，恢复到目标版本
- 重检操作 → 幂等，返回最新评分
- 确认交付 → 幂等，已确认的再次确认返回当前状态

## 11. 修订次数限制

| 限制项 | 阈值 | 原因 |
|--------|------|------|
| 单 issue 修订轮次 | 3次 | 防止对话修订反复无法解决同一问题 |
| 总修订轮次 | 10次 | 防止无限循环 |
| 版本栈深度 | 10个 | 防止快照文件膨胀 |

超过限制后，该 issue 标记为 `max_retries_reached`，前端显示「建议通过对话详细描述修订需求」。

## 12. 前端状态管理

### 12.1 合入 useSessionStore

质检状态是 session 状态的一部分，在 `web/src/store/useSessionStore.ts` 的 `SessionCache` 接口 (L21) 中新增字段：

```typescript
// web/src/store/useSessionStore.ts — SessionCache 新增

export interface QualityIssueData {
  id: string;
  type: 'completeness' | 'accuracy' | 'consistency' | 'format' | 'hallucination';
  severity: 'high' | 'medium' | 'low';
  message: string;
  section: string;
  state: 'open' | 'dismissed' | 'revising' | 'resolved' | 'max_retries_reached';
}

export interface SectionQualityData {
  score: number;
  status: 'passed' | 'warning';
  issues: QualityIssueData[];
}

export interface VersionInfoData {
  id: string;
  created_at: string;
  overall_score: number;
  label: string;
}

export interface QualityStateData {
  phase: 'reviewing' | 'revising' | 'confirmed';
  overall_score: number;
  overall_status: 'passed' | 'warning';
  section_scores: Record<string, SectionQualityData>;
  version_stack: VersionInfoData[];
  current_version: string;
}

// SessionCache 新增:
// qualityState: QualityStateData | null;
```

在 `emptyCache()` (L156) 中初始化为 `null`，在 `restoreSession()` 中从后端获取填充。

### 12.2 SSE 事件处理

在 `web/src/hooks/useProgress.ts` 的 `useSessionStream` (L224) 中新增事件处理。当前 `useSessionStream` 只接收 `onChatResponse` 和 `onAgentMessage` 回调，需扩展：

```typescript
// web/src/hooks/useProgress.ts — UseSessionStreamOptions 扩展

export interface UseSessionStreamOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
  onQualityResult?: (data: any) => void;
  onSectionQuality?: (data: any) => void;
  onPreviewRefresh?: (data: any) => void;
  onQualityConfirmed?: (data: any) => void;
}
```

在 `useSessionStream` 内部，将新增回调传递给 `sseManager.subscribeSession()`：

```typescript
const unsubscribe = sseManager.subscribeSession(
  sessionId,
  (data) => { if (onChatResponseRef.current) onChatResponseRef.current(data); },
  (data) => { if (onAgentMessageRef.current) onAgentMessageRef.current(data); },
  (data) => { if (onQualityResultRef.current) onQualityResultRef.current(data); },
  (data) => { if (onSectionQualityRef.current) onSectionQualityRef.current(data); },
  (data) => { if (onPreviewRefreshRef.current) onPreviewRefreshRef.current(data); },
  (data) => { if (onQualityConfirmedRef.current) onQualityConfirmedRef.current(data); },
);
```

### 12.3 发起修订对话

点击「发起修订」按钮时的前端逻辑：

```typescript
// web/src/components/quality/IssueRow.tsx

function handleStartRevision(issue: QualityIssueData) {
  const chatInput = `【质检问题】${issue.section}: ${issue.message}\n请帮我修订这部分内容。`;
  // 预填到聊天输入框，不直接发送
  useSessionStore.getState().syncActive({
    // 通过 pendingInput 机制预填（需 ChatPanel 配合）
  });
}
```

### 12.4 SSEMessage 类型扩展

在 `web/src/types/api.ts` 的 `SSEMessage` 接口 (L202) 中扩展 event 联合类型：

```typescript
// web/src/types/api.ts — SSEMessage.event 扩展

export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete'
       | 'chat_response' | 'agent_message' | 'heartbeat' | 'connected' | 'message' | 'cancelled'
       | 'quality_result' | 'section_quality' | 'preview_refresh' | 'quality_confirmed';
  data: ProgressData | PhaseData | ErrorData | CompleteData | ChatResponseData | AgentMessageData | any;
}
```

## 13. 后端实现要点

### 13.1 新增 quality/action 路由

在 `src/api/main.py` 新增端点（与现有 `feedback` 端点 L392 同级）：

```python
# src/api/main.py

@app.post("/api/v1/research/quality/action")
async def quality_action(request: QualityActionRequest):
    return await research_api.handle_quality_action(request)

@app.get("/api/v1/research/quality/{session_id}")
async def get_quality_state(session_id: str):
    return await research_api.get_quality_state(session_id)
```

`src/api/research_api.py` 新增 `handle_quality_action()` 和 `get_quality_state()`：

```python
# src/api/research_api.py

async def handle_quality_action(self, request: QualityActionRequest) -> Dict[str, Any]:
    action = request.action
    session_id = request.session_id
    if action == "quality_dismiss":
        return await self._handle_quality_dismiss(session_id, request.issue_id)
    elif action == "quality_reopen":
        return await self._handle_quality_reopen(session_id, request.issue_id)
    elif action == "quality_rollback":
        return await self._handle_quality_rollback(session_id, request.version_id)
    elif action == "quality_confirm":
        return await self._handle_quality_confirm(session_id)
    elif action == "quality_recheck":
        return await self._handle_quality_recheck(session_id, request.section_name)
    else:
        return {"error": f"Unknown action: {action}", "error_code": "UNKNOWN_ACTION"}

async def get_quality_state(self, session_id: str) -> Dict[str, Any]:
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
    return session.get("quality_state", {})
```

### 13.2 Issue ID 稳定生成

在 `QualityCheckAgent.check_by_sections()` (L873) 返回 issue 时，生成稳定 ID：

```python
# src/agents/fixed_agents/quality_check_agent.py — check_by_sections() 内

from src.core.quality.quality_state import generate_issue_id

for issue in issues:
    issue["id"] = generate_issue_id(section_name, issue.get("type", ""), issue.get("message", ""))
    issue["section"] = section_name
    if "state" not in issue:
        issue["state"] = "open"
```

### 13.3 快照管理

新增 `src/core/quality/quality_snapshot_manager.py`，基于文件系统的多文件快照管理：

```python
# src/core/quality/quality_snapshot_manager.py

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class QualitySnapshotManager:
    
    def __init__(self, base_dir: str = "data/snapshots"):
        self.base_dir = Path(base_dir)
    
    async def create_snapshot(
        self,
        session_id: str,
        html_path: str,
        md_path: str,
        quality_state: dict,
    ) -> str:
        version_n = len(quality_state.get("version_stack", []))
        version_id = f"v{version_n}"
        snap_dir = self.base_dir / session_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(html_path, snap_dir / f"{version_id}.html")
        shutil.copy2(md_path, snap_dir / f"{version_id}.md")
        (snap_dir / f"{version_id}_quality.json").write_text(
            json.dumps(quality_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return version_id
    
    async def restore_snapshot(self, session_id: str, version_id: str) -> Optional[dict]:
        snap_dir = self.base_dir / session_id
        quality_json = snap_dir / f"{version_id}_quality.json"
        if not quality_json.exists():
            return None
        quality_state = json.loads(quality_json.read_text(encoding="utf-8"))
        return {
            "html_path": str(snap_dir / f"{version_id}.html"),
            "md_path": str(snap_dir / f"{version_id}.md"),
            "quality_state": quality_state,
        }
    
    async def cleanup_old(self, session_id: str, keep: int = 10):
        snap_dir = self.base_dir / session_id
        if not snap_dir.exists():
            return
        versions = sorted(snap_dir.glob("v*.html"))
        if len(versions) > keep:
            for v in versions[:-keep]:
                stem = v.stem
                v.unlink(missing_ok=True)
                (snap_dir / f"{stem}.md").unlink(missing_ok=True)
                (snap_dir / f"{stem}_quality.json").unlink(missing_ok=True)
```

> 注意: 现有 `src/core/adjustment/snapshot_manager.py` 中的 `SnapshotManager` 使用内存存储，
> 适用于修订系统的 report tree 快照。质检快照需要文件系统存储（HTML/MD/JSON 三文件），
> 因此新增独立的 `QualitySnapshotManager`，不与现有类冲突。

### 13.4 预览生成与章节锚点

修改 `src/content/content_orchestrator.py` 的 `transform_to_html()` 或 `src/core/preview/preview_generator.py` 的 `generate_html_preview_from_data()`，在生成 HTML 时为每个章节添加锚点：

```html
<div id="section-核心财务指标" class="report-section">
  <h2>核心财务指标</h2>
  ...
</div>
```

锚点 ID 格式: `section-{sanitized_name}`，`sanitized_name` 为章节名去除特殊字符后的结果。

### 13.5 预览刷新推送

修订完成后，后端主动推送 `preview_refresh` 事件：

```python
from src.core.session_streamer import SessionStreamer

SessionStreamer.push_preview_refresh(
    session_id,
    preview_url=f"/api/v1/html-reports/{task_id}.html",
    version_id=new_version_id,
)
```

前端收到后重新加载 iframe src，加 timestamp 参数避免浏览器缓存：

```typescript
// web/src/components/preview/DocumentPreview.tsx 内
iframe.src = `${previewUrl}?t=${Date.now()}`;
```

## 14. 错误处理

| 错误场景 | 处理 |
|----------|------|
| 修订服务调用失败 | 通过 `SessionStreamer.push_agent_message()` SSE 推送错误信息，issue 从 `revising` 回退为 `open` |
| 预览生成失败 | 通过 `push_agent_message()` 推送警告，提示用户可通过对话继续修订 |
| 排版自检失败 | 在修订提示条中显示排版警告，提供[查看][回滚]选项 |
| 修订超限 | issue 标记 `max_retries_reached`，前端显示"建议通过对话详细描述修订需求" |
| 并发操作冲突 | 轻量锁拦截，返回 409 Conflict |
| 快照恢复失败 | 返回错误，提示用户刷新页面重新加载 |
| 重检失败 | 保持当前评分不变，通过 `push_agent_message()` 推送重检失败通知 |

## 15. 测试策略

### 15.1 后端测试

| 测试名 | 覆盖 |
|--------|------|
| `test_generate_issue_id_stable` | 同一 issue 多次调用返回相同 ID |
| `test_issue_id_merge_on_recheck` | 重检时已 resolved/dismissed 的 issue 保持原状态 |
| `test_quality_dismiss_and_reopen` | 忽略 → 重新打开 → 状态正确 |
| `test_quality_rollback` | 修订后回滚到 v0，HTML/MD/评分全部恢复 |
| `test_quality_confirm_with_open_issues` | 有 open/dismissed issue 时确认需展示清单 |
| `test_revision_triggers_recheck` | 对话修订完成后自动重检受影响章节 |
| `test_revision_updates_issue_state` | 修订改善评分 → issue revising → resolved |
| `test_revision_no_improvement` | 修订未改善评分 → issue revising → open |
| `test_snapshot_create_and_restore` | 快照创建与恢复一致性 (HTML+MD+quality_state) |
| `test_check_preview_health` | 预览自检逻辑 (标签闭合、内容膨胀、稀疏检测) |
| `test_max_retries_reached` | 超过3次修订标记 max_retries_reached |
| `test_concurrent_quality_action_blocked` | 并发质检操作被锁拦截 |

### 15.2 前端测试

| 测试名 | 覆盖 |
|--------|------|
| QualityPanel 显示评分和 issue 列表 | 组件渲染 |
| IssueRow 「发起修订」预填聊天输入框 | 点击行为 |
| IssueRow 忽略/重新打开 | 状态切换 |
| SSE 事件 → sessionStore 更新 | quality_result / section_quality |
| preview_refresh → iframe 刷新 | 预览自动更新 |
| 修订提示条显示与回滚 | 提示条交互 |
| 确认交付弹窗显示 issue 清单 | 交付前确认 |
| 章节导航条滚动到锚点 | 导航交互 |

### 15.3 E2E 测试

| 测试名 | 覆盖 |
|--------|------|
| 完整修订闭环 | 研究 → 质检展示 → 对话修订 → 重检 → 确认 |
| 排版错乱回滚 | 修订 → 预览错乱 → 提示条回滚 → 预览正常 |
| 多 issue 顺序修订 | 2个 issue 逐一对话修订，评分逐步提升 |
| 忽略后确认 | 忽略 issue → 确认 → 弹 issue 清单 → 确认交付 |
| 版本回滚状态恢复 | 修订后回滚 → issue 状态恢复 → 可再次修订 |

## 16. 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/core/quality/__init__.py` | 质检模块初始化 |
| `src/core/quality/quality_state.py` | QualityState / QualityIssue Pydantic 模型 + generate_issue_id() |
| `src/core/quality/quality_snapshot_manager.py` | 基于 HTML+MD+JSON 三文件的版本快照管理 |
| `src/core/quality/preview_health.py` | 预览排版自检 check_preview_health() |
| `web/src/components/quality/QualityPanel.tsx` | 质量面板主组件 |
| `web/src/components/quality/IssueRow.tsx` | Issue 交互行 |
| `web/src/components/quality/VersionTimeline.tsx` | 版本时间线 |
| `web/src/components/quality/RevisionHintBar.tsx` | 修订提示条 |
| `web/src/components/quality/ConfirmDeliveryDialog.tsx` | 确认交付对话框 |
| `web/src/components/quality/SectionNavBar.tsx` | 章节导航条 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/agents/fixed_agents/quality_check_agent.py` | `check_by_sections()` (L873) 返回稳定 issue ID + state |
| `src/api/research_api.py` | 新增 `handle_quality_action()` + `get_quality_state()` + 5 个 handler + `_handle_v2_revision()` 内修订联动逻辑 |
| `src/api/main.py` | 新增 `POST /quality/action` + `GET /quality/{session_id}` 端点 |
| `src/core/session_streamer.py` | `SessionSSEEventType` (L33) 新增 PREVIEW_REFRESH / QUALITY_CONFIRMED + 2 个 push classmethod |
| `src/content/content_orchestrator.py` | `transform_to_html()` 为章节添加锚点 id |
| `web/src/types/api.ts` | `SSEMessage.event` (L202) 扩展联合类型 + QualityStateData 等接口 |
| `web/src/lib/sse.ts` | `subscribeSession()` (L171) 注册 quality_result / section_quality / preview_refresh / quality_confirmed 事件监听 |
| `web/src/hooks/useProgress.ts` | `UseSessionStreamOptions` (L219) 扩展 + `useSessionStream()` 传递新回调 |
| `web/src/store/useSessionStore.ts` | `SessionCache` (L21) 新增 qualityState 字段 |
| `web/src/components/layout/MainLayout.tsx` | 集成 QualityPanel + SectionNavBar |

## 17. 实施优先级

| 优先级 | 内容 | 依赖 |
|--------|------|------|
| P0 | 前端SSE打通 + QualityPanel展示 | 无 |
| P0 | quality/action API (dismiss/reopen/rollback/confirm/recheck) | 无 |
| P0 | 版本快照 + 回滚 | 修订逻辑 |
| P0 | 对话修订与质检联动 (修订→重检→更新issue状态) | 现有修订链路 |
| P1 | 章节导航条 + 锚点 | P0 |
| P1 | 修订提示条 + 排版保护 | P0 |
| P1 | 确认交付对话框 (展示issue清单) | P0 |
| P2 | 版本时间线 UI | P0 |
| P2 | 修订次数限制 + 并发锁 | P0 |
| P2 | 预览自检 | P0 |

# 质检反馈交互修订系统 — 修订方案 v2

> 日期: 2026-06-01
> 状态: 修订中
> 范围: 报告研究完成后的质检展示、用户交互、内容修订、预览刷新全链路
> 核心原则: **质检让问题可见，修订让对话来做**

---

## 0. 修订说明

本方案基于 2026-06-01 原始设计文档，结合项目当前代码实际状态重新修订。主要变化：

1. **明确已有实现 vs 待实现**：标注每个模块的当前状态
2. **修正发现的 bug**：`session_streamer.py` 中 `push_quality_confirmed()` 引用了未定义变量
3. **修正与现有代码的对接点**：原方案中部分行号已过期，重新定位
4. **精简前端方案**：基于现有组件结构（`MainLayout` + `DocumentPreview` + `RevisionPanel`）集成，而非全新布局
5. **明确实施步骤**：按依赖顺序排列，每步可独立验证

---

## 1. 背景与问题

当前系统在报告研究完成后，质检信息无法被用户感知，更无法交互：

| 断点 | 现状 | 影响 |
|------|------|------|
| 前端SSE | `sse.ts` `subscribeSession()` 只监听 `chat_response` / `agent_message`，不监听 `quality_result` / `section_quality` | 质检分数被静默丢弃 |
| 前端组件 | 无质量面板 | 用户看不到章节评分 |
| 后端API | `handle_quality_action()` 是 stub，仅处理 `approve` 动作 | 无质检专用操作（dismiss/rollback/confirm/recheck 全缺失） |
| 后端SSE | `push_quality_confirmed()` 有 bug，引用未定义的 `section_name`/`quality_data` | 质检确认事件无法正确推送 |
| 修订闭环 | `_handle_v2_revision()` 无质检联动（无快照、无 issue 标记、无修订后重检） | 无"修订→重检→刷新"循环 |
| 质检Agent | `check_by_sections()` 返回的 issue 无稳定 ID | 重检时无法追踪同一问题 |
| 预览刷新 | 修订后无自动刷新 | 用户不知道修订是否生效 |
| 排版风险 | 修订只改 markdown 源文件 | HTML 预览可能排版错乱 |

### 1.1 已有实现（可复用）

| 模块 | 文件 | 状态 |
|------|------|------|
| 数据模型 | `src/core/quality/quality_state.py` | ✅ 完整实现（QualityIssue/SectionScore/VersionInfo/QualityState/generate_issue_id/merge_issues_on_recheck） |
| 快照管理 | `src/core/quality/quality_snapshot_manager.py` | ✅ 完整实现（create/restore/list/cleanup） |
| 预览自检 | `src/core/quality/preview_health.py` | ✅ 完整实现 |
| SSE事件类型 | `src/core/session_streamer.py` | ⚠️ 部分实现（QUALITY_RESULT/SECTION_QUALITY/PREVIEW_REFRESH/QUALITY_CONFIRMED 类型已定义，push 方法已有，但 push_quality_confirmed 有 bug） |
| API端点注册 | `src/api/main.py` | ✅ 路由已注册（/quality/action, /quality/{session_id}） |
| 请求模型 | `src/api/research_api.py` | ⚠️ QualityActionRequest 已定义但 action 枚举不含 quality_* 前缀 |

---

## 2. 设计目标

1. **可见**: 研究完成后前端实时展示分章节评分、整体评分、问题列表
2. **可对话**: 质检问题通过对话发起修订，用户可精细控制修订方向和范围
3. **可观测**: 每次修订后预览自动刷新，评分实时更新
4. **可恢复**: 排版错乱时可一键回滚到修订前版本
5. **有终态**: 明确"确认交付"出口，避免无限修订循环

---

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

---

## 4. 数据模型

### 4.1 QualityState（已实现 ✅）

`src/core/quality/quality_state.py` 已完整实现：

- `QualityIssue` — 含 id/type/severity/message/section/state
- `SectionScore` — 含 score/status/issues
- `VersionInfo` — 含 id/created_at/html_path/md_path/quality_state_snapshot/overall_score/label
- `QualityState` — 含 phase/overall_score/overall_status/section_scores/version_stack/current_version
- `generate_issue_id()` — 基于 section+type+message 的稳定哈希
- `merge_issues_on_recheck()` — 重检时 issue 合并逻辑

**无需修改，直接使用。**

### 4.2 session 中存储方式

```python
session["quality_state"] = quality_state.model_dump()
```

当前 `get_quality_state()` 返回的是 `session.get("quality_status", "unknown")` 字符串，需改为返回完整 `QualityState` dict。

---

## 5. 后端修改清单

### 5.1 修复 Bug: `push_quality_confirmed()` 

**文件**: `src/core/session_streamer.py`

**问题**: `push_quality_confirmed()` 方法引用了 `section_name` 和 `quality_data`，这些变量在方法签名和作用域中不存在。

**当前代码**:
```python
@classmethod
def push_quality_confirmed(cls, session_id: str, final_document_path: str):
    cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, {
        "session_id": session_id,
        "final_document_path": final_document_path,
        "section_name": section_name,  # ❌ 未定义
        "quality_data": quality_data,  # ❌ 未定义
    })
```

**修复为**:
```python
@classmethod
def push_quality_confirmed(cls, session_id: str, final_document_path: str):
    cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, {
        "session_id": session_id,
        "final_document_path": final_document_path,
        "timestamp": datetime.now().isoformat(),
    })
```

### 5.2 修改 `QualityActionRequest` action 枚举

**文件**: `src/api/research_api.py`

**当前代码**:
```python
class QualityActionRequest(BaseModel):
    session_id: str
    action: Literal["quality_dismiss", "quality_reopen", "quality_rollback", "quality_confirm", "quality_recheck"]
    issue_id: Optional[str] = None
    version_id: Optional[str] = None
    section_name: Optional[str] = None
```

**当前 `handle_quality_action()`** 只处理 `approve`，需替换为完整的 5 个 action handler。

**修改为**:
```python
class QualityActionRequest(BaseModel):
    session_id: str
    action: Literal["quality_dismiss", "quality_reopen", "quality_rollback", "quality_confirm", "quality_recheck"]
    issue_id: Optional[str] = None
    version_id: Optional[str] = None
    section_name: Optional[str] = None
```

（`QualityActionRequest` 本身不需要改，但 `handle_quality_action()` 需要完全重写。）

### 5.3 重写 `handle_quality_action()`

**文件**: `src/api/research_api.py`

将当前 stub 替换为完整实现：

```python
async def handle_quality_action(self, request: QualityActionRequest) -> Dict[str, Any]:
    action = request.action
    session_id = request.session_id
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
    
    if action == "quality_dismiss":
        return await self._handle_quality_dismiss(session, request.issue_id)
    elif action == "quality_reopen":
        return await self._handle_quality_reopen(session, request.issue_id)
    elif action == "quality_rollback":
        return await self._handle_quality_rollback(session, request.version_id)
    elif action == "quality_confirm":
        return await self._handle_quality_confirm(session)
    elif action == "quality_recheck":
        return await self._handle_quality_recheck(session, request.section_name)
    else:
        return {"error": f"Unknown action: {action}", "error_code": "UNKNOWN_ACTION"}
```

### 5.4 实现 5 个 quality handler

**文件**: `src/api/research_api.py`

#### `_handle_quality_dismiss(session, issue_id)`

```python
async def _handle_quality_dismiss(self, session, issue_id: str) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
    
    found = False
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("id") == issue_id:
                issue["state"] = "dismissed"
                found = True
                break
        if found:
            break
    
    if not found:
        return {"error": f"Issue {issue_id} not found", "error_code": "ISSUE_NOT_FOUND"}
    
    session["quality_state"] = quality_data
    return {"success": True, "issue_id": issue_id, "state": "dismissed"}
```

#### `_handle_quality_reopen(session, issue_id)`

```python
async def _handle_quality_reopen(self, session, issue_id: str) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
    
    found = False
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("id") == issue_id and issue.get("state") == "dismissed":
                issue["state"] = "open"
                found = True
                break
        if found:
            break
    
    if not found:
        return {"error": f"Issue {issue_id} not found or not dismissed", "error_code": "ISSUE_NOT_FOUND"}
    
    session["quality_state"] = quality_data
    return {"success": True, "issue_id": issue_id, "state": "open"}
```

#### `_handle_quality_rollback(session, version_id)`

```python
async def _handle_quality_rollback(self, session, version_id: str) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
    
    version_stack = quality_data.get("version_stack", [])
    target_version = None
    for v in version_stack:
        if v.get("id") == version_id:
            target_version = v
            break
    
    if not target_version:
        return {"error": f"Version {version_id} not found", "error_code": "VERSION_NOT_FOUND"}
    
    session_id = session.get("session_id", session.get("id", ""))
    snap_mgr = QualitySnapshotManager()
    snapshot = await snap_mgr.restore_snapshot(session_id, version_id)
    if not snapshot:
        return {"error": "Snapshot restore failed", "error_code": "SNAPSHOT_RESTORE_FAILED"}
    
    html_src = Path(snapshot["html_path"])
    md_src = Path(snapshot["md_path"])
    
    task_id = session.get("task_id", "")
    html_dest = Path(f"data/html_reports/{task_id}.html")
    
    if html_src.exists() and html_dest.parent.exists():
        shutil.copy2(str(html_src), str(html_dest))
    
    md_dest = session.get("report_md_path", "")
    if md_src.exists() and md_dest:
        shutil.copy2(str(md_src), md_dest)
    
    restored_quality = snapshot["quality_state"]
    
    for section_name, section_data in restored_quality.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") == "resolved":
                issue["state"] = "open"
    
    session["quality_state"] = restored_quality
    quality_data = restored_quality
    
    SessionStreamer.push_preview_refresh(
        session_id,
        preview_url=f"/api/v1/html-reports/{task_id}.html",
        version_id=version_id,
    )
    SessionStreamer.push_quality_result(session_id, restored_quality)
    
    return {"success": True, "version_id": version_id, "quality_state": restored_quality}
```

#### `_handle_quality_confirm(session)`

```python
async def _handle_quality_confirm(self, session) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
    
    open_issues = []
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") in ("open", "dismissed", "max_retries_reached"):
                open_issues.append({
                    "id": issue.get("id"),
                    "section": section_name,
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                    "state": issue.get("state"),
                })
    
    if open_issues:
        return {
            "status": "pending_issues",
            "open_issues": open_issues,
            "message": "仍有未解决的问题，请确认是否仍要交付",
        }
    
    quality_data["phase"] = "confirmed"
    session["quality_state"] = quality_data
    
    session_id = session.get("session_id", session.get("id", ""))
    task_id = session.get("task_id", "")
    
    SessionStreamer.push_quality_confirmed(session_id, f"/api/v1/html-reports/{task_id}.html")
    
    return {"status": "confirmed", "quality_state": quality_data}
```

#### `_handle_quality_recheck(session, section_name)`

```python
async def _handle_quality_recheck(self, session, section_name: Optional[str] = None) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}
    
    session_id = session.get("session_id", session.get("id", ""))
    
    quality_agent = QualityCheckAgent()
    results = await quality_agent.check_by_sections(session)
    
    new_issues_by_section = {}
    for result in results:
        sec = result.get("section", "")
        issues = result.get("issues", [])
        for issue in issues:
            issue["id"] = generate_issue_id(sec, issue.get("type", ""), issue.get("message", ""))
            issue["section"] = sec
            if "state" not in issue:
                issue["state"] = "open"
        new_issues_by_section[sec] = issues
    
    existing_issues = {}
    for sec, sec_data in quality_data.get("section_scores", {}).items():
        existing_issues[sec] = sec_data.get("issues", [])
    
    merged = merge_issues_on_recheck(existing_issues, new_issues_by_section)
    
    overall_score = 0.0
    count = 0
    for sec, issues in merged.items():
        score = _calculate_section_score(issues)
        status = "passed" if score >= 70 else "warning"
        if sec in quality_data.get("section_scores", {}):
            quality_data["section_scores"][sec]["score"] = score
            quality_data["section_scores"][sec]["status"] = status
            quality_data["section_scores"][sec]["issues"] = issues
        else:
            quality_data["section_scores"][sec] = {
                "score": score,
                "status": status,
                "issues": issues,
            }
        overall_score += score
        count += 1
    
    if count > 0:
        quality_data["overall_score"] = round(overall_score / count, 1)
        quality_data["overall_status"] = "passed" if quality_data["overall_score"] >= 70 else "warning"
    
    session["quality_state"] = quality_data
    
    SessionStreamer.push_quality_result(session_id, quality_data)
    SessionStreamer.push_section_quality(session_id, quality_data.get("section_scores", {}))
    
    return {"success": True, "quality_state": quality_data}

def _calculate_section_score(issues: list) -> float:
    base = 100.0
    for issue in issues:
        if issue.get("state") in ("resolved", "dismissed"):
            continue
        sev = issue.get("severity", "low")
        if sev == "high":
            base -= 20
        elif sev == "medium":
            base -= 10
        else:
            base -= 5
    return max(0.0, base)
```

### 5.5 修改 `get_quality_state()`

**文件**: `src/api/research_api.py`

**当前代码**（返回简单字符串）:
```python
async def get_quality_state(self, session_id: str):
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
    return session.get("quality_status", "unknown")
```

**修改为**（返回完整 QualityState dict）:
```python
async def get_quality_state(self, session_id: str) -> Dict[str, Any]:
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
    return session.get("quality_state", {})
```

### 5.6 修改 `check_by_sections()` 生成稳定 Issue ID

**文件**: `src/agents/fixed_agents/quality_check_agent.py`

在 `check_by_sections()` 返回结果时，为每个 issue 添加稳定 ID：

```python
from src.core.quality.quality_state import generate_issue_id

# 在 check_by_sections() 返回结果前，为每个 issue 添加 id
for result in results:
    section_name = result.get("section", "")
    for issue in result.get("issues", []):
        issue["id"] = generate_issue_id(section_name, issue.get("type", ""), issue.get("message", ""))
        issue["section"] = section_name
        if "state" not in issue:
            issue["state"] = "open"
```

### 5.7 修订与质检联动：修改 `_handle_v2_revision()`

**文件**: `src/api/research_api.py`

在 `_handle_v2_revision()` 执行修订前和修订后，增加质检状态联动。

**修订前 — 创建快照 + 标记 issue 为 revising**:

```python
# 在 _handle_v2_revision() 内，修订执行前
quality_state_data = session.get("quality_state", {})
if quality_state_data and quality_state_data.get("phase") in ("reviewing", "revising"):
    quality_state_data["phase"] = "revising"
    session["quality_state"] = quality_state_data
    
    snap_mgr = QualitySnapshotManager()
    html_path = f"data/html_reports/{session.get('task_id', '')}.html"
    md_path = session.get("report_md_path", "")
    await snap_mgr.create_snapshot(
        session_id, html_path, md_path, quality_state_data
    )
    
    for section_name, section_data in quality_state_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") == "open" and issue.get("section") in modified_sections:
                issue["state"] = "revising"
    session["quality_state"] = quality_state_data
```

**修订后 — 重检 + 更新 issue 状态**:

```python
# 修订成功后
if result_success and quality_state_data:
    modified_sections = [section] if section else None
    await self._post_revision_recheck(session, modified_sections)

async def _post_revision_recheck(self, session, modified_sections: Optional[List[str]] = None):
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return
    
    session_id = session.get("session_id", session.get("id", ""))
    
    quality_agent = QualityCheckAgent()
    results = await quality_agent.check_by_sections(session)
    
    new_issues_by_section = {}
    for result in results:
        sec = result.get("section", "")
        if modified_sections and sec not in modified_sections:
            continue
        issues = result.get("issues", [])
        for issue in issues:
            issue["id"] = generate_issue_id(sec, issue.get("type", ""), issue.get("message", ""))
            issue["section"] = sec
            if "state" not in issue:
                issue["state"] = "open"
        new_issues_by_section[sec] = issues
    
    existing_issues = {}
    for sec, sec_data in quality_data.get("section_scores", {}).items():
        existing_issues[sec] = sec_data.get("issues", [])
    
    merged = merge_issues_on_recheck(existing_issues, new_issues_by_section)
    
    for sec, issues in merged.items():
        score = _calculate_section_score(issues)
        status = "passed" if score >= 70 else "warning"
        quality_data["section_scores"][sec] = {
            "score": score,
            "status": status,
            "issues": issues,
        }
    
    task_id = session.get("task_id", "")
    
    try:
        preview_gen = PreviewGenerator()
        preview_gen.generate_html_preview_from_data(session)
    except Exception as e:
        logger.error(f"Preview generation failed after revision: {e}")
    
    SessionStreamer.push_preview_refresh(
        session_id,
        preview_url=f"/api/v1/html-reports/{task_id}.html",
        version_id=quality_data.get("current_version", "v0"),
    )
    SessionStreamer.push_quality_result(session_id, quality_data)
    SessionStreamer.push_section_quality(session_id, quality_data.get("section_scores", {}))
    
    session["quality_state"] = quality_data
```

### 5.8 章节锚点（HTML 生成时添加 id）

**文件**: `src/content/content_orchestrator.py`（或 `src/core/preview/preview_generator.py`）

在生成 HTML 时，为每个章节的容器 div 添加锚点 id：

```html
<div id="section-核心财务指标" class="report-section">
  <h2>核心财务指标</h2>
  ...
</div>
```

锚点 ID 格式: `section-{sanitized_name}`，`sanitized_name` 为章节名去除特殊字符后的结果。

> 具体修改点需在 HTML 模板/生成逻辑中定位章节输出位置后确定。

---

## 6. 前端修改清单

### 6.1 修改 `sse.ts` — 扩展 SSE 事件监听

**文件**: `web/src/lib/sse.ts`

当前 `subscribeSession()` 只监听 `chat_response` 和 `agent_message`，需扩展。

**新增回调类型和存储**:

```typescript
type QualityResultCallback = (data: any) => void;
type SectionQualityCallback = (data: any) => void;
type PreviewRefreshCallback = (data: any) => void;
type QualityConfirmedCallback = (data: any) => void;

private sessionQualityCallbacks: Map<string, Set<QualityResultCallback>> = new Map();
private sessionSectionQualityCallbacks: Map<string, Set<SectionQualityCallback>> = new Map();
private sessionPreviewRefreshCallbacks: Map<string, Set<PreviewRefreshCallback>> = new Map();
private sessionQualityConfirmedCallbacks: Map<string, Set<QualityConfirmedCallback>> = new Map();
```

**`subscribeSession()` 签名扩展**:

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

**新增事件监听**（在 `subscribeSession()` 内）:

```typescript
eventSource.addEventListener('quality_result', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionQualityCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream quality_result parse error:', e);
  }
});

eventSource.addEventListener('section_quality', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionSectionQualityCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream section_quality parse error:', e);
  }
});

eventSource.addEventListener('preview_refresh', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const callbacks = this.sessionPreviewRefreshCallbacks.get(sessionId);
    if (callbacks) callbacks.forEach((cb) => cb(data));
  } catch (e) {
    console.error('Session stream preview_refresh parse error:', e);
  }
});

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

### 6.2 修改 `useProgress.ts` — 扩展 `UseSessionStreamOptions`

**文件**: `web/src/hooks/useProgress.ts`

```typescript
export interface UseSessionStreamOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
  onQualityResult?: (data: any) => void;
  onSectionQuality?: (data: any) => void;
  onPreviewRefresh?: (data: any) => void;
  onQualityConfirmed?: (data: any) => void;
}
```

在 `useSessionStream()` 内部，将新增回调传递给 `sseManager.subscribeSession()`。

### 6.3 修改 `useSessionStore.ts` — 新增 qualityState 字段

**文件**: `web/src/store/useSessionStore.ts`

**新增类型**:

```typescript
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
```

**`SessionCache` 新增字段**:
```typescript
qualityState: QualityStateData | null;
```

**`emptyCache()` 初始化**:
```typescript
qualityState: null,
```

### 6.4 修改 `types/api.ts` — 扩展 SSEMessage event 类型

**文件**: `web/src/types/api.ts`

```typescript
export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete'
       | 'chat_response' | 'agent_message' | 'heartbeat' | 'connected' | 'message' | 'cancelled'
       | 'quality_result' | 'section_quality' | 'preview_refresh' | 'quality_confirmed';
  data: ProgressData | PhaseData | ErrorData | CompleteData | ChatResponseData | AgentMessageData | any;
}
```

### 6.5 新增前端组件

#### `web/src/components/quality/QualityPanel.tsx`

质量面板主组件，显示整体评分 + 各章节评分 + issue 列表 + 操作按钮。

```
┌─────────────────────────────────────────┐
│  质量评分                            [✕] │
├─────────────────────────────────────────┤
│  整体评分: 72.5 / 100  ⚠ 警告          │
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

#### `web/src/components/quality/IssueRow.tsx`

每条 issue 的交互行，点击「发起修订」将 issue 描述填入聊天输入框。

#### `web/src/components/quality/RevisionHintBar.tsx`

修订完成后预览区域顶部的临时提示条，5秒自动消失，含「一键回滚」按钮。

#### `web/src/components/quality/ConfirmDeliveryDialog.tsx`

确认交付弹窗，展示未解决 issue 清单，用户需二次确认。

#### `web/src/components/quality/SectionNavBar.tsx`

章节导航条，显示在预览 iframe 上方，点击跳转到对应章节锚点。

### 6.6 修改 `MainLayout.tsx` — 集成质量面板

**文件**: `web/src/components/layout/MainLayout.tsx`

在现有布局中，当 `qualityState.phase !== 'confirmed'` 且 `qualityState` 不为 null 时，在报告预览右侧展示 `QualityPanel`。

### 6.7 修改 `DocumentPreview.tsx` — 集成章节导航 + 修订提示条

**文件**: `web/src/components/preview/DocumentPreview.tsx`

- iframe 上方增加 `SectionNavBar`
- iframe 上方增加 `RevisionHintBar`（收到 `preview_refresh` 时显示）
- 收到 `preview_refresh` SSE 时重新加载 iframe

---

## 7. 对话式修订集成

### 7.1 「发起修订」流程

用户在质检面板点击 issue 的「发起修订」按钮后：

1. 前端将 issue 描述填入聊天输入框：
   ```
   【质检问题】核心财务指标章节: 章节结构不完整，缺少分析框架（当前1/7项）
   请帮我修订这部分内容，补充完整的分析框架。
   ```
2. 用户可在此基础上补充具体要求后发送
3. 发送走现有 `POST /api/v1/research/interact` 端点
4. 后端 `_llm_converse()` 处理对话，识别修订意图后调用 `_handle_v2_revision()`
5. 修订完成后，后端自动执行 5.7 中描述的联动逻辑

### 7.2 前端预填机制

在 `IssueRow.tsx` 中点击「发起修订」：

```typescript
function handleStartRevision(issue: QualityIssueData) {
  const chatInput = `【质检问题】${issue.section}: ${issue.message}\n请帮我修订这部分内容。`;
  // 通过 store 或 ref 预填到聊天输入框，不直接发送
  useSessionStore.getState().setPendingInput(chatInput);
}
```

需要在 `ChatPanel` 组件中配合读取 `pendingInput` 并填入输入框。

---

## 8. 版本快照与回滚

### 8.1 快照管理（已实现 ✅）

`src/core/quality/quality_snapshot_manager.py` 已完整实现：

- `create_snapshot()` — 创建 HTML+MD+JSON 三文件快照
- `restore_snapshot()` — 从快照恢复
- `list_snapshots()` — 列出所有快照
- `cleanup_old()` — 清理旧快照

### 8.2 版本栈管理

每次修订执行前，在 `QualitySnapshotManager.create_snapshot()` 后，更新 `quality_state.version_stack`：

```python
version_n = len(quality_data.get("version_stack", []))
version_id = f"v{version_n}"
quality_data["version_stack"].append({
    "id": version_id,
    "created_at": datetime.now().isoformat(),
    "html_path": f"data/snapshots/{session_id}/{version_id}.html",
    "md_path": f"data/snapshots/{session_id}/{version_id}.md",
    "quality_state_snapshot": quality_data,
    "overall_score": quality_data.get("overall_score", 0),
    "label": f"修订前快照 v{version_n}",
})
quality_data["current_version"] = version_id
session["quality_state"] = quality_data
```

### 8.3 回滚流程

见 5.4 中 `_handle_quality_rollback()` 实现。回滚时：
1. 从快照恢复 HTML/MD/quality_state
2. 将 resolved 的 issue 重新标记为 open
3. 推送 `preview_refresh` + `quality_result` SSE 事件

---

## 9. 排版错乱处理

### 9.1 预览自检（已实现 ✅）

`src/core/quality/preview_health.py` 已实现 `check_preview_health()`，检查：
- 表格标签闭合
- 内容稀疏
- 内容膨胀

### 9.2 修订后自检流程

修订完成后，在 `_post_revision_recheck()` 中加入预览自检：

```python
from src.core.quality.preview_health import check_preview_health

old_html_length = 0
old_html_path = f"data/html_reports/{task_id}.html"
if Path(old_html_path).exists():
    old_html_length = len(Path(old_html_path).read_text(encoding="utf-8"))

health = check_preview_health(old_html_path, old_html_length)
if not health["healthy"]:
    SessionStreamer.push_agent_message(
        session_id,
        agent_name="system",
        content=f"修订完成但预览可能存在排版问题: {', '.join(i['message'] for i in health['issues'])}。可使用版本回滚恢复。",
    )
```

### 9.3 修订提示条

前端收到 `preview_refresh` 后显示 `RevisionHintBar`，包含：
- 修订完成提示 + 评分变化
- 如预览自检不通过，显示「排版异常」警告
- 「一键回滚」按钮

---

## 10. 并发与幂等

### 10.1 修订锁

对话修订走现有 `_pending_section_injects` 队列，已有 `_inject_in_progress` 防重入保护。

### 10.2 质检操作锁

对于质检操作（dismiss/reopen/rollback），使用 session 级别轻量锁：

```python
session["_quality_action_lock"] = {
    "locked": True,
    "action": "rollback",
    "started_at": datetime.now().isoformat(),
}
```

### 10.3 幂等性

- 同一 issue 重复点击「忽略」→ 幂等，保持 dismissed
- 同一版本重复点击「回滚」→ 幂等，恢复到目标版本
- 重检操作 → 幂等，返回最新评分
- 确认交付 → 幂等，已确认的再次确认返回当前状态

---

## 11. 修订次数限制

| 限制项 | 阈值 | 原因 |
|--------|------|------|
| 单 issue 修订轮次 | 3次 | 防止对话修订反复无法解决同一问题 |
| 总修订轮次 | 10次 | 防止无限循环 |
| 版本栈深度 | 10个 | 防止快照文件膨胀 |

超过限制后，该 issue 标记为 `max_retries_reached`，前端显示「建议通过对话详细描述修订需求」。

实现方式：在 `QualityIssue` 模型中新增 `revision_count: int = 0` 字段，每次从 `open` 进入 `revising` 时 +1。

---

## 12. 错误处理

| 错误场景 | 处理 |
|----------|------|
| 修订服务调用失败 | SSE 推送错误信息，issue 从 `revising` 回退为 `open` |
| 预览生成失败 | SSE 推送警告，提示用户可通过对话继续修订 |
| 排版自检失败 | 修订提示条中显示排版警告，提供[回滚]选项 |
| 修订超限 | issue 标记 `max_retries_reached` |
| 并发操作冲突 | 轻量锁拦截，返回 409 Conflict |
| 快照恢复失败 | 返回错误，提示用户刷新页面 |
| 重检失败 | 保持当前评分不变，SSE 推送重检失败通知 |

---

## 13. 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `web/src/components/quality/QualityPanel.tsx` | 质量面板主组件 |
| `web/src/components/quality/IssueRow.tsx` | Issue 交互行 |
| `web/src/components/quality/RevisionHintBar.tsx` | 修订提示条 |
| `web/src/components/quality/ConfirmDeliveryDialog.tsx` | 确认交付对话框 |
| `web/src/components/quality/SectionNavBar.tsx` | 章节导航条 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/core/session_streamer.py` | 修复 `push_quality_confirmed()` bug（移除未定义变量引用） |
| `src/agents/fixed_agents/quality_check_agent.py` | `check_by_sections()` 返回稳定 issue ID + state |
| `src/api/research_api.py` | 重写 `handle_quality_action()` + `get_quality_state()` + 新增 5 个 handler + `_post_revision_recheck()` + `_handle_v2_revision()` 修订联动 |
| `src/content/content_orchestrator.py` | HTML 生成时为章节添加锚点 id |
| `web/src/types/api.ts` | `SSEMessage.event` 扩展联合类型 + QualityStateData 等接口 |
| `web/src/lib/sse.ts` | `subscribeSession()` 注册 quality_result / section_quality / preview_refresh / quality_confirmed 事件监听 |
| `web/src/hooks/useProgress.ts` | `UseSessionStreamOptions` 扩展 + `useSessionStream()` 传递新回调 |
| `web/src/store/useSessionStore.ts` | `SessionCache` 新增 qualityState 字段 + 相关类型 |
| `web/src/components/layout/MainLayout.tsx` | 集成 QualityPanel |
| `web/src/components/preview/DocumentPreview.tsx` | 集成 SectionNavBar + RevisionHintBar + preview_refresh 刷新 |

### 已存在无需修改的文件

| 文件 | 说明 |
|------|------|
| `src/core/quality/quality_state.py` | ✅ 完整实现 |
| `src/core/quality/quality_snapshot_manager.py` | ✅ 完整实现 |
| `src/core/quality/preview_health.py` | ✅ 完整实现 |
| `src/core/quality/__init__.py` | ✅ 已有 |
| `src/api/main.py` | ✅ 路由已注册 |

---

## 14. 实施优先级

| 优先级 | 内容 | 依赖 | 涉及文件 |
|--------|------|------|----------|
| **P0-1** | 修复 `push_quality_confirmed()` bug | 无 | `session_streamer.py` |
| **P0-2** | `check_by_sections()` 生成稳定 issue ID | 无 | `quality_check_agent.py` |
| **P0-3** | 重写 `handle_quality_action()` + `get_quality_state()` + 5个handler | P0-2 | `research_api.py` |
| **P0-4** | `_handle_v2_revision()` 修订联动 + `_post_revision_recheck()` | P0-2, P0-3 | `research_api.py` |
| **P0-5** | 前端 SSE 扩展 + qualityState store | 无（可与P0-1~4并行） | `sse.ts`, `useProgress.ts`, `useSessionStore.ts`, `api.ts` |
| **P0-6** | QualityPanel + IssueRow 前端组件 | P0-5 | `QualityPanel.tsx`, `IssueRow.tsx`, `MainLayout.tsx` |
| **P1-1** | 章节导航条 + HTML 锚点 | P0-6 | `SectionNavBar.tsx`, `content_orchestrator.py`, `DocumentPreview.tsx` |
| **P1-2** | 修订提示条 + 排版保护 | P0-4, P0-6 | `RevisionHintBar.tsx`, `DocumentPreview.tsx` |
| **P1-3** | 确认交付对话框 | P0-3, P0-6 | `ConfirmDeliveryDialog.tsx` |
| **P2-1** | 修订次数限制 + 并发锁 | P0-3 | `research_api.py` |
| **P2-2** | 预览自检集成 | P0-4 | `research_api.py` |

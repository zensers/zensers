# 知识模块前端集成 — 深度分析设计文档（终版）

## 1. 执行摘要

对项目知识模块的完整代码审计已完成。核心结论：

- **后端 80% 就绪**：`KnowledgeImporter.import_url()`, `KnowledgeManager`, `UserKnowledgeBank` 均已实现
- **调度器 50% 就绪**：`DreamModeScheduler` 已存在且有 `background_loop`，但仅管理知识提取（非知识导入）
- **SSE 基础设施 100% 就绪**：`ProgressStreamer` + `SessionStreamer` 无需修改
- **前端 0% 未开始**：API 端点、路由、组件、Store、Hook 均需新建
- **最大单一缺口**：`main.py` 中既无 `DreamModeScheduler` 初始化，也无知识导入 API 端点

---

## 2. 关键设计发现

### 2.1 两个 KnowledgeCompiler 并存 — 无代码共用

| 编译器 | 位置 | 用途 | 接口 | 存储 |
|--------|------|------|------|------|
| **知识库编译器** | `src/core/memory/knowledge/compiler.py` (830行) | `KnowledgeImporter` 内置 | `compile_research(raw_content, source_info)` → `CompiledKnowledge` | 文件系统: knowledge_root/concepts/, entities/, relations/ |
| **Orchestrator 编译器** | `src/core/orchestrator/aggregation/knowledge_compiler.py` (439行) | Orchestrator Agent 结果处理 | `compile(agent_id, result, topic)` → `List[KnowledgePage]` | SQLite (通过 knowledge_bank) |

**影响**: `import_url()` → `compile_research()` 走的是知识库编译器（文件系统存储），而非通过 `UserKnowledgeBank` 的 SQLite 存储。这意味着通过 URL 导入的知识会写入 `knowledge_root/` 目录，但**不会出现在 `UserKnowledgeBank` 的 SQLite 搜索中**。

**缓解**: 在 `import_url()` 中增加 `store_to_bank=True` 选项，将编译结果写入 `UserKnowledgeBank`。

### 2.2 DreamModeScheduler 的精确分析

```
DreamModeScheduler (dream_scheduler.py:56)
├── _is_main_task_running: bool          ← 主任务是否运行
├── _state: DreamModeState               ← IDLE/RUNNING/PAUSED/COMPLETED/ERROR
├── config: DreamModeConfig              ← 包含 idle_check_interval(10s), batch_size(10) 等
├── raw_data_store: RawResearchDataStore ← 研究资料暂存区（SQLite）
├── _extraction_phase: KnowledgeExtractionPhase
├── _background_task: asyncio.Task
│
├── on_main_task_started()              ← 立即暂停提取
├── on_main_task_completed()            ← 存储资料 + 检查触发
├── start_background_loop()             ← 每10秒轮询
├── _start_extraction()                 ← 提取知识（已实现 + async）
├── run_now()                          ← 手动触发
├── stop/stop_background()
│
└── _maybe_trigger_extraction() 中内联检查 _is_main_task_running  ← 当前暂停机制
```

**当前能力**:
- 调度器每10秒检查 `_is_main_task_running` + `pending_count` 
- 仅在用户空闲时处理待提取资料
- `start_background_loop()` 是 `async def` 循环，可扩展

**扩展方案（子组件模式）**:
```python
class DreamModeScheduler:
    def __init__(self, ...):
        self.import_manager = ImportTaskManager(self)  # 子组件
    
    @property
    def should_pause(self):
        return self._is_main_task_running or self._resource_monitor.is_overloaded()
    
    async def _extended_background_loop(self):
        while True:
            if self._is_main_task_running:
                await asyncio.sleep(self.config.idle_check_interval)
                continue
            # 优先处理导入任务（比知识提取优先级高）
            if not self.import_manager.queue.empty():
                _, task_id = self.import_manager.queue.get_nowait()
                await self._run_import(task_id)
                continue  # 不 sleep，立刻检查下一个
            # 知识提取
            pending = self.raw_data_store.get_pending_count()
            if pending >= self.config.trigger_on_pending_threshold:
                await self._start_extraction()
            await asyncio.sleep(self.config.idle_check_interval)
```

### 2.3 import_url() 完整执行路径（含所有风险点）

```
import_url(url, auto_extract=True, timeout=30, max_size=10MB, retries=3)
│
├── [Phase 1: URL验证] validate_url(url) — DNS查询(socket.getaddrinfo)
│   ├── 协议检查 (http/https only)
│   ├── IP黑名单检查 (SSRF防护)
│   └── DNS解析 — 同步阻塞，最长~5s（socket默认超时）
│   ⚠️ 线程池执行
│
├── [Phase 2: HTTP下载] urllib.request.urlopen(req, timeout=30)
│   ├── HTTP请求 — 同步阻塞，最长30s
│   ├── Content-Length检查 (超过10MB → 失败)
│   └── response.read(max_size+1) — 全量读入内存
│   ⚠️ 线程池执行 | ⚠️ 不可中断（urlopen不支持中断） | ⚠️ 无进度回调
│   ⚠️ 重试3次，指数退避未实现（固定重试间隔）
│
├── [Phase 3: HTML提取] _extract_text_from_html(html)
│   ├── 正则剔除 script/style/注释
│   ├── 正则剔除 HTML 标签
│   ├── 空白整理
│   └── 提取 <title>
│   ⚠️ 纯正则 | 无 Readability 类结构化提取 | 约O(n)时间
│
└── [Phase 4: 知识编译] compiler.compile_research(text, source_info)
    ├── 正则实体提取 (公司/人物/产品模式)
    ├── 概念关键词匹配
    ├── 关系提取
    └── 保存到文件系统
    ⚠️ 线程池执行 | ⚠️ 无进度回调 | ⚠️ 写入文件系统非 SQLite
```

### 2.4 前端命令模式参考（/template 实现分析）

`ChatPanel.handleSend()` 中 `/template` 的实现是一个纯前端命令模式：

```
ChatPanel.handleSend(text)
├── parseTemplateCommand(text)            ← 纯前端正则匹配
│   ├── /template → 显示模板列表
│   └── /template <id> [topic] → 匹配模板
├── RESEARCH_TEMPLATES (前端数组定义)      ← 无后端 API 调用
├── formatTemplateMessage(template, topic) ← 构造聊天消息
├── useResearchStore.setActiveTemplate()   ← 更新 store
└── 用户点击 "Start Research" → quickStartResearch()
    └── POST /api/v1/research/quick-start  ← 此时才调用后端
```

**对 /knowledge 命令的参考价值**:
- 命令解析模式可直接复用 (`/knowledge <url>`)
- 但 /knowledge 需要**立即调用后端 API**（url 验证和任务注册不能在纯前端完成）
- 与 /template 不同，/knowledge 不能纯前端响应

### 2.5 main.py 初始化缺口分析

```python
# main.py (当前)
_container = configure_container()
_knowledge_manager = resolve_or_none(KnowledgeManager)   # ✅ 有
# DreamModeScheduler 未初始化                                # ❌ 无

# main.py (需要)
_knowledge_manager = resolve_or_none(KnowledgeManager)
_dream_scheduler = DreamModeScheduler(...)                 # 新增
_import_task_manager = ImportTaskManager(_dream_scheduler) # 新增
_dream_scheduler.import_manager = _import_task_manager
_dream_scheduler.start_background()                        # 启动后台循环
```

---

## 3. 集成方案

### 3.1 后端新增组件

| 组件 | 文件 | 工作量 | 说明 |
|------|------|--------|------|
| `knowledge_api.py` | `src/api/knowledge_api.py` | ~200行 | 4-5个端点，参考 research_api.py |
| `ImportTaskManager` | 嵌入 dream_scheduler.py 或独立 | ~250行 | 任务状态管理 + SQLite 持久化 |
| 扩展 DreamModeScheduler | dream_scheduler.py | ~80行 | 增加 import_manager 子组件 |
| 增强 import_url() | importer.py | ~50行 | 增加 progress_callback + interrupt_check |

### 3.2 新增 API 端点契约

```
POST /api/v1/knowledge/import-url
  Request:  { url: string, auto_extract?: boolean }
  Response: { task_id: string, url: string, estimated_size?: number, max_size: number }
  Errors:   400 URL validation failed | 413 URL exceeds max size
  Note:     注册 ImportTask，后台异步执行

GET /api/v1/knowledge/tasks?task_id=xxx
  Response: { task_id, status, progress, phases, created_at, error? }
  Note:     轮询降级用

POST /api/v1/knowledge/tasks/{task_id}/cancel
  Response: { status: "cancelled" }

GET /api/v1/knowledge/entities?q=&type=&page=&limit=
  Response: { items: [...], total, page, limit }

DELETE /api/v1/knowledge/entities/{id}
  Response: { status: "deleted" }
```

### 3.3 前端新增组件

```
web/src/
  app/
    knowledge/page.tsx                    # 知识管理页面（新路由）
  components/
    chat/KnowledgeImportPanel.tsx         # 导入进度面板（新, ~150行）
    knowledge/                            # 新建目录
      KnowledgePage.tsx                   # 知识管理页面主体
      KnowledgeSearchBar.tsx              # 搜索栏
      KnowledgeEntityCard.tsx             # 条目卡片
      KnowledgeImportHistory.tsx          # 导入历史
  hooks/
    useKnowledgeImport.ts                 # 新建（SSE + 轮询，参考 useProgress）
    useKnowledgeSearch.ts                 # 新建
  store/
    useKnowledgeStore.ts                  # 新建（Zustand，参考 useResearchStore）
  lib/
    knowledge.ts                          # 新建（命令解析 + 格式化）
    api.ts                                # 修改（添加知识 API 方法）
  types/
    knowledge.ts                          # 新建（类型定义）
```

### 3.4 SSE 事件流设计

知识导入任务的 SSE 事件类型与现有研究任务完全兼容：

```
event: phase_start
data: {"task_id": "know_import_xxx", "phase_id": "downloading", "phase_name": "下载中"}

event: progress
data: {"task_id": "know_import_xxx", "phase_id": "downloading", "progress": 0.45, "message": "45% - 下载中 (10.2MB/22.5MB)"}

event: phase_complete
data: {"task_id": "know_import_xxx", "phase_id": "downloading", "status": "completed"}

event: progress
data: {"task_id": "know_import_xxx", "phase_id": "parsing", "progress": 0.6, "message": "解析中..."}

event: progress
data: {"task_id": "know_import_xxx", "phase_id": "compiling", "progress": 0.8, "message": "编译中..."}

event: complete
data: {"task_id": "know_import_xxx", "status": "completed", "result": {"pages_created": 5, "entities_extracted": 12}}

event: error
data: {"task_id": "know_import_xxx", "code": "DOWNLOAD_FAILED", "message": "URL 下载超时"}

event: cancelled
data: {"task_id": "know_import_xxx", "reason": "用户取消导入"}
```

### 3.5 前端 KnowledgeImportPanel 交互

```
用户输入: /knowledge https://arxiv.org/pdf/2401.12345

轮到空闲时执行:

┌──────────────────────────────────────────┐
│ 📚 知识导入                              │
│   https://arxiv.org/pdf/2401.12345       │
│                                          │
│  ████████████░░░░░░ 65%                  │
│                                          │
│  阶段1: 下载中...    ✅ 22.5MB/22.5MB    │
│  阶段2: 解析中...    ⏳ 45%              │
│  阶段3: 编译中...    ⬜ 等待中            │
│                                          │
│  知识提取: 12 个实体 / 5 个数据点        │
│                                          │
│  创建于: data/users/default/knowledge/   │
│                                          │
│  [取消导入]  [查看知识库 →]              │
└──────────────────────────────────────────┘

导入完成后:

┌──────────────────────────────────────────┐
│ 📚 知识导入完成                          │
│                                          │
│  ✅ 成功: 从 URL 提取了 12 个实体        │
│     → 查看知识库 →                       │
└──────────────────────────────────────────┘

同时聊天框推送消息:
┌──────────────────────────────────────────┐
│ 🤖 Assistant                             │
│ 📚 **知识导入完成**                      │
│ 来源: `https://arxiv.org/pdf/2401.12345` │
│ - 提取了 **12** 个实体                   │
│ - 生成了 **5** 个数据点                  │
│ - 存储于：知识库                         │
│                                          │
│ 输入 `/knowledge` 查看知识库。           │
└──────────────────────────────────────────┘
```

---

## 4. 风险与缓解详细矩阵

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|---------|
| R1 | `urllib.request.urlopen()` 最长阻塞30秒 — 如果在事件循环中执行将冻结所有 HTTP 响应 | 高 | **严重** | 强制 `run_in_executor`；API 层定义 `background_tasks` 管理 |
| R2 | 10MB URL 限制 — 用户链接大 PDF 文档时直接返回 413 | 高 | 中 | 前端在 `/knowledge` 命令解析时提示大小限制；后端返回友好错误；未来考虑扩展至 50MB |
| R3 | 下载不可中断 — `urlopen` 不支持线程安全的取消，`_cancel_event.set()` 无法中断正在进行的 HTTP 请求 | 中 | 中 | 下载完成后才检查取消标志；大文件下载期间用户只能等待下载完成才能取消 |
| R4 | 编译结果写入文件系统而非 `UserKnowledgeBank`（SQLite）— 搜索 `/api/v1/knowledge/entities` 时不会返回 | 中 | **高** | 在 `import_url()` 中增加 `store_to_bank=True` 参数，编译后通过 `knowledge_bank` API 写入 SQLite |
| R5 | DreamModeScheduler 在 `main.py` 未初始化 — 导致导入任务有创建无调度 | 高 | **严重** | API startup 事件中创建并 start_background() |
| R6 | URL 导入的 HTML 提取仅用正则 — 对于复杂/嵌套页面提取质量差 | 中 | 中 | 先用现有实现；未来可集成 readability-lxml 或 markdownify 提高质量 |
| R7 | 前端 SSE 连接断开后 KnowledgeImportPanel 状态丢失 | 低 | 中 | 复用 useProgress 的5秒轮询降级 + SessionManager 持久化 |
| R8 | 用户连续导入多个 URL — 队列逐个下载导致体验差 | 低 | 低 | ImportTaskManager 队列管理 + 批量进度展示 |
| R9 | 知识条目的语义去重 — 同一内容不同 URL 导入后产生重复实体 | 中 | 中 | 当前使用 MD5 manifest 去重（文件名级）；语义去重留作后续 |

---

## 5. 实现顺序

### Phase 1: 后端基础设施（1.5天）
1. `ImportTaskManager` 类（任务状态管理 + SQLite 持久化）
2. 扩展 `DreamModeScheduler._extended_background_loop()` — 导入任务调度
3. 增加 `KnowledgeManager.import_url()` 代理（补齐 `source_info` 透传 + `store_to_bank` 选项）

### Phase 2: 后端 API（1天）
1. `knowledge_api.py` — 4个端点
2. `main.py` 初始化：DreamModeScheduler + ImportTaskManager
3. 集成测试

### Phase 3: 前端核心（2天）
1. `types/knowledge.ts` + `lib/knowledge.ts`
2. `api.ts` 知识方法
3. `ChatPanel.tsx` — `/knowledge` 命令检测
4. `KnowledgeImportPanel.tsx` — 进度面板
5. `useKnowledgeImport.ts` — SSE + 轮询

### Phase 4: 知识管理页面（1天）
1. `/knowledge` 路由 + `KnowledgePage.tsx`
2. 搜索/浏览/删除
3. 导入历史
4. 侧边栏入口

### Phase 5: 打磨（0.5天）
1. 大文件提醒
2. 错误处理完善
3. 恢复测试

---

## 6. 设计决策记录

| 决策 | 选项 | 结论 | 理由 |
|------|------|------|------|
| 命令格式 | `/knowledge <url>` vs `/knowledge import <url>` | **`/knowledge <url>`** | 更简洁；bare `/knowledge` 显示知识库概览 |
| 调度模型 | 独立 ImportScheduler vs DreamModeScheduler 子组件 | **子组件模式** | 复用现有的主任务检测 + 后台循环，符合组合模式设计 |
| 进度推送 | 新建 KnowledgeStreamer vs 复用 ProgressStreamer | **复用 ProgressStreamer** | 事件格式完全兼容，无需新增 SSE 端点 |
| 任务存储 | 独立 DB vs DreamMode 共用 | **独立 SQLite** | 隔离关注点，不影响现有 DreamMode 状态 |
| 知识搜索 | 直接查 SQLite vs 通过知识库 API | **通过 knowledge_bank API** | 统一搜索入口，确保搜索覆盖所有来源 |
| 大文件策略 | 下载后解析 vs 拒绝 | **拒绝（>10MB）** | 纯 urllib 无条件对流式分块下载；提示用户下载后通过文件导入（未来功能） |

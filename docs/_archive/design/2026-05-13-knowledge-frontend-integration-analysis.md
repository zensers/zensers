# 知识模块前端集成方案 — 调研分析与设计

## 1. 调研结论总览

### 1.1 后端现状（已完成，可直接对接）

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| `KnowledgeImporter` | `src/core/memory/knowledge/importer.py` (1216行) | ✅ 完整实现 | 支持文件/目录/URL 导入、SSRF 防护、文件大小限制、manifest 去重 |
| `UserKnowledgeBank` | `src/core/memory/knowledge_bank.py` (1033行) | ✅ 完整实现 | 封装 importer + compiler + 快速进化 + 学习记录 |
| `KnowledgeManager` | `src/core/memory/knowledge_manager.py` (427行) | ✅ 完整实现 | 统一入口，委托到 UserKnowledgeBank |
| `import_file()` | knowledge_bank.py:715 | ✅ 已实现 | 含 `progress_callback` 和 `interrupt_check` 参数位置 |
| `import_url()` | importer.py:1004 | ✅ 已实现 | 支持 URL 导入、HTML 提取、自动知识编译 |
| `import_directory()` | knowledge_bank.py:741 | ✅ 已实现 | 批量目录导入 |
| `ProgressStreamer` | `src/core/progress_streamer.py` (676行) | ✅ 完整实现 | SSE 实时推送，多订阅者，自动清理 |
| `SessionStreamer` | `src/core/session_streamer.py` (287行) | ✅ 完整实现 | 持久化 Session SSE，不随任务结束关闭 |
| `DreamModeScheduler` | 存在于 src/core 中 | ✅ 存在 | 后台任务调度器，需扩展以支持知识导入 |
| Backend API 端点 | `src/api/main.py` | ❌ **未实现** | 没有任何 `/api/v1/knowledge/*` 端点 |
| `KnowledgeManager` 在 API 层初始化 | main.py:172-178 | ✅ 已集成 | `_knowledge_manager` 全局可用 |

### 1.2 前端现状（需要新建）

| 模块 | 现状 | 说明 |
|------|------|------|
| 聊天命令解析 | ✅ ChatPanel.handleSend() 有 `/template` 模式可复用 | 需扩展 `/knowledge <url>` 命令 |
| SSE 连接 | ✅ useProgress + useSessionStream hook | 可直接复用 |
| 状态管理 | ✅ Zustand + useResearchStore 模式 | 需新建 useKnowledgeStore |
| API 客户端 | ✅ api.ts 有 Axios 实例 | 需添加知识 API 方法 |
| 类型定义 | ✅ types/api.ts 有 SSE/Research 类型 | 需添加知识相关类型 |
| 知识管理页面 | ❌ 无 `/knowledge` 路由 | 需新建 |
| 知识导入面板 | ❌ 无 KnowledgeImportPanel 组件 | 需新建 |
| 侧边栏知识入口 | ❌ Header 无知识入口按钮 | 需添加 |

---

## 2. 已有设计方案回顾

现有 `docs/superpowers/specs/2026-05-11-knowledge-import-command-design.md` 覆盖了：

- **执行模型**: `async def` + `run_in_executor` 统一模型
- **ProgressProxy**: 线程安全桥接，deque + `call_soon_threadsafe`
- **ImportTaskManager**: SQLite 持久化任务状态管理 + 暂停/恢复/中断
- **DreamModeScheduler 扩展**: 持有 ImportTaskManager 子组件，空闲时处理
- **SystemResourceMonitor**: CPU/内存/磁盘 IO 监控，迟滞机制
- **路径安全检查**: 白名单 + `os.path.realpath`
- **流式解析**: `parse_file_stream` + 中断检查点
- **前端 KnowledgeImportPanel**: 文件级进度展示

**该方案的核心设计仍然有效**，但它侧重**本地文件导入** (`/knowledge import <path>`)。

---

## 3. 用户诉求与关键差异分析

用户期望：**`/knowledge <document_url>`** — 通过 URL 导入网页文档

### 关键差异

| 维度 | 原方案 (`/knowledge import <path>`) | 用户诉求 (`/knowledge <url>`) |
|------|------|------|
| 输入类型 | 本地文件路径 | 网页 URL |
| 安全性 | 路径遍历防护 + 白名单 | SSRF 防护（已有） |
| 文件大小 | 受限于磁盘 IO 和内存 | 受限于网络带宽和响应大小 |
| 进度展示 | 文件读取阶段：逐页/逐块 | URL 阶段：下载 + 解析 + 编译 |
| 耗时模式 | 大文件读取慢 | 大文件下载慢（网络 IO） |
| 阻塞风险 | 大文件读取阻塞事件循环 | 大文件下载阻塞网络请求 |

### 核心设计目标修正

```
原始目标：
1. ✓ 前端通过斜杠命令触发
2. ✓ 混合执行模式
3. ✓ 实时进度反馈
4. ✗ 知识浏览/搜索/删除 (仍然需要)
5. ✓ 不阻塞用户其他任务
6. ✓ 自动响应主任务
7. ✓ 利用空闲时间处理

调整重点：
- 输入从本地路径改为 URL
- 进度阶段从 "扫描→解析→编译" 调整为 "下载→解析→编译"
- URL 特有的安全问题已由后端处理，前端只需传递 URL 字符串
- 无需白名单配置——但可以增加允许域名白名单选项
```

---

## 4. 推荐架构

### 4.1 整体架构

```
用户输入: /knowledge https://example.com/report
                │
                ▼
┌──────────────────────────────────────────────────────┐
│                  前端 (Next.js)                        │
│                                                       │
│  ChatPanel.handleSend()                               │
│    ├─ parseKnowledgeCommand(text)                     │
│    ├─ 无 URL → 显示使用说明 + 已有知识概览             │
│    ├─ 有 URL → POST /api/v1/knowledge/import-url      │
│    └─ 返回 task_id + 文件信息                          │
│                                                       │
│  KnowledgeImportPanel (新建)                          │
│    ├─ SSE 订阅: /api/v1/stream/{task_id}              │
│    ├─ 阶段: 下载中 → 解析中 → 编译中 → 完成            │
│    ├─ 完成通知: 聊天消息 + 面板折叠                     │
│    └─ 轮询降级: 5秒间隔 GET /api/v1/knowledge/tasks    │
│                                                       │
│  KnowledgePage (新建)                                  │
│    └─ /knowledge 路由                                 │
│       ├─ 已导入列表（搜索/过滤）                        │
│       ├─ 导入历史 + 状态                               │
│       └─ 删除/管理                                     │
└──────────────────────────┬───────────────────────────┘
                           │ POST /api/v1/knowledge/import-url
                           ▼
┌──────────────────────────────────────────────────────┐
│                   后端 (FastAPI)                       │
│                                                       │
│  knowledge_api.py (新建)                               │
│  ├─ POST /api/v1/knowledge/import-url                 │
│  │   ├─ 接收: { url, auto_extract }                   │
│  │   ├─ 验证 URL 合法性                                │
│  │   ├─ 注册 ImportTask (通过 ImportTaskManager)       │
│  │   ├─ 返回: { task_id, url, estimated_size }        │
│  │   └─ asyncio.create_task(_run_import(...))         │
│  │                                                     │
│  ├─ GET /api/v1/knowledge/tasks                       │
│  │   └─ 查询任务状态列表 (轮询降级)                     │
│  │                                                     │
│  ├─ POST /api/v1/knowledge/{task_id}/cancel           │
│  │   └─ 取消导入任务                                   │
│  │                                                     │
│  ├─ GET /api/v1/knowledge/entities                    │
│  │   └─ 搜索已导入的知识实体                            │
│  │                                                     │
│  └─ DELETE /api/v1/knowledge/entities/{id}            │
│      └─ 删除知识条目                                   │
│                                                       │
│  ImportTaskManager (新增, 参照原方案)                   │
│  ├─ 任务状态: queued → downloading → parsing           │
│  │           → compiling → completed/failed            │
│  ├─ SQLite 持久化                                      │
│  └─ 中断恢复                                           │
│                                                       │
│  DreamModeScheduler (扩展)                             │
│  ├─ 持有 ImportTaskManager                             │
│  ├─ should_pause() → 复用主任务检测                    │
│  ├─ background_loop → 调度导入任务                     │
│  └─ SystemResourceMonitor → 资源感知                    │
│                                                       │
│  KnowledgeManager (已有，扩展 import_url 回调)          │
│  └─ import_url(url, auto_extract, callbacks)           │
│       └─ 委托至 bank.importer.import_url()             │
└──────────────────────────────────────────────────────┘
```

### 4.2 导入流程状态机

```
                   ┌──────────┐
                   │  queued  │
                   └────┬─────┘
                        │ (调度器选择此任务)
                   ┌────▼─────┐
          ┌────────│downloading│◄────────┐
          │        └────┬─────┘         │
          │             │ (下载完成)      │
          │        ┌────▼─────┐         │
          │        │  parsing  │         │
          │        └────┬─────┘         │
          │             │ (解析完成)      │
          │        ┌────▼──────┐        │
          │        │ compiling │        │
          │        └────┬──────┘        │
          │             │ (编译完成)      │
          │        ┌────▼─────┐         │
          │        │completed │         │
          │        └────┬─────┘         │
          │             │               │
          │        ┌────▼─────┐         │
          ├────────│  paused  │─────────┘
          │        └──────────┘   (暂停后恢复→重新下载)
          │
          │   should_pause() == true 或 用户暂停
          │   → 暂停 → 标记 checkpoint
          │   → 主任务结束后重新入队
          │
          │   任务失败 → failed 状态
          │   用户取消 → cancelled 状态
          └────────────────────────────────────
```

### 4.3 前端组件树

```
src/
  app/
    knowledge/                          # 知识管理页面（新路由）
      page.tsx                          # 知识库概览 + 搜索
    page.tsx                            # 主聊天页（不变）

  components/
    chat/
      ChatPanel.tsx                     # 修改：添加 /knowledge 命令解析
      ChatInput.tsx                     # 修改：添加 /knowledge 占位提示
      KnowledgeImportPanel.tsx          # 新建：导入进度面板
    knowledge/                          # 新建目录
      KnowledgePage.tsx                 # 知识管理页面主体
      KnowledgeSearchBar.tsx            # 知识搜索栏
      KnowledgeEntityCard.tsx           # 知识条目卡片
      KnowledgeImportHistory.tsx        # 导入历史列表

  hooks/
    useKnowledgeImport.ts               # 新建：导入任务 hook（SSE + 轮询）
    useKnowledgeSearch.ts               # 新建：知识搜索 hook

  store/
    useKnowledgeStore.ts                # 新建：知识状态管理

  lib/
    api.ts                              # 修改：添加知识 API 方法
    knowledge.ts                        # 新建：命令解析工具函数

  types/
    knowledge.ts                        # 新建：知识相关类型定义
```

### 4.4 关键交互流程

```
用户: /knowledge https://arxiv.org/pdf/2401.12345

1. ChatPanel.handleSend() 检测到 /knowledge 前缀
2. 调用 parseKnowledgeCommand() 解析 URL
3. POST /api/v1/knowledge/import-url { url, auto_extract: true }
4. 后端：
   a. URL 格式 + SSRF 安全检查
   b. 注册 ImportTask → task_id
   c. 返回 { task_id, url, status: "queued" }
5. 前端：
   a. 聊天框显示 "📚 开始导入知识..." 消息
   b. 弹出 KnowledgeImportPanel 进度面板
   c. SSE 订阅 /api/v1/stream/{task_id}
   d. 实时展示：下载 % → 解析 → 编译 → 完成
6. 完成后：
   a. KnowledgeImportPanel 显示完成摘要（实体数、页数）
   b. 聊天框推送 "📚 导入完成：提取 X 个实体"
   c. 面板可折叠，用户可继续聊天

空闲时段执行细节：
1. ImportTaskManager 注册任务后状态为 queued
2. DreamModeScheduler.background_loop 轮询队列
3. 如果主任务正在运行 → 跳过，等待下一轮
4. 如果资源过载（CPU > 50% / 内存 > 80%） → 跳过
5. 如果系统空闲 → 取出队列任务，执行 _run_import()
6. _run_import 内部每完成一个 url 后检查 should_pause()
7. 如果主任务启动或用户操作 → 暂停，下次空闲时继续
```

---

## 5. 重点风险与注意事项

### 5.1 URL 导入的特殊性

- **幂等性**：同一 URL 多次导入 → 后台已通过 manifest 去重
- **断点续传**：URL 下载不支持字节级续传 → 暂停后恢复需重新下载
- **大小限制**：目前 `MAX_URL_SIZE = 10MB`，后端用纯 urllib 下载
- **大文件策略**：超过 10MB 的 URL 内容 → 在前端直接提示 "内容过大，建议下载后通过文件导入"

### 5.2 CLI 导入的知识仍需后端 API

- `KnowledgeImporter` 已支持文件导入，但目前仅有 CLI 入口
- 如果需要将来支持文件导入，需增加文件上传端点或文件路径白名单验证
- **当前阶段只实现 URL 导入**，文件导入留作后续

### 5.3 SSE 复用

- 完全复用现有的 `ProgressStreamer` + `/api/v1/stream/{task_id}` 端点
- 复用 `SessionStreamer` 推送完成通知到聊天
- `useProgress` hook 可直接用于知识导入任务（阶段事件格式相同）

### 5.4 状态持久化

- DreamModeScheduler/ImportTaskManager 用 SQLite 持久化任务状态
- 服务重启后恢复未完成的导入任务
- 前端轮询降级机制复用现有 `useProgress` 的轮询逻辑

---

## 6. 实现顺序建议

### Phase 1: 后端 API（2天）
1. 创建 `knowledge_api.py` — `POST /api/v1/knowledge/import-url`
2. 创建 `ImportTaskManager`（参照原设计文档）
3. 扩展 `DreamModeScheduler.background_loop` — 调度导入任务
4. 添加知识查询 API — `GET/DELETE /api/v1/knowledge/entities`
5. 添加任务状态查询 + 取消 — `GET/POST /api/v1/knowledge/tasks`

### Phase 2: 前端核心命令（2天）
1. `types/knowledge.ts` — 知识相关类型定义
2. `lib/knowledge.ts` — `/knowledge` 命令解析工具函数
3. 修改 `ChatPanel.tsx` — 添加 `/knowledge` 命令检测
4. `store/useKnowledgeStore.ts` — 知识状态管理
5. `api.ts` 添加知识 API 方法
6. `KnowledgeImportPanel.tsx` — 导入进度面板

### Phase 3: 知识管理页面（1-2天）
1. `/knowledge` 路由 + `KnowledgePage.tsx`
2. 知识搜索/浏览
3. 导入历史展示
4. 侧边栏知识入口

### Phase 4: 空闲调度优化（1天）
1. `SystemResourceMonitor` 集成
2. 暂停/恢复全链路测试
3. 服务重启恢复验证

---

## 7. 与现有设计方案的关系

本方案是对 `2026-05-11-knowledge-import-command-design.md` 的**补充和修正**：

| 原设计方案 | 本方案 |
|-----------|--------|
| `/knowledge import <path>` 本地文件 | `/knowledge <url>` 网络 URL |
| 路径安全检查（白名单） | URL 安全检查（SSRF防护，后端已有） |
| parse_file_stream 流式解析 | URL 下载 + HTML 提取文本 |
| 文件级进度展示 | URL 下载进度 + 解析进度 |
| 需要白名单配置 | 无需用户配置（仍可加域名白名单） |

**保留的原方案设计**：
- ✅ `ProgressProxy` 线程安全桥接
- ✅ `ImportTaskManager` 任务状态管理 + SQLite 持久化
- ✅ `DreamModeScheduler` 扩展方式
- ✅ `SystemResourceMonitor` 资源感知调度
- ✅ 中断检查点 + 暂停/恢复模式
- ✅ SSE + 轮询降级
- ✅ 完成通知通过 SessionStreamer 推送

---

## 8. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| URL 文档下载过慢阻塞事件循环 | 中 | 高 | 下载在 run_in_executor 中执行 |
| 大 URL 超过 10MB 限制 | 低 | 中 | 前端提示下载后文件导入 |
| 知识过多拖慢搜索响应 | 中 | 中 | 分页 + 全文索引（FT5 已有） |
| DreamModeScheduler 现有逻辑冲突 | 低 | 高 | 子组件模式隔离，不侵入现有 core memory consolidation |
| 前端页面未响应 SSE 事件 | 低 | 中 | 轮询降级机制（已有） |

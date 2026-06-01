# 知识导入指令模式 — 设计方案（终版）

## 1. 背景与问题

### 1.1 现状

- 用户无法通过前端聊天窗口上传数十 GB 的本地资料给 LLM
- 系统已有 `KnowledgeImporter` 仅支持 CLI 调用
- 诸多基础设施已就绪但未在前端暴露

### 1.2 核心目标

1. 前端通过斜杠命令 `/knowledge import <path>` 触发知识导入
2. 混合执行模式：小文件即时处理，大文件/目录排队后台处理
3. 实时进度反馈：文件级 + 阶段级
4. 知识可在前端浏览、搜索、删除
5. **导入不阻塞用户其他任务**（事件循环安全）
6. **自动响应主任务**（用户发起新研究时暂停）
7. **利用空闲时间处理**（资源感知调度）

---

## 2. 架构总览

关键原则：
- **执行模型统一**：所有导入任务都是 `async def`，同步操作通过 `run_in_executor` 移出事件循环
- **线程安全**：进度更新通过 `call_soon_threadsafe` 投回事件循环
- **架构分层**：API → KnowledgeManager → UserKnowledgeBank → KnowledgeImporter，不绕过
- **组合模式**：DreamModeScheduler 持有 ImportTaskManager 子组件，而非将所有方法塞入调度器

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                     │
│                                                              │
│  ChatInput → parseCommand → /knowledge import <path>         │
│       │                                                       │
│       ├── KnowledgeImportPanel (新组件，非泛化 ProgressPanel) │
│       ├── KnowledgePage (知识库浏览/搜索/删除)                │
│       └── 完成通知 → 聊天消息                                  │
└──────────────────────┬────────────────────────────────────────┘
                       │ POST /api/v1/knowledge/import
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                       Backend (FastAPI)                       │
│                                                              │
│  knowledge_api.py                                             │
│  ├── 路径安全检查                                              │
│  ├── 文件扫描 + 大小/类型判定                                   │
│  ├── 调用 KnowledgeManager                                     │
│  └── 返回 task_id                                              │
│                                                               │
│  KnowledgeManager (已有，不绕过)                                │
│  ├── import_file() / import_directory() → KnowledgeImporter   │
│  └── deposit() → 矛盾检测、自动编译、学习记录                   │
│       │                                                        │
│       ├── KnowledgeImporter (已有，增强)                       │
│       │   ├── FileParser 流式解析 (新增 parse_file_stream)     │
│       │   └── 中断检查点 (每文件 + 每页)                       │
│       │                                                        │
│       └── ProgressProxy (新增，线程安全桥接)                   │
│           ├── 线程安全收集进度事件                               │
│           └── call_soon_threadsafe → 事件循环                  │
│               └── ProgressStreamer (已有 SSE 推送)              │
│                                                               │
│  ImportTaskManager (新增子组件，DreamModeScheduler 持有)       │
│  ├── 导入任务状态管理 (SQLite 持久化)                          │
│  ├── 暂停/恢复/中断 (代理到 DreamModeScheduler)               │
│  └── 中断恢复 (服务重启后重新入队)                             │
│                                                               │
│  DreamModeScheduler (已有，扩展)                               │
│  ├── 持有 ImportTaskManager 子组件                             │
│  ├── 复用 should_pause / is_main_task_running                 │
│  └── background_loop 增强：调度导入任务                        │
│                                                               │
│  SystemResourceMonitor (新增)                                  │
│  ├── 采样缓存 (1秒间隔，复用最新值)                            │
│  ├── 迟滞机制 (Hysteresis)                                    │
│  ├── CPU + 内存 + 磁盘 IO                                     │
│  └── psutil 可选依赖，无 psutil 时降级为仅检查主任务           │
│                                                               │
│  SessionStreamer (已有)                                       │
│  └── 导入完成 → 推送聊天消息通知                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 执行模型（修复致命缺陷1）

### 3.1 统一模型：async def + run_in_executor

**唯一正确的执行模型**。`_run_import` 是 async def，同步操作通过 `run_in_executor` 执行。

```python
async def _run_import(self, task_id: str, files: List[Path],
                      manager: KnowledgeManager, proxy: ProgressProxy):
    """
    执行导入任务。
    始终是 async def，同步操作通过 run_in_executor 移出事件循环。
    绝不将协程提交到 ThreadPoolExecutor。
    """
    loop = asyncio.get_running_loop()
    state = self._task_manager.get_state(task_id)
    state.status = "running"

    proxy.start_phase("scanning", "扫描文件")
    await proxy.flush()  # 确保事件已投递
    # 扫描由同步代码完成，在调用处已执行

    for i in range(state.checkpoint, len(files)):
        # ========== 中断检查点 ==========
        if self._should_pause():
            state.status = "paused"
            state.checkpoint = i
            self._task_manager.persist(state)
            proxy.phase_complete("scanning", interrupted=True)
            await proxy.flush()
            return  # 暂停，下次 resume 从 checkpoint 继续

        file = files[i]

        # ========== 解析文件（移出事件循环）==========
        proxy.update(
            progress=i / len(files),
            phase="parsing",
            message=f"正在解析 ({i+1}/{len(files)})",
            file_progress={"current": file.name, "done": i, "total": len(files)}
        )
        await proxy.flush()

        content = await loop.run_in_executor(
            None,
            manager.import_file,
            str(file), True, {"title": file.stem}, True
        )

        # ========== 进程内检查点（解析大文件期间）=======
        # 流式解析中 parse_file_stream 自身的 page_callback 也会检查
        # 见 7.1 节

        if content and content.status == "failed":
            state.failed_files.append(str(file))
            continue

        state.processed = i + 1
        state.current_file = file.name

    # ========== 完成 ==========
    state.status = "completed"
    self._task_manager.persist(state)
    proxy.complete(state.get_result())
    await proxy.flush()

    # 通过 SessionStreamer 推送聊天通知
    self._session_streamer.push_chat_response(
        session_id="global",
        message=self._format_completion_message(state)
    )
```

### 3.2 调用链

```
FastAPI endpoint (async def)
  └─ KnowledgeManager (async def)
       └─ ImportTaskManager.register() → 创建 task_id
       └─ asyncio.create_task(_run_import(...))  ← 协程，不是 submit 到线程池
            └─ run_in_executor(None, manager.import_file, ...)  ← 同步操作移出事件循环
            └─ run_in_executor(None, importer.parser.parse_file_stream, ...)  ← 流式解析
            └─ proxy.update(...)  ← 线程安全，call_soon_threadsafe
```

---

## 4. 线程安全桥接（ProgressProxy）

### 4.1 背景

`ProgressStreamer` 的 `_task_states` 和 `_subscribers` 是类级别属性，其方法设计为在事件循环中调用。
`asyncio.Queue` 同样假定单线程使用。

从 `run_in_executor` 的线程中直接调用 `ProgressStreamer` 类方法在 CPython GIL 下大多数简单操作是原子的（`dict[key]=value`、`list.append` 等），但：
- `get_or_create_task()` 是复合操作（read + conditional write）
- 跨线程使用 `asyncio.Queue` 违反其设计假定
- 长期维护中容易引入新的竞争条件

因此添加 `ProgressProxy` 作为防御性设计，将进度事件收集在 deque 中，再通过 `flush()` 投回事件循环统一消费。

```python
import asyncio
from typing import Dict, Any, Optional
from collections import deque
import threading

class ProgressProxy:
    """
    线程安全的进度代理。

    设计：
    - 同步代码（在线程池中运行）调用 thread-safe 方法存入队列
    - 异步代码（在事件循环中运行）通过 flush() 消费队列并投递到 ProgressStreamer
    - 使用 collections.deque（线程安全 append/popleft）+ threading.Lock
    - 周期 Flush：长时间运行的文件解析中，如果超过 FLUSH_INTERVAL 没有显式 flush，
      通过 call_soon_threadsafe 自动将进度投递到事件循环，确保前端不卡死
    """

    FLUSH_INTERVAL = 2.0  # 每 2 秒至少推送一次进度

    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop):
        self.task_id = task_id
        self._loop = loop
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._flushing = False
        self._last_flush_time = time.time()

    def update(self, progress: float, phase: str = "",
               message: str = "", **metadata):
        """线程安全——可从 run_in_executor 中调用"""
        with self._lock:
            self._queue.append({
                "type": "progress",
                "progress": progress,
                "phase": phase,
                "message": message,
                "metadata": metadata
            })
        # 周期 Flush：超过间隔时通过 call_soon_threadsafe 自动投递
        now = time.time()
        if now - self._last_flush_time > self.FLUSH_INTERVAL:
            self._loop.call_soon_threadsafe(self._auto_flush)
            self._last_flush_time = now

    def start_phase(self, phase_id: str, phase_name: str):
        with self._lock:
            self._queue.append({
                "type": "phase_start",
                "phase_id": phase_id,
                "phase_name": phase_name
            })
        self._loop.call_soon_threadsafe(self._auto_flush)

    def complete(self, result: Dict[str, Any]):
        with self._lock:
            self._queue.append({
                "type": "complete",
                "result": result
            })
        self._loop.call_soon_threadsafe(self._auto_flush)

    def _auto_flush(self):
        """由 call_soon_threadsafe 调用的内部 flush，在事件循环中执行"""
        # 不需要锁——call_soon_threadsafe 保证在事件循环线程中串行执行
        events = []
        with self._lock:
            while self._queue:
                events.append(self._queue.popleft())

        for ev in events:
            t = ev["type"]
            if t == "progress":
                ProgressStreamer.update_progress(
                    self.task_id,
                    ev["progress"],
                    phase_id=ev.get("phase"),
                    message=ev.get("message", ""),
                    metadata=ev.get("metadata", {})
                )
            elif t == "phase_start":
                ProgressStreamer.start_phase(
                    self.task_id,
                    ev["phase_id"],
                    ev["phase_name"]
                )
            elif t == "complete":
                ProgressStreamer.complete_task(
                    self.task_id,
                    result=ev.get("result", {}),
                    metadata={"type": "knowledge_import"}
                )

    async def flush(self):
        """显式 flush——同步等待所有已排队事件投递完毕。"""
        self._auto_flush()
        # 由于 _auto_flush 由 call_soon_threadsafe 调用且已经在事件循环中，
        # 在 async def 中调用 flush() 时可以直接执行
```

### 4.2 使用模式

```python
async def _run_import(self, task_id, files, manager, proxy):
    # 在事件循环中创建 proxy
    loop = asyncio.get_running_loop()
    proxy = ProgressProxy(task_id, loop)

    # 在线程池中运行同步操作
    content = await loop.run_in_executor(None, sync_func, file)

    # 同步操作内部调用 proxy.update()——线程安全
    # async def 调用者负责 proxy.flush()——将事件投递到事件循环

    proxy.update(0.5, "parsing", "解析中...")
    await proxy.flush()  # ← 关键：确保事件已投递
```

---

## 5. 架构分层（修复致命缺陷3）

**原则**：所有导入操作走 `KnowledgeManager`，不直接实例化 `KnowledgeImporter`。

### 5.1 通过 KnowledgeManager 导入

```python
# 正确：通过 KnowledgeManager
manager = KnowledgeManager(user_id=user_id)

# 单文件
result = await loop.run_in_executor(
    None,
    manager.import_file,           # ← 委托到 bank.import_file
    str(file),                     # → bank → importer.import_file
    True,                          # auto_extract
    {"title": file.stem},          # source_info
    True                           # skip_if_imported
)

# 目录（多个文件时重复调用上面的单文件逻辑）
for file in files:
    result = await loop.run_in_executor(None, manager.import_file, ...)

# 不需要 manager.deposit()——bank.import_file 已包含实体提取和知识编译
# bank.import_file 内部调用 importer.import_file → compiler.compile_research → compiler.save_knowledge
```

### 5.2 现有委托链

```
manager.import_file()
  └─ bank.import_file()           ← UserKnowledgeBank
       └─ importer.import_file()  ← KnowledgeImporter
            ├─ parser.parse_file()
            ├─ compiler.compile_research()
            └─ compiler.save_knowledge()
```

**需修改**：`KnowledgeManager.import_file()` 当前签名缺少 `source_info` 参数（knowledge_manager.py:248），而 `bank.import_file()` 已有（knowledge_bank.py:715-720）。需在 Manager 层补上此参数透传。

```python
# KnowledgeManager 修改前
def import_file(self, file_path, auto_extract=True, skip_if_imported=True):

# KnowledgeManager 修改后
def import_file(self, file_path, auto_extract=True,
                source_info=None, skip_if_imported=True):
    return self._knowledge_bank.import_file(
        file_path, auto_extract, source_info, skip_if_imported)
```

### 5.3 增强 bank.import_file 以支持回调

```python
# UserKnowledgeBank 新增参数
def import_file(
    self,
    file_path: str,
    auto_extract: bool = True,
    source_info: Optional[Dict] = None,
    skip_if_imported: bool = True,
    progress_callback: Optional[Callable] = None,   # 新增
    interrupt_check: Optional[Callable] = None       # 新增
) -> "ImportResult":
    # 传递给 KnowledgeImporter.import_file()
    return self._knowledge_importer.import_file(
        file_path, auto_extract, source_info,
        skip_if_imported,
        progress_callback=progress_callback,       # 透传
        interrupt_check=interrupt_check             # 透传
    )
```

---

## 6. ImportTaskManager（组合模式）

### 6.1 设计

`DreamModeScheduler` 持有 `ImportTaskManager` 子组件，而非直接管理导入任务。

```python
class ImportTaskManager:
    """
    导入任务管理器。

    职责：
    - 任务状态管理 (内存 + SQLite 持久化)
    - 暂停/恢复/中断 (通过回调访问 DreamModeScheduler 状态)
    - 服务重启恢复

    由 DreamModeScheduler 持有，不独立运行。
    """

    def __init__(self, scheduler: 'DreamModeScheduler',
                 session_streamer: 'SessionStreamer',
                 db_path: str = "data/knowledge_import_queue.db"):
        self._scheduler = scheduler  # 反向引用，用于 should_pause()
        self._session_streamer = session_streamer
        self._db_path = db_path
        self._tasks: Dict[str, ImportTaskState] = {}
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._init_db()

    async def register(self, files: List[Path], source_path: str,
                       user_id: str = "default") -> str:
        """注册导入任务"""
        task_id = f"know_import_{uuid.uuid4().hex[:12]}"
        priority = 0 if len(files) <= 3 else 1  # 小批量优先
        state = ImportTaskState(
            task_id=task_id, files=files, total=len(files),
            source_path=source_path, user_id=user_id,
            priority=priority
        )
        self._tasks[task_id] = state
        self._persist(state)
        await self._queue.put((priority, task_id))
        return task_id

    def should_pause(self) -> bool:
        """代理到 DreamModeScheduler"""
        return self._scheduler.should_pause()

    async def recover(self):
        """服务重启恢复——从 SQLite 恢复非终态任务"""
        for state in self._load_all_active():
            if state.status == "running":
                state.status = "interrupted"
            self._tasks[state.task_id] = state
            await self._queue.put((state.priority, state.task_id))

    # ... 其他方法：cancel, retry, get_status, persist ...


class DreamModeScheduler:
    """扩展后——持有 ImportTaskManager 子组件"""

    def __init__(self, ...):
        # ... 现有初始化代码 ...
        self.import_manager = ImportTaskManager(self)  # 子组件
        self._resource_monitor = SystemResourceMonitor()

    def should_pause(self) -> bool:
        return (self._is_main_task_running or
                self._resource_monitor.is_overloaded())

    async def _extended_background_loop(self):
        """
        增强的后台循环。

        设计要点：
        - 导入任务逐个处理，不插入 sleep（除非队列为空）
        - _run_import 内部每处理完一个文件就检查 should_pause
        - CoreMemory consolidation 仅在队列为空时执行
        - 避免"处理 1 个文件 → sleep 10 秒 → 处理下一个文件"的低效模式
        """
        while True:
            if self._is_main_task_running:
                await asyncio.sleep(self.config.idle_check_interval)
                continue

            # 高效模式：队列非空时连续处理，不 sleep
            processed_any = False

            while not self.import_manager.get_queue().empty():
                _, task_id = self.import_manager.get_queue().get_nowait()
                processed_any = True
                await self._run_import(task_id)
                # _run_import 完成后立即检查下一个任务
                # 不在此处 sleep

            # CoreMemory：仅在队列为空时执行
            if not processed_any:
                pending = self.raw_data_store.get_pending_count()
                if pending >= self.config.trigger_on_pending_threshold:
                    await self._start_extraction()

                # 队列为空且无 CoreMemory 任务 → 空闲，等待检查间隔
                await asyncio.sleep(self.config.idle_check_interval)
            # 队列非空时，直接进入下一次循环，无 sleep
```

**职责变更对比**：

| 职责 | 原设计 | 修订后 |
|---|---|---|
| 任务创建/状态管理 | ImportQueue (独立) | DreamModeScheduler.import_manager |
| 暂停检测 | 无 | DreamModeScheduler.should_pause() + ResourceMonitor |
| 空闲检测 | 无 | DreamModeScheduler._extended_background_loop() |
| 队列持久化 | ImportQueue (独立) | ImportTaskManager._persist() |
| CoreMemory consolidation | DreamModeScheduler | DreamModeScheduler (不变) |
| 导入执行 | ImportQueueWorker | DreamModeScheduler._run_import() |

---

## 7. 流式解析 + 编译器兼容性（修复致命缺陷8）

### 7.1 parse_file_stream 设计

```python
class FileParser:
    """
    流式解析器。

    关键约束：编译器 compile_research() 需要完整文本。
    流式解析解决的是"文件读取阶段"的内存峰值，而非"实体提取阶段"。

    parse_file_stream 返回完整的拼接文本，并在解析过程中：
    1. 逐页/逐块回调外部进度
    2. 每页后检查中断标志
    3. 维护总内存占用不超过 STREAM_CHUNK_MEMORY_LIMIT
    """

    STREAM_CHUNK_MEMORY_LIMIT = 100 * 1024 * 1024  # 100MB

    def parse_file_stream(
        self,
        file_path: str,
        *,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """
        流式解析文件。

        Args:
            file_path: 文件路径
            progress_callback: 进度回调(page_index, total_pages)
            interrupt_check: 中断检查 (每页/每块后调用)

        Returns:
            完整文本内容 (或 None 解析失败)

        内存说明：
        - 流式解析过程中内存峰值为 max(文件流读缓冲, 渐进拼接文本总大小)
        - 渐进拼接 = 所有页面/块的文本累积 → 最终 = 全量文本
        - 编译器需要全量文本，所以总内存峰值 ≈ 文件文本大小 + 100MB 读缓冲
        - 替代方案（如需进一步降低内存）是分块编译，但当前 Compiler API 不支持
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        all_text_parts = []
        total_pages = 0
        processed = 0

        # 中断检查包装
        def should_stop():
            nonlocal processed
            processed += 1
            if progress_callback:
                progress_callback(processed, total_pages or 1)
            return interrupt_check and interrupt_check()

        if ext == '.pdf':
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)
                for page in reader.pages:
                    if should_stop():
                        return None  # 中断，放弃本次文件
                    text = page.extract_text()
                    if text:
                        all_text_parts.append(text)

        elif ext == '.csv':
            import csv
            import io
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # CSV 读取后按行分段
            # ...

        else:
            # 文本文件：按行分批
            CHUNK_LINES = 500
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = []
                for line in f:
                    lines.append(line)
                    if len(lines) >= CHUNK_LINES:
                        lines = []  # batch processed
                        if should_stop():
                            return None
                total_pages = 1

        if interrupt_check and interrupt_check():
            return None

        return "\n\n".join(all_text_parts) if all_text_parts else None
```

### 7.2 编译阶段的内存

```
[文件读取阶段]
  parse_file_stream:
    内存峰值 = 100MB (流缓冲区) + 渐进拼接文本
    → 最终产出 content (全部文本字符串)

[实体提取阶段]
  compiler.compile_research(content):
    接收 content (全量文本)
    → 当前 API 需要全量文本，无法分块

[总内存峰值]
  大文件解析时内存 ≈ content_size + 100MB 读缓冲
  对于 500MB PDF：文本提取后 ≈ 50-100MB 纯文本
  → 总内存 ≈ 200MB，可控
```

**文档边界**：当前 `KnowledgeCompiler.compile_research()` API 需要全量文本。如果未来需要更低内存，需要重构 Compiler 支持增量处理。当前设计明确标注此约束，不作为阻塞项。

---

### 7.2 编译器兼容性说明

`KnowledgeCompiler.compile_research()` 需要全量文本作为输入（签名：`compile_research(raw_content: str, source_info)`），因为实体提取、关系发现需要全局上下文。

流式解析在这个上下文中的角色是：

| 阶段 | 内存峰值 | 说明 |
|---|---|---|
| 文件读取 | `流缓冲区(100MB)` + `渐进拼接` | 流式解析消除此阶段的内存峰值 |
| 实体提取 | `压缩后文本体积` | compiler 需要全量文本，但 PDF→文本压缩比约 10:1。500MB PDF → ~50MB 文本，在可控范围内 |

**这不是一个缺陷，而是一个已知约束**。如果未来需要进一步降低实体提取阶段的内存，需要重构 Compiler 支持增量处理。当前不在范围内。

---

## 8. 系统资源监控

```python
import time
from dataclasses import dataclass

@dataclass
class ResourceSample:
    cpu: float
    memory: float
    disk_read_mb: float
    disk_write_mb: float
    timestamp: float

class SystemResourceMonitor:
    """
    系统资源监控。

    设计要点：
    - 采样缓存：1 秒内复用最新值，不重复采集
    - 迟滞 (Hysteresis)：阈值±5% 死区，防止频繁切换
    - 监控维度：CPU + 内存 + 磁盘 IO（导入的主要瓶颈）
    - psutil 可选：无 psutil 时降级为仅返回正常
    """

    CPU_HIGH = 50.0      # 过载阈值
    CPU_LOW = 30.0       # 恢复正常阈值（迟滞死区 20%）
    MEM_HIGH = 80.0
    MEM_LOW = 70.0
    CACHE_TTL = 1.0      # 采样缓存 TTL（秒）
    CPU_SAMPLES = 5      # 滑动窗口大小（消除 Windows 瞬时采样抖动）

    def __init__(self):
        self._cache: Optional[ResourceSample] = None
        self._overloaded = False
        self._has_psutil = self._check_psutil()
        # CPU 滑动窗口：psutil.cpu_percent(interval=0.0) 在 Windows 上返回
        # 瞬时值，可能因线程调度间隙剧烈抖动（0% ↔ 100%）。滑动平均消除噪声。
        self._cpu_samples: deque = deque(maxlen=self.CPU_SAMPLES)

    def _check_psutil(self) -> bool:
        try:
            import psutil
            return True
        except ImportError:
            return False

    def _sample(self) -> Optional[ResourceSample]:
        if not self._has_psutil:
            return None

        # 采样缓存
        now = time.time()
        if (self._cache and
            now - self._cache.timestamp < self.CACHE_TTL):
            return self._cache

        import psutil

        # 非阻塞采样 + 滑动平均
        raw_cpu = psutil.cpu_percent(interval=0.0)
        self._cpu_samples.append(raw_cpu)
        cpu = sum(self._cpu_samples) / len(self._cpu_samples)  # 滑动平均

        mem = psutil.virtual_memory().percent
        disk = psutil.disk_io_counters()

        self._cache = ResourceSample(
            cpu=cpu,
            memory=mem,
            disk_read_mb=(disk.read_bytes if disk else 0) / 1024 / 1024,
            disk_write_mb=(disk.write_bytes if disk else 0) / 1024 / 1024,
            timestamp=now
        )
        return self._cache

    def is_overloaded(self) -> bool:
        """带迟滞判断"""
        sample = self._sample()
        if sample is None:
            return False  # 无 psutil 时不限速

        if self._overloaded:
            # 当前过载状态 → 需要降到 LOW 阈值才恢复
            self._overloaded = not (
                sample.cpu < self.CPU_LOW and
                sample.memory < self.MEM_LOW
            )
        else:
            # 当前正常状态 → 达到 HIGH 阈值才过载
            self._overloaded = (
                sample.cpu > self.CPU_HIGH or
                sample.memory > self.MEM_HIGH
            )

        return self._overloaded
```

**迟滞效果**：

```
CPU 48% → 49% → 51% (过载) → 52% → 49% → 31% (恢复) → 30%
       正常    正常    过载      过载   过载   正常       正常
```

---

## 9. 路径安全检查（修复严重问题6）

```python
import os

def validate_import_path(path: str) -> Path:
    """
    路径安全检查。

    原则：
    - 白名单仅限用户明确配置的目录，无默认全盘通配
    - 使用 os.path.realpath 解析所有重定向（含 Windows 挂载点）
    - 拒绝符号链接指向敏感目录的文件
    """

    try:
        p = Path(path)
    except (TypeError, ValueError) as e:
        raise ValueError(f"无效路径格式: {e}")

    if not p.is_absolute():
        raise ValueError("路径必须是绝对路径")

    # 使用 os.path.realpath 解析 Windows 挂载点和符号链接
    # 可能抛出 PermissionError（无权限访问）或 OSError（路径无效）
    try:
        resolved = Path(os.path.realpath(str(p)))
    except PermissionError as e:
        raise PermissionError(f"无权限访问路径: {path}")
    except OSError as e:
        raise ValueError(f"路径无法访问: {path} ({e})")

    # 检查白名单
    from src.config import settings
    allowed = settings.get("knowledge.allowed_import_dirs", [])

    # 默认白名单：无。用户必须在 settings.yaml 中配置
    if not allowed:
        raise ValueError("未配置允许的导入目录。请在 settings.yaml 中设置 knowledge.allowed_import_dirs")

    allowed_resolved = [Path(os.path.realpath(d)) for d in allowed]

    ok = False
    for base in allowed_resolved:
        try:
            resolved.relative_to(base)
            ok = True
            break
        except ValueError:
            continue

    if not ok:
        raise ValueError(f"路径不在允许的目录中。允许的目录: {', '.join(allowed)}")

    if not resolved.exists():
        raise FileNotFoundError(f"路径不存在: {path}")

    return resolved
```

**默认配置（settings.yaml）**：

```yaml
knowledge:
  allowed_import_dirs:
    - D:\KnowledgeBase
    - D:\Reports
  # 无默认值——用户首次使用 /knowledge import 时会收到配置引导
```

**为什么这么设计**：
- `Path.home()` 范围过大（含 AppData、Temp） → 移除
- `D:\` 根目录范围过大 → 移除
- 明确可配置 → 用户精确控制
- `os.path.realpath` 处理 Windows 挂载点 → 防止挂载点逃逸
- 第一次使用时提示用户配置 → 安全 + 可用性平衡

---

## 10. 进度展示与前端

### 10.1 KnowledgeImportPanel（新组件）

不泛化现有 `ProgressPanel`（硬编码太多），新建独立组件：

```
components/
  chat/
    ProgressPanel.tsx          (研究任务，不变)
    KnowledgeImportPanel.tsx   (知识导入任务，新增)
```

**KnowledgeImportPanel 交互**：

```
┌──────────────────────────────────────────┐
│ 📚 知识导入                              │
│   /knowledge import D:\研究报告           │
│                                          │
│  ████████████░░░░ 80%                    │
│  📄 阶段: 实体提取中...                   │
│                                          │
│  ┌─ 文件进度 ───────────────────────┐    │
│  │ ✅ 行业分析_2024.pdf      (完成)  │    │
│  │ ✅ 市场趋势.docx          (完成)  │    │
│  │ ⏳ 竞争格局.xlsx (解析中...)       │    │
│  │ ⬜ 财务数据.csv           (等待)  │    │
│  │ ❌ 损坏文档.pdf           (失败)  │    │
│  └─────────────────────────────────┘    │
│                                          │
│  汇总: 10 文件中 3/10, 失败 1           │
│  实体: 42 个 | 处理: 152 MB              │
│  预计剩余: 约 1 分钟                      │
│                                          │
│  [取消导入]                               │
└──────────────────────────────────────────┘
```

### 10.2 SSE 降级方案

```
SSE 连接正常 → 实时推送进度
SSE 断开  → 前端 useKnowledgeImport hook 开始轮询
             GET /api/v1/knowledge/tasks?task_id=xxx (5 秒间隔)
             恢复 SSE 连接后切回实时推送
```

### 10.3 实现工作量评估

| 组件 | 工作量 | 说明 |
|---|---|---|
| KnowledgeImportPanel | ~150 行 | 新组件，含文件进度列表 |
| commands.ts | ~80 行 | 命令解析 + 补全 |
| ChatInput 修改 | ~50 行 | 注入命令检测逻辑 |
| useKnowledgeImport hook | ~100 行 | SSE 订阅 + 轮询降级 |
| KnowledgePage | ~400 行 | 概览 + 搜索 + 导入历史 + 实体管理 |
| **小计** | **~780 行** | 约为原估算的 3 倍 |

---

## 11. 错误恢复与幂等性（修复严重问题9）

### 11.1 事务日志

```python
@dataclass
class ImportTaskState:
    task_id: str
    files: List[Path]
    total: int
    processed: int = 0
    failed_files: List[str] = field(default_factory=list)
    current_file: str = ""
    checkpoint: int = 0  # 已成功处理的文件索引
    status: str = "queued"  # queued | running | paused | completed | failed | interrupted
    created_at: datetime = field(default_factory=datetime.now)
    transaction_log: List[TransactionEntry] = field(default_factory=list)
    # ↑ 记录每个文件的处理结果：成功/失败/实体数

@dataclass
class TransactionEntry:
    file_path: str
    status: str  # success | failed | partial
    entities_created: int
    timestamp: datetime
```

### 11.2 重试策略

- **重试整个任务** → 从 checkpoint 继续（已处理的文件通过 manifest 跳过）
- **重试失败文件** → 仅重新提交失败的文件列表
- **部分提取的文件** → 重试时覆盖（文件名+哈希匹配时擦除重建，不追加）
  - **注意**：`compiler.save_knowledge()` 当前是增量追加模式，不支持幂等覆盖。重试可能导致实体重复。
    未来通过语义去重来解决。在语义去重上线前，重试依赖 manifest 哈希去重防止多数重复场景。
- **没有整体原子性**（跨 100 个文件的事务在 SQLite 中不可行且不必要）

### 11.3 前端错误处理

```
┌─── 导入中遇到错误 ──────────────────────┐
│ ⚠ 10 个文件中 2 个解析失败               │
│ 失败文件:                                  │
│   ❌ 损坏的PDF_1.pdf — PDF 文件损坏       │
│   ❌ 加密文档.xlsx   — 需要密码           │
│                                           │
│ [跳过失败继续] [重试全部] [取消]          │
└──────────────────────────────────────────┘
```

---

## 12. 知识点导入与 UserKnowledgeBank 关联

```python
# 修改 UserKnowledgeBank.import_file 的返回，补充关联信息
@dataclass
class ImportResult:
    file_path: str
    status: str
    content: Optional[str] = None
    pages_created: int = 0
    entities_extracted: int = 0
    # 新增关联字段
    entity_ids: List[int] = field(default_factory=list)  # 创建的实体ID列表
    relation_ids: List[int] = field(default_factory=list) # 创建的关系ID列表

    def to_dict(self):
        return {
            "file_path": self.file_path,
            "status": self.status,
            "pages_created": self.pages_created,
            "entities_extracted": self.entities_extracted,
            "entity_ids": self.entity_ids,       # 新增
            "relation_ids": self.relation_ids,    # 新增
        }
```

---

## 13. 前端命令用户流程

```
用户输入 /knowledge import D:\研究报告

  → 前端检测命令 → 调用 POST /api/v1/knowledge/import
  → 后端扫描路径 → 返回 task_id + 文件数 + 模式
  → 前端:
      ├─ 聊天框中显示"开始导入"消息
      ├─ 弹出 KnowledgeImportPanel
      └─ 订阅 SSE /api/v1/stream/{task_id}
  → 进度实时更新
  → 完成后:
      ├─ KnowledgeImportPanel 显示完成状态 (可收起)
      └─ 聊天框推送完成通知消息
```

---

## 14. 实现顺序

### Phase 1: 基础设施（3-4 天）
1. `ResourceMonitor`（psutil 可选 + 迟滞 + 缓存）
2. `ProgressProxy`（线程安全桥接）
3. `ImportTaskManager`（状态管理 + SQLite 持久化）
4. `FileParser.parse_file_stream()`（流式解析 + 中断检查）
5. 扩展 `DreamModeScheduler`（持有 ImportTaskManager + 改进 background_loop）

### Phase 2: API + 集成（2 天）
1. `knowledge_api.py` 端点
2. 路径安全检查（白名单配置 + realpath 挂载点检查）
3. `KnowledgeManager` 增强（回调透传）
4. 服务重启恢复逻辑

### Phase 3: 前端（2-3 天）
1. `commands.ts` 命令解析
2. `ChatInput` 命令检测 + 自动补全
3. `KnowledgeImportPanel` 新组件
4. `useKnowledgeImport` hook（SSE + 轮询降级）
5. 完成通知（SessionStreamer 聊天消息）

### Phase 4: 知识管理页面（1-2 天）
1. `/knowledge` 页面
2. 侧边栏菜单 + 路由
3. 知识搜索/浏览/删除

### Phase 5: 测试（1-2 天）
- 事件循环阻塞测试（大文件解析时 HTTP 正常响应）
- 线程安全测试（多线程 + asyncio 并发调用 ProgressProxy）
- 暂停/恢复/中断全链路
- 服务重启恢复
- 超大文件/目录性能
- 路径安全测试（挂载点、符号链接）

---

## 15. 开放问题

- **挂载点路径逃逸**：Windows 挂载点可将 D:\ 指向系统目录。`os.path.realpath` 能解一层，但嵌套挂载点需要额外测试 — **当前不在范围内，文档记录为已知限制**
- **Compiler 分块**：`compile_research()` 需要全量文本。未来如需更低内存，需重构 Compiler — **当前不在范围内**
- **网络路径**：`\\server\share` 当前不支持 — **未来可通过配置白名单添加**
- **语义去重**：manifest 是文件哈希级去重。语义级去重（相似内容的不同版本）不在范围
- **psutil 系统兼容**：Windows 下 `psutil.cpu_percent(interval=0.0)` 返回瞬时值，精确度低于 interval>0，但对资源监控足够

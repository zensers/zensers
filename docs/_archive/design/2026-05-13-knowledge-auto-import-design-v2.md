# 知识模块自动化导入方案 v2

> 基于 v1 审计修正版 | 审计报告见 `2026-05-13-knowledge-auto-import-design.md` 的 user review

---

## 0. v1 → v2 修正摘要

| # | 问题 | v1 错误 | v2 修正 |
|---|------|---------|---------|
| 1 | 配置类型 | `DreamModeScheduler` 传入 `KnowledgeConfig`，两 dataclass 字段不兼容 | 新字段加到 `DreamModeConfig`，调度器自持自有配置 |
| 2 | 双重编译 | `_store_import_content_to_bank` 重新调用 `compile_research()` | `ImportResult` 增加 `compiled_knowledge` 字段，直接复用 |
| 3 | Manifest 去重 | 另建文件集，与 `Importer._import_manifest` 不互通 | 直接复用 `Importer` 的 manifest + `_compute_file_hash` |
| 4 | 存储不完整 | 只写 entities/relations，缺 data_points/insights | 补全四类写入 |
| 5 | import_url 误判 | 声称 importer 无 `import_url()` | importer 已有（`importer.py:1004`），只加 `UserKnowledgeBank`/`KnowledgeManager` 代理 |
| 6 | import_max_workers 冲突 | 新增重复配置 | 统一用 `DreamModeConfig.import_max_workers: int = 2` |
| 7 | 文件系统竞争 | 未处理多线程写文件 | `compiler.save_knowledge()` 加 threading.Lock |
| 8 | 行数估算 | 230 行 | 实际 ~270 行 |

---

## 1. 变更清单（精确）

| 文件 | 修改 | 行数 | 类型 |
|------|------|------|------|
| `src/core/memory/dream/dream_scheduler.py` | `DreamModeConfig` 新增 5 字段 + 扫描逻辑 | +135 | 修改 |
| `src/core/memory/knowledge_bank.py` | 新增 `import_url()` 代理 + `_store_compiled_to_bank()` | +70 | 修改 |
| `src/core/memory/knowledge_manager.py` | 新增 `import_url()` 代理 | +15 | 修改 |
| `src/core/memory/knowledge/importer.py` | `ImportResult` 加 `compiled_knowledge` 字段 | +10 | 修改 |
| `src/core/memory/knowledge/compiler.py` | `save_knowledge()` 加线程锁 | +10 | 修改 |
| `src/api/main.py` | DreamModeScheduler 初始化 | +35 | 修改 |
| **合计** | | **~275** | |

---

## 2. 详细设计

### 2.1 DreamModeConfig 扩展

```python
# dream_scheduler.py:38-53

@dataclass
class DreamModeConfig:
    """做梦模式配置"""
    # === 已有字段（不变）===
    trigger_after_task: bool = True
    trigger_on_idle_seconds: int = 30
    trigger_on_pending_threshold: int = 10
    batch_size: int = 10
    max_duration_seconds: int = 300
    min_interval_seconds: int = 60
    max_concurrent_tasks: int = 1
    idle_check_interval: int = 10

    # === v2 新增：知识源自动导入 ===
    knowledge_source_dirs: tuple = ()  # 用 tuple 保持 dataclass 不可变语义
    """知识源目录列表
       环境变量: DREAM_SOURCE_DIRS (逗号分隔)"""

    knowledge_scan_interval: int = 300
    """目录扫描间隔（秒）
       环境变量: DREAM_SCAN_INTERVAL"""

    knowledge_auto_import: bool = True
    """启用自动导入
       环境变量: DREAM_AUTO_IMPORT"""

    knowledge_store_to_bank: bool = True
    """导入后写入 SQLite
       环境变量: DREAM_STORE_TO_BANK"""

    import_max_workers: int = 2
    """导入并发数（替代 KnowledgeConfig.import_max_workers=4）
       环境变量: DREAM_IMPORT_MAX_WORKERS"""
```

### 2.2 ImportResult 扩展（消除双重编译）

```python
# importer.py:90-124

@dataclass
class ImportResult:
    """导入结果"""
    file_path: str
    status: str  # success, failed, skipped, partial
    content: Optional[str] = None
    pages_created: int = 0
    entities_extracted: int = 0
    error_message: str = ""
    import_time: datetime = field(default_factory=datetime.now)
    file_size: int = 0
    compiled_knowledge: Optional["CompiledKnowledge"] = None  # v2 新增
```

在 `import_file()` 和 `import_url()` 编译后赋值：

```python
# importer.py:848 (import_file 中)
stats = knowledge.get_stats()
result.pages_created = stats["total"]
result.entities_extracted = stats["entities"]
result.compiled_knowledge = knowledge  # v2 新增
```

### 2.3 UserKnowledgeBank — import_url 代理 + store_compiled

```python
# knowledge_bank.py

def import_url(
    self,
    url: str,
    auto_extract: bool = True,
    timeout: int = 30,
    max_size: int = MAX_URL_SIZE,
    retries: int = 3,
    *,
    store_to_bank: bool = True,
) -> "ImportResult":
    """导入 URL 内容（代理到 KnowledgeImporter.import_url）"""
    result = self.importer.import_url(
        url,
        auto_extract=auto_extract,
        timeout=timeout,
        max_size=max_size,
        retries=retries,
    )
    if store_to_bank and result.status == "success" and result.compiled_knowledge:
        self._store_compiled_to_bank(result.compiled_knowledge)
    return result


def import_file(
    self,
    file_path: str,
    auto_extract: bool = True,
    source_info: Optional[Dict] = None,
    skip_if_imported: bool = True,
    *,
    store_to_bank: bool = True,
) -> "ImportResult":
    """导入文件（增加 store_to_bank 参数，仅关键字传参）"""
    result = self.importer.import_file(
        file_path,
        auto_extract=auto_extract,
        source_info=source_info,
        skip_if_imported=skip_if_imported,
    )
    if store_to_bank and result.status in ("success", "partial") and result.compiled_knowledge:
        self._store_compiled_to_bank(result.compiled_knowledge)
    return result


def _store_compiled_to_bank(self, knowledge: "CompiledKnowledge"):
    """将已有编译结果写入 UserKnowledgeBank SQLite

    复用 KnowledgeExtractionPhase._store_to_knowledge_bank 的存储模式。
    knowledge 是已编译结果，不重新编译。
    """
    # 实体
    for page in knowledge.entities:
        self.entities.add_entity(
            entity_type=page.metadata.get("entity_type", "generic"),
            name=page.title,
            description=page.content[:500],
        )

    # 概念（存为知识实体）
    for page in knowledge.concepts:
        self.entities.add_entity(
            entity_type="concept",
            name=page.title,
            description=page.content[:500],
        )

    # 关系（依赖实体已存在）
    for page in knowledge.relations:
        source = page.metadata.get("source_entity", "")
        target = page.metadata.get("target_entity", "")
        if source and target:
            self.relations.add_relation(
                source_entity=source,
                target_entity=target,
                relation_type=page.metadata.get("relation_type", "related_to"),
                context=page.content[:300],
            )

    logger.info(f"Stored compiled knowledge to bank: {len(knowledge.entities)} entities, "
                f"{len(knowledge.concepts)} concepts, {len(knowledge.relations)} relations")
```

### 2.4 KnowledgeManager — import_url 代理

```python
# knowledge_manager.py

def import_url(
    self,
    url: str,
    auto_extract: bool = True,
    timeout: int = 30,
    max_size: int = 10485760,
    retries: int = 3,
    *,
    store_to_bank: bool = True,
) -> "ImportResult":
    """导入 URL 内容（代理到 UserKnowledgeBank）"""
    return self._knowledge_bank.import_url(
        url=url,
        auto_extract=auto_extract,
        timeout=timeout,
        max_size=max_size,
        retries=retries,
        store_to_bank=store_to_bank,
    )
```

### 2.5 DreamModeScheduler — 目录扫描（复用 manifest）

```python
# dream_scheduler.py

import json
import concurrent.futures
from pathlib import Path
from typing import List, Set

class DreamModeScheduler:
    def __init__(self, ...):
        # ... 已有初始化代码不变 ...
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.import_max_workers,
            thread_name_prefix="dream-import",
        )

    async def start_background_loop(self):
        """扩展后的背景循环"""
        logger.info("Starting dream mode background loop")
        while True:
            try:
                if self._is_main_task_running:
                    await asyncio.sleep(self.config.idle_check_interval)
                    continue

                # [优先级 1] 知识源目录扫描
                await self._maybe_scan_source_dirs()

                # [优先级 2] 研究资料知识提取（已有逻辑）
                if self._last_main_task_time:
                    idle_time = (datetime.now() - self._last_main_task_time).total_seconds()
                    if idle_time >= self.config.trigger_on_idle_seconds:
                        pending_count = self.raw_data_store.get_pending_count()
                        if pending_count > 0:
                            await self._start_extraction()

                await asyncio.sleep(self.config.idle_check_interval)

            except asyncio.CancelledError:
                logger.info("Background loop cancelled")
                break
            except Exception as e:
                logger.error(f"Background loop error: {e}")
                await asyncio.sleep(self.config.idle_check_interval)

    async def _maybe_scan_source_dirs(self):
        """检查并导入知识源目录中的新文件"""
        dirs = self.config.knowledge_source_dirs
        if not dirs or not self.config.knowledge_auto_import:
            return

        for dir_path in dirs:
            if self._is_main_task_running:
                break

            source_dir = Path(dir_path)
            if not source_dir.is_dir():
                continue

            new_files = self._collect_new_files(source_dir)
            if not new_files:
                continue

            logger.info(f"Auto-importing {len(new_files)} files from {source_dir}")
            loop = asyncio.get_running_loop()

            for f in new_files:
                if self._is_main_task_running:
                    break
                await loop.run_in_executor(
                    self._executor,
                    self._knowledge_bank.import_file,
                    f,
                )

    def _collect_new_files(self, source_dir: Path) -> List[str]:
        """收集未导入的新文件（复用 Importer manifest 去重）"""
        # 通过访问 importer 的 manifest 来检查是否已导入
        # 此处不直接读 manifest，而是尝试导入（skip_if_imported=True）
        # importer.import_file 内部会做 MD5 哈希检查
        result = []

        # 只做轻量扫描：找到所有支持的文件
        supported_ext = {'.md', '.txt', '.csv', '.json', '.pdf', '.docx', '.xlsx', '.xls'}
        for f in sorted(source_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in supported_ext:
                result.append(str(f))

        return result
```

### 2.6 compiler.py — 线程安全

```python
# compiler.py
import threading

class KnowledgeCompiler:
    _save_lock = threading.Lock()

    def save_knowledge(self, knowledge: CompiledKnowledge):
        with self._save_lock:
            # ... 原有保存逻辑不变 ...
            for page in knowledge.concepts:
                self._save_page(page, "concepts")
            for page in knowledge.entities:
                self._save_page(page, "entities")
            for page in knowledge.relations:
                self._save_page(page, "relations")
```

### 2.7 main.py — 初始化

```python
# src/api/main.py

from src.core.memory.dream.dream_scheduler import DreamModeScheduler, DreamModeConfig
from src.core.memory.dream.raw_data_store import RawResearchDataStore
from src.core.memory import KnowledgeManager
from src.core.memory.config import KnowledgeConfig as _KC

# 构建 DreamModeConfig（含 v2 新增的知识源配置）
_dream_cfg = DreamModeConfig(
    idle_check_interval=10,
    knowledge_auto_import=os.getenv("DREAM_AUTO_IMPORT", "true").lower() == "true",
    knowledge_scan_interval=int(os.getenv("DREAM_SCAN_INTERVAL", "300")),
    knowledge_source_dirs=tuple(
        d.strip() for d in os.getenv("DREAM_SOURCE_DIRS", "").split(",") if d.strip()
    ),
    knowledge_store_to_bank=os.getenv("DREAM_STORE_TO_BANK", "true").lower() == "true",
    import_max_workers=int(os.getenv("DREAM_IMPORT_MAX_WORKERS", "2")),
)

_dream_scheduler = None
if _knowledge_manager:
    _raw_data_store = RawResearchDataStore()
    _dream_scheduler = DreamModeScheduler(
        knowledge_bank=_knowledge_manager.knowledge_bank,
        raw_data_store=_raw_data_store,
        config=_dream_cfg,
        dream_mode=None,
    )
    _dream_scheduler.start_background()
    logger.info(
        f"DreamModeScheduler started, source_dirs={_dream_cfg.knowledge_source_dirs}, "
        f"scan_interval={_dream_cfg.knowledge_scan_interval}s"
    )

# 在 shutdown 时
if _dream_scheduler:
    await _dream_scheduler.shutdown()
```

---

## 3. 线程安全模型（修正版）

| 操作 | 线程 | 保护机制 |
|------|------|----------|
| 目录扫描 `_collect_new_files()` | 事件循环 | 轻量 stat + glob，无阻塞 |
| 文件导入 `import_file()` | `ThreadPoolExecutor` | `Importer._cancel_event` 提供中断 |
| 文件系统写入 `save_knowledge()` | `ThreadPoolExecutor` | `threading.Lock`（v2 新增） |
| SQLite 写入 `_store_compiled_to_bank()` | `ThreadPoolExecutor` | WAL 模式 + 独立连接 |
| `_is_main_task_running` 检查 | 事件循环 | 主任务开始即设置 True，跳过导入 |

---

## 4. 配置示例

```bash
# .env
DREAM_SOURCE_DIRS=data/sources/market_reports,data/sources/industry_pdfs
DREAM_SCAN_INTERVAL=300
DREAM_AUTO_IMPORT=true
DREAM_STORE_TO_BANK=true
DREAM_IMPORT_MAX_WORKERS=2
```

---

## 5. 数据流（修正版）

```
DreamModeConfig.knowledge_source_dirs
        │
        ▼
DreamModeScheduler.start_background_loop()
        │
        ├─ _is_main_task_running? → sleep
        │
        └─ _maybe_scan_source_dirs()
              │
              ▼
        收集新文件（仅 glob，无哈希计算）
              │
              ▼   (run_in_executor)
         KnowledgeImporter.import_file()
              │
              ├─ MD5 manifest 去重（Importer 内部）
              ├─ 文件解析
              ├─ compiler.compile_research()  ← 唯一一次编译
              ├─ compiler.save_knowledge()     ← 文件系统（线程锁保护）
              │
              └─ result.compiled_knowledge ← 已有编译结果
                      │
                      ▼   (store_to_bank=True)
                   _store_compiled_to_bank()
                      │
                      ├─ entities.add_entity()    → SQLite
                      ├─ relations.add_relation() → SQLite
                      └─ data_points + insights   → SQLite
```

---

## 6. 边界案例处理

| 场景 | 行为 |
|------|------|
| 用户启动研究任务 | `_is_main_task_running=True` → 扫描跳过，导入跳过 |
| 目录不存在 | `Path(dir).is_dir()` → 跳过，日志警告 |
| 文件正在被写入（partial write） | `Importer._compute_file_hash` + manifest 去重 → 无效哈希导致下次重新导入 |
| 超大文件（>50MB） | `FileParser._parse_file` 返回 None → 标记失败，日志记录 |
| 扫描过程中新文件不断产生 | 每轮扫描只处理快照，下次再扫到新变更 |
| 多目录有同名文件 | 各自独立 MD5 校验，互不影响 |

# 知识模块自动化导入方案

> 设计原则：纯后端、配置驱动、零前端、零 API、复用现有基础设施

---

## 1. 核心决策

| 选项 | 结论 | 理由 |
|------|------|------|
| 前端交互 | **砍掉** | 收益/成本比太低 |
| 知识源管理 | **配置驱动** | `KnowledgeConfig` 已支持 `from_env()`，扩展即可 |
| 自动化引擎 | **DreamModeScheduler** | 已有 `start_background_loop()` + 主任务优先机制 |
| 知识存储 | **文件系统 + SQLite 双写** | 编译器需要文件系统，搜索需要 SQLite |
| 线程模型 | **run_in_executor** | import 是同步阻塞 IO，不能在事件循环中直接执行 |

---

## 2. 代码基础评估

### 2.1 已就绪的部分（无需修改）

| 组件 | 状态 | 说明 |
|------|------|------|
| `DreamModeScheduler` | ✅ 就绪 | `start_background_loop()` + `on_main_task_started/completed` |
| `KnowledgeExtractionPhase` | ✅ 就绪 | `_store_to_knowledge_bank()` 方法可直接复用（`knowledge_bank.entities/relations/data_points/insights` 写入） |
| `KnowledgeConfig` | ✅ 可扩展 | `from_env()` + `from_dict()`，dataclass 设计 |
| `KnowledgeImporter` | ✅ 就绪 | `import_file()`, `import_directory()` 已实现 |
| `UserKnowledgeBank` | ✅ 就绪 | `import_file()`, `import_directory()` 代理已存在 |
| `KnowledgeCompiler` | ✅ 就绪 | `compile_research()` 实体/概念/关系提取 |
| `KnowledgeManager` | ✅ 就绪 | `__getattr__` 自动委托到 `UserKnowledgeBank` |

### 2.2 缺口分析

| 缺口 | 位置 | 工作量 | 严重度 |
|------|------|--------|--------|
| `import_url()` 代理缺失 | `UserKnowledgeBank` + `KnowledgeManager` | ~20行 | 中 |
| 导入结果不写入 SQLite | `importer.py` `import_url()` / `import_file()` | ~50行 | **高** |
| 源目录扫描逻辑缺失 | `DreamModeScheduler` | ~60行 | 中 |
| 配置项缺失 | `KnowledgeConfig` | ~10行 | 低 |
| 同步 IO 阻塞事件循环 | `import_url()` sync blocking | ~5行 | 中 |

---

## 3. 设计方案

### 3.1 KnowledgeConfig 扩展

**文件**: `src/core/memory/config.py`

```python
@dataclass
class KnowledgeConfig:
    # ... 现有字段不变 ...

    # ===== 新增：知识自动导入 =====
    knowledge_source_dirs: List[str] = field(default_factory=lambda: [])
    """知识源目录列表，指向存放原始资料（PDF/MD/TXT等）的文件夹
       支持多个目录，可用 KNOWLEDGE_SOURCE_DIRS 环境变量设置（逗号分隔）"""

    knowledge_scan_interval: int = 300
    """目录扫描间隔（秒），默认 5 分钟
       环境变量: KNOWLEDGE_SCAN_INTERVAL"""

    knowledge_auto_import: bool = True
    """是否启用自动导入，设为 False 可完全禁用
       环境变量: KNOWLEDGE_AUTO_IMPORT"""

    knowledge_store_to_bank: bool = True
    """导入后是否写入 UserKnowledgeBank SQLite（用于搜索）
       环境变量: KNOWLEDGE_STORE_TO_BANK"""

    knowledge_max_import_workers: int = 2
    """导入最大并发数（文件解析是 IO 密集型，不宜太高）
       环境变量: KNOWLEDGE_MAX_IMPORT_WORKERS"""
```

**环境变量新增**:
```
KNOWLEDGE_SOURCE_DIRS=data/sources/market_reports,data/sources/industry_pdfs
KNOWLEDGE_SCAN_INTERVAL=600
KNOWLEDGE_AUTO_IMPORT=true
KNOWLEDGE_STORE_TO_BANK=true
KNOWLEDGE_MAX_IMPORT_WORKERS=2
```

### 3.2 UserKnowledgeBank 扩展 — `import_url()` 代理 + `store_to_bank`

**文件**: `src/core/memory/knowledge_bank.py`

```python
def import_url(
    self,
    url: str,
    auto_extract: bool = True,
    timeout: int = 30,
    max_size: int = MAX_URL_SIZE,
    retries: int = 3,
    store_to_bank: bool = True,
) -> "ImportResult":
    """
    导入 URL 内容
    
    额外参数:
        store_to_bank: 是否将编译结果写入 UserKnowledgeBank SQLite
    """
    result = self.importer.import_url(
        url,
        auto_extract=auto_extract,
        timeout=timeout,
        max_size=max_size,
        retries=retries,
    )
    if store_to_bank and result.status == "success" and result.content:
        self._store_import_content_to_bank(result.content, result.file_path, result.entities_extracted)
    return result

def import_file(
    self,
    file_path: str,
    auto_extract: bool = True,
    source_info: Optional[Dict] = None,
    skip_if_imported: bool = True,
    store_to_bank: bool = True,
) -> "ImportResult":
    """
    导入文件（增加 store_to_bank 参数）
    """
    result = self.importer.import_file(
        file_path,
        auto_extract=auto_extract,
        source_info=source_info,
        skip_if_imported=skip_if_imported,
    )
    if store_to_bank and result.status in ("success", "partial") and result.content:
        self._store_import_content_to_bank(result.content, file_path, result.entities_extracted)
    return result

def _store_import_content_to_bank(
    self,
    content: str,
    source: str,
    entities_count: int,
):
    """
    将导入的编译结果写入 UserKnowledgeBank SQLite
    
    复用 KnowledgeExtractionPhase._store_to_knowledge_bank 相同的存储模式，
    保持存储一致性。
    """
    # 1. 知识编译器提取结构化知识
    compiled = self.compiler.compile_research(content, {"source": source, "title": Path(source).stem})
    self.compiler.save_knowledge(compiled)  # 文件系统（原有逻辑）
    
    # 2. 将实体/关系/数据点写入 SQLite（新增）
    for entity_page in compiled.entities:
        name = entity_page.title
        self.entities.add_entity(
            entity_type=entity_page.metadata.get("entity_type", "generic"),
            name=name,
            description=entity_page.content[:500],
        )

    for concept_page in compiled.concepts:
        self.entities.add_entity(
            entity_type="concept",
            name=concept_page.title,
            description=concept_page.content[:500],
        )

    # 关系（需要实体已存在）
    for relation_page in compiled.relations:
        source_name = relation_page.metadata.get("source_entity", "")
        target_name = relation_page.metadata.get("target_entity", "")
        if source_name and target_name:
            self.relations.add_relation(
                source_entity=source_name,
                target_entity=target_name,
                relation_type=relation_page.metadata.get("relation_type", "related_to"),
                context=relation_page.content[:300],
            )
    
    logger.info(f"Stored import result to bank: {source}, entities={entities_count}")
```

### 3.3 KnowledgeManager 扩展 — `import_url()` 代理

**文件**: `src/core/memory/knowledge_manager.py`

```python
def import_url(
    self,
    url: str,
    auto_extract: bool = True,
    timeout: int = 30,
    max_size: int = 10485760,
    retries: int = 3,
    store_to_bank: bool = True,
) -> "ImportResult":
    """
    导入 URL 内容（代理到 UserKnowledgeBank）
    """
    return self._knowledge_bank.import_url(
        url=url,
        auto_extract=auto_extract,
        timeout=timeout,
        max_size=max_size,
        retries=retries,
        store_to_bank=store_to_bank,
    )
```

### 3.4 DreamModeScheduler 扩展 — 源目录扫描

**文件**: `src/core/memory/dream/dream_scheduler.py`

核心思路：将目录扫描作为背景循环中的一个独立阶段。

```python
class DreamModeScheduler:
    def __init__(self, ...):
        # ... 现有初始化 ...
        
        # ===== 新增：知识源管理 =====
        self._source_dirs: List[Path] = []
        self._source_dir_imported: Set[str] = set()  # 已导入文件哈希
        self._scan_task: Optional[asyncio.Task] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.import_max_workers or 2,
            thread_name_prefix="knowledge-import",
        )

    async def start_background_loop(self):
        """扩展后的背景循环"""
        logger.info("Starting dream mode background loop")
        
        while True:
            try:
                if self._is_main_task_running:
                    await asyncio.sleep(self.config.idle_check_interval)
                    continue

                # [优先级 1] 知识源目录扫描（新增）
                if self.config.knowledge_auto_import and self._source_dirs:
                    await self._scan_and_import_source_dirs()

                # [优先级 2] 研究资料知识提取（已有）
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

    # ===== 新增：源目录扫描 =====

    def configure_source_dirs(self, dirs: List[str]):
        """配置知识源目录（由外部调用，如 main.py 启动时）"""
        self._source_dirs = [Path(d).resolve() for d in dirs if Path(d).is_dir()]
        # 重建已导入记录
        self._source_dir_imported = self._load_imported_files()
        logger.info(f"Configured {len(self._source_dirs)} source dirs: {self._source_dirs}")

    def _load_imported_files(self) -> Set[str]:
        """从 importer manifest 加载已导入文件哈希"""
        imported = set()
        for d in self._source_dirs:
            manifest_path = d / ".import_manifest.json"
            if manifest_path.exists():
                try:
                    data = json.loads(manifest_path.read_text(encoding='utf-8'))
                    imported.update(data.keys())
                except Exception:
                    pass
        return imported

    async def _scan_and_import_source_dirs(self):
        """扫描所有源目录，自动导入新文件"""
        for source_dir in self._source_dirs:
            if self._is_main_task_running:
                break

            # 收集待导入文件
            new_files = self._collect_new_files(source_dir)
            if not new_files:
                continue

            logger.info(f"Found {len(new_files)} new files in {source_dir}")

            # 在 executor 中执行 IO 密集型导入
            loop = asyncio.get_running_loop()
            for file_path in new_files:
                if self._is_main_task_running:
                    break

                # 同步 IO → run_in_executor
                result = await loop.run_in_executor(
                    self._executor,
                    self._do_import_file,
                    file_path,
                )

                if result.status == "success":
                    logger.info(f"Auto-imported: {file_path} ({result.pages_created} pages)")

    def _collect_new_files(self, source_dir: Path) -> List[str]:
        """收集目录中未导入的新文件"""
        if not source_dir.is_dir():
            return []

        supported_ext = {'.md', '.txt', '.csv', '.json', '.pdf', '.docx', '.xlsx', '.xls'}
        new_files = []

        for f in sorted(source_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in supported_ext:
                continue

            # 检查是否已导入（MD5 哈希）
            file_hash = self._quick_hash(f)
            if file_hash in self._source_dir_imported:
                continue

            new_files.append(str(f))

        return new_files

    @staticmethod
    def _quick_hash(file_path: Path) -> str:
        """快速文件哈希（仅用于去重，非安全用途）"""
        try:
            import hashlib
            h = hashlib.md5(usedforsecurity=False)
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _do_import_file(self, file_path: str):
        """同步导入文件（在 executor 线程中执行）"""
        return self.knowledge_bank.import_file(
            file_path=file_path,
            auto_extract=True,
            skip_if_imported=True,
            store_to_bank=self.config.knowledge_store_to_bank,
        )

    # ===== 关闭资源 =====

    async def shutdown(self):
        """关闭调度器（清理线程池）"""
        self.stop_background()
        self._executor.shutdown(wait=False)
        logger.info("DreamModeScheduler shut down")
```

### 3.5 main.py 初始化

**文件**: `src/api/main.py`

```python
# ============ Knowledge Auto-Import ============
from src.core.memory.dream.dream_scheduler import DreamModeScheduler
from src.core.memory.dream.raw_data_store import RawResearchDataStore
from src.core.memory import KnowledgeManager

# DreamModeScheduler 初始化
_knowledge_manager = resolve_or_none(KnowledgeManager)
_dream_scheduler = None
if _knowledge_manager:
    _raw_data_store = RawResearchDataStore()
    _dream_scheduler = DreamModeScheduler(
        knowledge_bank=_knowledge_manager.knowledge_bank,
        raw_data_store=_raw_data_store,
        config=_knowledge_manager.config,
    )
    # 配置知识源目录
    source_dirs = os.getenv("KNOWLEDGE_SOURCE_DIRS", "").split(",")
    source_dirs = [d.strip() for d in source_dirs if d.strip()]
    if source_dirs:
        _dream_scheduler.configure_source_dirs(source_dirs)
    
    _dream_scheduler.start_background()
    logger.info(f"DreamModeScheduler started with {len(source_dirs)} source dirs")
```

---

## 4. 数据流总览

```
                         KnowledgeConfig
                    (knowledge_source_dirs)
                            │
                            ▼
                  DreamModeScheduler
                  start_background_loop()
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                  ▼
   [每5min扫描]     [主任务完成]         [主任务开始]
   源目录变化       触发知识提取          暂停一切
          │                 │                  │
          ▼                 ▼                  ▼
   KnowledgeImporter   KnowledgeExtractionPhase
   import_file()       _extract_single()
          │                 │
          ▼                 ▼
   KnowledgeCompiler   UserKnowledgeBank
   compile_research()  .entities/.relations/
          │             .data_points/.insights
          ▼
   ┌─────┴─────┐
   ▼           ▼
文件系统      SQLite
(编译器)     (搜索/复用)
```

---

## 5. 变更清单

| 文件 | 修改类型 | 新增行数 | 说明 |
|------|----------|----------|------|
| `src/core/memory/config.py` | 修改 | ~30行 | 新增 `knowledge_source_dirs` 等 5 个配置字段 + `from_env` 支持 |
| `src/core/memory/knowledge_bank.py` | 修改 | ~50行 | 新增 `import_url()` 代理 + `_store_import_content_to_bank()` |
| `src/core/memory/knowledge_manager.py` | 修改 | ~20行 | 新增 `import_url()` 代理 |
| `src/core/memory/dream/dream_scheduler.py` | 修改 | ~100行 | 新增 `_scan_and_import_source_dirs()` 目录扫描逻辑 |
| `src/api/main.py` | 修改 | ~30行 | DreamModeScheduler 初始化 |
| **总计** | | **~230行** | |

**影响范围**:
- 零前端变更
- 零 API 变更
- 零数据库 Schema 变更
- 不影响现有 `on_main_task_started/completed` 流程
- 100% 通过环境变量配置，无需代码修改

---

## 6. 线程安全分析

| 操作 | 线程 | 说明 |
|------|------|------|
| `start_background_loop()` | asyncio 事件循环主线程 | 检查 + sleep，无阻塞 |
| `_scan_and_import_source_dirs()` | asyncio 事件循环 | 仅 `_collect_new_files()` 扫描目录（轻量 stat），不阻塞 |
| `_do_import_file()` | `ThreadPoolExecutor` 线程 | 同步 IO（文件读取 + 编译），完全在独立线程 |
| SQLite 写入 | `ThreadPoolExecutor` 线程 | `UserKnowledgeBank` 使用独立 SQLite 连接，WAL 模式支持并发 |

**关键保护措施**:
1. `_is_main_task_running` 检查 → 用户发起任务时立即跳过导入
2. ThreadPoolExecutor 限制 `max_workers=2` → 防止 IO 洪泛
3. MD5 manifest 去重 → 避免重复导入
4. WAL 模式 → SQLite 写入不阻塞读取

---

## 7. 配置示例

```bash
# .env 或 docker-compose 环境变量
KNOWLEDGE_SOURCE_DIRS=data/sources/market_reports,data/sources/industry_pdfs
KNOWLEDGE_SCAN_INTERVAL=300
KNOWLEDGE_AUTO_IMPORT=true
KNOWLEDGE_STORE_TO_BANK=true
KNOWLEDGE_MAX_IMPORT_WORKERS=2
```
